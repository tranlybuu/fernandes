import os
import json
import time
from .config import settings
from .emulator import EmulatorManager
from .llm_client import LLMClient

class WorkflowEngine:
    def __init__(self, workflows_dir: str = settings.workflows_dir):
        self.workflows_dir = workflows_dir
        os.makedirs(self.workflows_dir, exist_ok=True)

    def get_workflow_path(self, name: str) -> str:
        # Clean filename
        safe_name = "".join([c for c in name if c.isalpha() or c.isdigit() or c in (" ", "_", "-")]).rstrip()
        safe_name = safe_name.replace(" ", "_")
        return os.path.join(self.workflows_dir, f"{safe_name}.json")

    def list_workflows(self) -> list[str]:
        workflows = []
        for f in os.listdir(self.workflows_dir):
            if f.endswith(".json"):
                workflows.append(f[:-5])
        return sorted(workflows)

    def load_workflow(self, name: str) -> dict:
        path = self.get_workflow_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Workflow {name} not found.")
        with open(path, "r") as f:
            return json.load(f)

    def save_workflow(self, name: str, workflow_data: dict):
        path = self.get_workflow_path(name)
        with open(path, "w") as f:
            json.dump(workflow_data, f, indent=2)

    def delete_workflow(self, name: str):
        path = self.get_workflow_path(name)
        if os.path.exists(path):
            os.remove(path)

    def record_workflow(
        self,
        name: str,
        goal: str,
        emulator: EmulatorManager,
        llm: LLMClient,
        max_steps: int = 15,
        step_callback=None
    ) -> dict:
        """
        Runs the LLM-driven recording loop.
        Controls the emulator, queries LLM for actions, logs steps,
        and saves the resulting workflow.
        """
        steps = []
        history = []
        
        if step_callback:
            step_callback({"status": "starting", "message": f"Starting recording for workflow: {name}"})

        for step_idx in range(max_steps):
            try:
                # 1. Take annotated screenshot and parse elements
                screenshot_b64, elements = emulator.get_annotated_screenshot()
                
                # 2. Get LLM recommendation
                if step_callback:
                    step_callback({"status": "thinking", "step": step_idx + 1, "message": "LLM is thinking..."})
                
                llm_response = llm.get_next_action(
                    goal=goal,
                    history=history,
                    elements=elements,
                    screenshot_base64=screenshot_b64
                )
                
                action = llm_response.get("action")
                thought = llm_response.get("thought", "")
                target_id = llm_response.get("target_id")
                value = llm_response.get("value")
                explanation = llm_response.get("explanation", "")

                if step_callback:
                    step_callback({
                        "status": "decided",
                        "step": step_idx + 1,
                        "thought": thought,
                        "action": action,
                        "explanation": explanation,
                        "target_id": target_id,
                        "value": value
                    })

                if action == "stop":
                    if step_callback:
                        step_callback({"status": "completed", "message": "Goal achieved. Recording stopped."})
                    break

                # 3. Locate target element properties if click/input
                target_el = None
                selector = None
                cx, cy = 0, 0

                if action in ["click", "input_text"] and target_id is not None:
                    # Find element matching visual ID
                    for el in elements:
                        if el.get("visual_id") == int(target_id):
                            target_el = el
                            break
                    
                    if not target_el:
                        raise Exception(f"LLM specified visual ID {target_id} but it was not found on screen.")
                    
                    # Create selector for playback
                    selector = {
                        "resource_id": target_el.get("resource_id"),
                        "text": target_el.get("text"),
                        "content_desc": target_el.get("content_desc"),
                        "class_name": target_el.get("class_name")
                    }
                    cx, cy = target_el["center"]
                
                # 4. Execute action
                if action == "click":
                    emulator.click(cx, cy)
                    result_desc = f"Clicked at ({cx}, {cy})"
                elif action == "input_text":
                    # Focus first
                    emulator.click(cx, cy)
                    time.sleep(0.5)
                    emulator.input_text(value)
                    result_desc = f"Entered text '{value}' at ({cx}, {cy})"
                elif action == "press_key":
                    emulator.press_key(value)
                    result_desc = f"Pressed key '{value}'"
                elif action == "swipe":
                    # Swipe direction to coordinate
                    # Swipe starts in center of screen
                    width, height = emulator.d.window_size()
                    cx, cy = width // 2, height // 2
                    if value == "up":
                        emulator.swipe(cx, cy + int(height * 0.25), cx, cy - int(height * 0.25))
                    elif value == "down":
                        emulator.swipe(cx, cy - int(height * 0.25), cx, cy + int(height * 0.25))
                    elif value == "left":
                        emulator.swipe(cx + int(width * 0.25), cy, cx - int(width * 0.25), cy)
                    elif value == "right":
                        emulator.swipe(cx - int(width * 0.25), cy, cx + int(width * 0.25), cy)
                    result_desc = f"Swiped {value}"
                else:
                    raise Exception(f"Unknown action {action}")

                # 5. Record step
                step_record = {
                    "step_number": step_idx + 1,
                    "action": action,
                    "selector": selector,
                    "value": value,
                    "description": explanation
                }
                steps.append(step_record)
                
                # 6. Update history for LLM
                history.append({
                    "action": action,
                    "description": explanation,
                    "result_desc": result_desc
                })

                # Pause to let UI transition
                time.sleep(2.0)

            except Exception as e:
                if step_callback:
                    step_callback({"status": "error", "message": f"Error during recording step: {e}"})
                print(f"Recording error: {e}")
                break

        # Save workflow
        workflow_data = {
            "name": name,
            "goal": goal,
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": steps
        }
        self.save_workflow(name, workflow_data)
        return workflow_data

    def find_matching_element(self, selector: dict, current_elements: list[dict]) -> dict | None:
        """Finds the best matching element in the hierarchy based on selector."""
        best_match = None
        best_score = 0

        for el in current_elements:
            score = 0
            weight_total = 0

            # Match resource_id
            if selector.get("resource_id"):
                weight_total += 5
                if el.get("resource_id") == selector["resource_id"]:
                    score += 5

            # Match text
            if selector.get("text"):
                weight_total += 4
                if el.get("text") == selector["text"]:
                    score += 4

            # Match content_desc
            if selector.get("content_desc"):
                weight_total += 4
                if el.get("content_desc") == selector["content_desc"]:
                    score += 4

            # Match class_name
            if selector.get("class_name"):
                weight_total += 1
                if el.get("class_name") == selector["class_name"]:
                    score += 1

            if weight_total > 0:
                match_percentage = score / weight_total
                # Require at least 60% match, and choose the highest score
                if match_percentage >= 0.6 and score > best_score:
                    best_score = score
                    best_match = el

        return best_match

    def playback_workflow(
        self,
        name: str,
        emulator: EmulatorManager,
        step_callback=None
    ) -> bool:
        """
        Executes a recorded workflow deterministically.
        Loads steps from JSON, resolves semantic selectors, and performs actions.
        NO LLM is used.
        """
        workflow = self.load_workflow(name)
        steps = workflow.get("steps", [])

        if step_callback:
            step_callback({"status": "starting", "message": f"Starting playback of workflow '{name}'"})

        for idx, step in enumerate(steps):
            step_num = step.get("step_number", idx + 1)
            action = step["action"]
            selector = step.get("selector")
            value = step.get("value")
            description = step.get("description", "")

            if step_callback:
                step_callback({
                    "status": "executing",
                    "step": step_num,
                    "description": description,
                    "action": action,
                    "value": value
                })

            try:
                # Resolve coordinates for actions targeting elements
                if action in ["click", "input_text"] and selector:
                    # Retrieve elements from current screen
                    matched_el = None
                    retries = 3
                    
                    # Try to locate element with retries (waiting for page load)
                    for attempt in range(retries):
                        elements = emulator.extract_elements()
                        matched_el = self.find_matching_element(selector, elements)
                        if matched_el:
                            break
                        time.sleep(1.0) # wait before retrying

                    if not matched_el:
                        # Deterministic matching failed! Try self-healing using LLM.
                        if step_callback:
                            step_callback({
                                "status": "healing", 
                                "step": step_num, 
                                "message": f"Element not found. Starting LLM Self-Healing..."
                            })
                        
                        # Initialize LLM Client
                        from .config import settings
                        from .llm_client import LLMClient
                        
                        # Build default client from persistent config
                        provider = "gemini"
                        api_key = settings.gemini_api_key
                        if not api_key:
                            if settings.openai_api_key:
                                provider = "openai"
                                api_key = settings.openai_api_key
                            elif settings.anthropic_api_key:
                                provider = "anthropic"
                                api_key = settings.anthropic_api_key
                            else:
                                provider = "local"
                        
                        llm = LLMClient(
                            provider=provider,
                            api_key=api_key,
                            base_url=settings.local_llm_url if provider == "local" else None,
                            model=settings.local_llm_model if provider == "local" else None
                        )
                        
                        # Capture screen elements and annotated screenshot
                        screenshot_b64, current_elements = emulator.get_annotated_screenshot()
                        
                        # Call LLM to suggest recovery action
                        heal_res = llm.heal_step(
                            goal=workflow.get("goal", ""),
                            failed_step=step,
                            elements=current_elements,
                            screenshot_base64=screenshot_b64
                        )
                        
                        heal_action = heal_res.get("action")
                        heal_target_id = heal_res.get("target_id")
                        heal_value = heal_res.get("value")
                        heal_explanation = heal_res.get("explanation", "")
                        
                        if step_callback:
                            step_callback({
                                "status": "healing_decision",
                                "step": step_num,
                                "message": f"LLM decided: {heal_action.upper()} - {heal_explanation}"
                            })
                        
                        if heal_action == "skip":
                            if step_callback:
                                step_callback({"status": "success", "step": step_num, "message": "Step skipped by LLM"})
                            time.sleep(1.0)
                            continue
                        
                        # Execute healed action
                        healed_el = None
                        if heal_action in ["click", "input_text"] and heal_target_id is not None:
                            for el in current_elements:
                                if el.get("visual_id") == int(heal_target_id):
                                    healed_el = el
                                    break
                            
                            if not healed_el:
                                raise Exception(f"LLM specified visual ID {heal_target_id} for healing, but it was not found on screen.")
                            
                            cx, cy = healed_el["center"]
                            if heal_action == "click":
                                emulator.click(cx, cy)
                            elif heal_action == "input_text":
                                emulator.click(cx, cy)
                                time.sleep(0.5)
                                emulator.input_text(heal_value or value)
                                
                            # SELF-HEALING UPDATE:
                            # Update the step's selector in the active workflow steps list
                            step["selector"] = {
                                "resource_id": healed_el.get("resource_id"),
                                "text": healed_el.get("text"),
                                "content_desc": healed_el.get("content_desc"),
                                "class_name": healed_el.get("class_name")
                            }
                            # Update workflow file on disk
                            workflow["steps"][idx] = step
                            self.save_workflow(name, workflow)
                            if step_callback:
                                step_callback({
                                    "status": "healed", 
                                    "step": step_num, 
                                    "message": f"Saved workflow '{name}.json' has been self-healed!"
                                })
                                
                        elif heal_action == "press_key":
                            emulator.press_key(heal_value)
                        elif heal_action == "swipe":
                            width, height = emulator.d.window_size()
                            cx, cy = width // 2, height // 2
                            if heal_value == "up":
                                emulator.swipe(cx, cy + int(height * 0.25), cx, cy - int(height * 0.25))
                            elif heal_value == "down":
                                emulator.swipe(cx, cy - int(height * 0.25), cx, cy + int(height * 0.25))
                            elif heal_value == "left":
                                emulator.swipe(cx + int(width * 0.25), cy, cx - int(width * 0.25), cy)
                            elif heal_value == "right":
                                emulator.swipe(cx - int(width * 0.25), cy, cx + int(width * 0.25), cy)
                        else:
                            raise Exception(f"Failed to find element and LLM healing was unable to recover.")
                    else:
                        cx, cy = matched_el["center"]
                        
                        if action == "click":
                            emulator.click(cx, cy)
                        elif action == "input_text":
                            emulator.click(cx, cy)
                            time.sleep(0.5)
                            emulator.input_text(value)
                
                elif action == "press_key":
                    emulator.press_key(value)
                
                elif action == "swipe":
                    width, height = emulator.d.window_size()
                    cx, cy = width // 2, height // 2
                    if value == "up":
                        emulator.swipe(cx, cy + int(height * 0.25), cx, cy - int(height * 0.25))
                    elif value == "down":
                        emulator.swipe(cx, cy - int(height * 0.25), cx, cy + int(height * 0.25))
                    elif value == "left":
                        emulator.swipe(cx + int(width * 0.25), cy, cx - int(width * 0.25), cy)
                    elif value == "right":
                        emulator.swipe(cx - int(width * 0.25), cy, cx + int(width * 0.25), cy)
                
                else:
                    raise Exception(f"Unsupported action: {action}")

                if step_callback:
                    step_callback({"status": "success", "step": step_num})
                
                # Wait for screen update
                time.sleep(2.0)

            except Exception as e:
                if step_callback:
                    step_callback({"status": "failed", "step": step_num, "message": str(e)})
                print(f"Playback error at step {step_num}: {e}")
                return False

        if step_callback:
            step_callback({"status": "completed", "message": "Playback completed successfully."})
        return True
