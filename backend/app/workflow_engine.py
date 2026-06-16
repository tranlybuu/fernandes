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
        self.stop_requested = set()

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

    def request_stop(self, device_serial: str):
        if device_serial:
            self.stop_requested.add(device_serial)

    def record_workflow(
        self,
        name: str,
        goal: str,
        emulator: EmulatorManager,
        llm: LLMClient,
        max_steps: int = 15,
        step_callback=None,
        plan: list[str] | None = None
    ) -> dict:
        """
        Runs the LLM-driven recording loop.
        Controls the emulator, queries LLM for actions, logs steps,
        and saves the resulting workflow.
        """
        steps = []
        history = []
        
        # Capture current package at start of recording
        initial_package = None
        try:
            initial_package = emulator.get_current_package()
        except Exception:
            pass
        
        # Generate or use high-level plan
        if plan is not None:
            if step_callback:
                step_callback({"status": "plan_generated", "plan": plan})
        else:
            if step_callback:
                step_callback({"status": "starting", "message": "Analyzing goal and generating initial plan..."})
            plan = llm.generate_initial_plan(goal)
            if step_callback:
                step_callback({"status": "plan_generated", "plan": plan})
        
        if step_callback:
            step_callback({"status": "starting", "message": f"Starting recording for workflow: {name}"})

        for step_idx in range(max_steps):
            try:
                # Check for stop request
                if emulator.device_serial in self.stop_requested:
                    self.stop_requested.discard(emulator.device_serial)
                    if step_callback:
                        step_callback({"status": "completed", "message": "Recording stopped by user."})
                    break

                # 1. Take annotated screenshot and parse elements
                screenshot_b64, elements = emulator.get_annotated_screenshot()
                
                # 2. Get LLM recommendation
                if step_callback:
                    step_callback({"status": "thinking", "step": step_idx + 1, "message": "LLM is thinking..."})
                
                llm_response = llm.get_next_action(
                    goal=goal,
                    history=history,
                    elements=elements,
                    screenshot_base64=screenshot_b64,
                    plan=plan
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

                # 7. Validate step progress
                try:
                    val_screenshot_b64, val_elements = emulator.get_annotated_screenshot()
                    
                    if step_callback:
                        step_callback({"status": "thinking", "step": step_idx + 1, "message": "Validating step progress..."})
                    
                    val_res = llm.validate_step_progress(
                        goal=goal,
                        plan=plan,
                        history=history,
                        elements=val_elements,
                        screenshot_base64=val_screenshot_b64
                    )
                    
                    completed_indices = val_res.get("completed_indices", [])
                    current_index = val_res.get("current_index", 0)
                    goal_achieved = val_res.get("goal_achieved", False)
                    is_looping = val_res.get("is_looping", False)
                    reason = val_res.get("reason", "")
                    
                    if step_callback:
                        step_callback({
                            "status": "plan_update",
                            "completed_indices": completed_indices,
                            "current_index": current_index,
                            "goal_achieved": goal_achieved
                        })
                    
                    if is_looping:
                        if step_callback:
                            step_callback({"status": "completed", "message": f"Loop detected: {reason or 'Repeated execution loop'}. Stopping flow validation."})
                        break

                    if goal_achieved:
                        if step_callback:
                            step_callback({"status": "completed", "message": "Goal fully achieved based on validation! Recording stopped."})
                        break
                except Exception as val_err:
                    print(f"Validation error: {val_err}")

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
            "initial_package": initial_package,
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

    def reset_to_initial_state(self, initial_package: str | None, emulator: EmulatorManager):
        if not initial_package:
            # Fallback to pressing home
            emulator.press_key("home")
            time.sleep(2.0)
            return
        
        # Check if the package is a launcher
        is_launcher = any(launcher in initial_package for launcher in [
            "launcher", "trebuchet", "desktop", "carousellauncher", "com.android.systemui"
        ])
        
        if is_launcher:
            emulator.press_key("home")
        else:
            try:
                emulator.stop_app(initial_package)
                time.sleep(1.0)
                emulator.launch_app(initial_package)
            except Exception:
                emulator.press_key("home")
        time.sleep(3.0) # Let the app/home screen load

    def playback_workflow(
        self,
        name: str,
        emulator: EmulatorManager,
        step_callback=None,
        is_refining: bool = False
    ) -> bool:
        """
        Executes a recorded workflow.
        Loads steps from JSON, resolves semantic selectors, and performs actions.
        If a step fails, LLM is used for up to 3 self-healing attempts.
        """
        workflow = self.load_workflow(name)
        steps = workflow.get("steps", [])
        initial_package = workflow.get("initial_package")

        if step_callback:
            step_callback({"status": "starting", "message": f"Starting playback of workflow '{name}'"})

        # Reset emulator to initial state
        if initial_package or is_refining:
            if step_callback:
                step_callback({"status": "starting", "message": "Resetting emulator to initial state..."})
            self.reset_to_initial_state(initial_package, emulator)

        # Iterate over a static copy of the steps list to prevent index shifting issues when mutating workflow steps
        steps_for_execution = list(steps)

        for idx, step in enumerate(steps_for_execution):
            # Check for stop request
            if emulator.device_serial in self.stop_requested:
                self.stop_requested.discard(emulator.device_serial)
                if step_callback:
                    step_callback({"status": "completed", "message": "Playback stopped by user."})
                return False

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
                        passed = False
                        for heal_attempt in range(3):
                            if step_callback:
                                step_callback({
                                    "status": "healing", 
                                    "step": step_num, 
                                    "message": f"Element not found. Starting LLM Self-Healing (Attempt {heal_attempt + 1}/3)..."
                                })
                            
                            # Initialize LLM Client
                            from .config import settings
                            from .llm_client import LLMClient
                            
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
                            heal_type = heal_res.get("type", "recovery")
                            
                            if step_callback:
                                step_callback({
                                    "status": "healing_decision",
                                    "step": step_num,
                                    "message": f"LLM decided: {heal_action.upper()} ({heal_type}) - {heal_explanation}"
                                })
                            
                            if heal_action == "skip":
                                if step_callback:
                                    step_callback({"status": "success", "step": step_num, "message": "Step skipped by LLM"})
                                time.sleep(1.0)
                                passed = True
                                break
                            
                            # Execute healed action
                            healed_el = None
                            if heal_action in ["click", "input_text"] and heal_target_id is not None:
                                for el in current_elements:
                                    if el.get("visual_id") == int(heal_target_id):
                                        healed_el = el
                                        break
                                
                                if not healed_el:
                                    if step_callback:
                                        step_callback({
                                            "status": "healing",
                                            "step": step_num,
                                            "message": f"LLM specified visual ID {heal_target_id} for healing, but it was not found on screen."
                                        })
                                    time.sleep(1.0)
                                    continue
                                
                                cx, cy = healed_el["center"]
                                if heal_action == "click":
                                    emulator.click(cx, cy)
                                elif heal_action == "input_text":
                                    emulator.click(cx, cy)
                                    time.sleep(0.5)
                                    emulator.input_text(heal_value or value)
                            
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
                                if step_callback:
                                    step_callback({
                                        "status": "healing",
                                        "step": step_num,
                                        "message": f"LLM healing was unable to recover or returned unknown action: {heal_action}"
                                    })
                                time.sleep(1.0)
                                continue
                            
                            # Wait for screen update
                            time.sleep(2.0)
                            
                            if heal_type == "selector_update":
                                # Selector update means this element *is* the target element, just updated.
                                # The step has now been executed.
                                if is_refining and healed_el:
                                    # Find the exact step reference in workflow["steps"] to update it
                                    for s in workflow["steps"]:
                                        if s is step:
                                            s["selector"] = {
                                                "resource_id": healed_el.get("resource_id"),
                                                "text": healed_el.get("text"),
                                                "content_desc": healed_el.get("content_desc"),
                                                "class_name": healed_el.get("class_name")
                                            }
                                            break
                                    self.save_workflow(name, workflow)
                                    if step_callback:
                                        step_callback({
                                            "status": "healed",
                                            "step": step_num,
                                            "message": f"Saved workflow '{name}.json' has been self-healed (selector updated)!"
                                        })
                                passed = True
                                break
                            
                            else: # "recovery" action
                                # Insert recovery action into workflow on disk if we are in refinement mode
                                if is_refining:
                                    recovery_step = {
                                        "step_number": idx + 1,
                                        "action": heal_action,
                                        "selector": {
                                            "resource_id": healed_el.get("resource_id") if healed_el else None,
                                            "text": healed_el.get("text") if healed_el else None,
                                            "content_desc": healed_el.get("content_desc") if healed_el else None,
                                            "class_name": healed_el.get("class_name") if healed_el else None
                                        } if heal_action in ["click", "input_text"] else None,
                                        "value": heal_value,
                                        "description": f"Healed recovery: {heal_explanation}"
                                    }
                                    
                                    # Find step index dynamically in case it shifted
                                    target_idx = -1
                                    for i, s in enumerate(workflow["steps"]):
                                        if s is step:
                                            target_idx = i
                                            break
                                    if target_idx != -1:
                                        workflow["steps"].insert(target_idx, recovery_step)
                                        for i, s in enumerate(workflow["steps"]):
                                            s["step_number"] = i + 1
                                        self.save_workflow(name, workflow)
                                        if step_callback:
                                            step_callback({
                                                "status": "healed",
                                                "step": step_num,
                                                "message": f"Saved workflow '{name}.json' has been self-healed (inserted recovery step)!"
                                            })
                                
                                # Now check if the original element is visible
                                elements = emulator.extract_elements()
                                matched_el = self.find_matching_element(selector, elements)
                                if matched_el:
                                    cx, cy = matched_el["center"]
                                    if action == "click":
                                        emulator.click(cx, cy)
                                    elif action == "input_text":
                                        emulator.click(cx, cy)
                                        time.sleep(0.5)
                                        emulator.input_text(value)
                                    passed = True
                                    if step_callback:
                                        step_callback({
                                            "status": "success",
                                            "step": step_num,
                                            "message": "Original step executed successfully after recovery!"
                                        })
                                    time.sleep(2.0)
                                    break
                                else:
                                    if step_callback:
                                        step_callback({
                                            "status": "healing",
                                            "step": step_num,
                                            "message": "Original element still not found after recovery. Retrying..."
                                        })
                        
                        if not passed:
                            if step_callback:
                                step_callback({
                                    "status": "failed",
                                    "step": step_num,
                                    "message": f"Step {step_num} failed after 3 healing attempts. Proceeding to next step..."
                                })
                            continue
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
                # Proceed to next step without aborting
                continue

        if step_callback:
            step_callback({"status": "completed", "message": "Playback completed successfully."})
        return True
