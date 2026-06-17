"""
workflow_engine.py — BrowserUse-inspired ReAct agent loop for Android automation.

Architecture:
  AgentState          — immutable snapshot of agent's in-flight state
  WorkflowEngine      — CRUD + record/playback/test runner
    record_workflow() — ReAct loop: Think → Act → Validate → [Replan|Intervene]
    playback_workflow()— deterministic playback with self-healing
    run_test_cases()  — post-workflow assertion runner
    post_intervention()— inject user guidance into a running session
"""

import os
import json
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .config import settings
from .emulator import EmulatorManager
from .llm_client import LLMClient


# ---------------------------------------------------------------------------
# Agent state (carried across loop iterations)
# ---------------------------------------------------------------------------

@dataclass
class AgentState:
    goal: str
    plan: list                          # list of str or conditional-dict steps
    steps: list = field(default_factory=list)   # recorded action steps (written to JSON)
    history: list = field(default_factory=list) # action history fed to LLM
    memory: str = ""                    # LLM persistent scratchpad
    current_plan_idx: int = 0
    consecutive_failures: int = 0
    total_actions: int = 0
    last_action_key: str = ""
    same_action_count: int = 0


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    def __init__(self, workflows_dir: str = settings.workflows_dir):
        self.workflows_dir = workflows_dir
        os.makedirs(self.workflows_dir, exist_ok=True)

        # Device-level stop requests (keyed by device serial)
        self.stop_requested: set[str] = set()

        # Per-session intervention state (keyed by session_id = workflow name)
        self._intervention_events: dict[str, threading.Event] = {}
        self._intervention_messages: dict[str, str] = {}
        self.active_sessions: dict[str, LLMClient] = {}

    # -----------------------------------------------------------------------
    # CRUD helpers
    # -----------------------------------------------------------------------

    def _safe_name(self, name: str) -> str:
        import unicodedata
        normalized_name = unicodedata.normalize('NFC', name)
        safe = "".join([c for c in normalized_name if c.isalpha() or c.isdigit() or c in (" ", "_", "-")]).rstrip()
        return safe.replace(" ", "_")

    def get_workflow_path(self, name: str) -> str:
        return os.path.join(self.workflows_dir, f"{self._safe_name(name)}.json")

    def list_workflows(self) -> list[str]:
        import unicodedata
        names = []
        for f in os.listdir(self.workflows_dir):
            if f.endswith(".json"):
                names.append(unicodedata.normalize('NFC', f[:-5]))
        return sorted(names)

    def load_workflow(self, name: str) -> dict:
        import unicodedata
        name = unicodedata.normalize('NFC', name)
        path = self.get_workflow_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Workflow '{name}' not found.")
        with open(path, "r") as f:
            return json.load(f)

    def save_workflow(self, name: str, workflow_data: dict):
        import unicodedata
        name = unicodedata.normalize('NFC', name)
        path = self.get_workflow_path(name)
        with open(path, "w") as f:
            json.dump(workflow_data, f, indent=2)

    def delete_workflow(self, name: str):
        import unicodedata
        name = unicodedata.normalize('NFC', name)
        path = self.get_workflow_path(name)
        if os.path.exists(path):
            os.remove(path)

    # -----------------------------------------------------------------------
    # Stop / intervention controls
    # -----------------------------------------------------------------------

    def request_stop(self, device_serial: str):
        if device_serial:
            self.stop_requested.add(device_serial)

    def post_intervention(self, session_id: str, message: str) -> bool:
        """
        Inject a user guidance message into a running recording session.
        Returns True if the session is active and the message was delivered.
        """
        import unicodedata
        session_id = unicodedata.normalize('NFC', session_id)
        if session_id not in self._intervention_events:
            return False
        self._intervention_messages[session_id] = message
        self._intervention_events[session_id].set()
        return True

    # -----------------------------------------------------------------------
    # Test case management
    # -----------------------------------------------------------------------

    def get_test_cases(self, name: str) -> list:
        try:
            return self.load_workflow(name).get("test_cases", [])
        except FileNotFoundError:
            return []

    def add_test_case(self, name: str, test_case: dict) -> dict:
        test_case.setdefault("id", f"tc_{uuid.uuid4().hex[:8]}")
        test_case.setdefault("check_type", "llm_assert")
        test_case.setdefault("status", "pending")
        test_case.setdefault("last_result", None)
        test_case.setdefault("last_run_at", None)

        wf = self.load_workflow(name)
        wf.setdefault("test_cases", []).append(test_case)
        self.save_workflow(name, wf)
        return test_case

    def update_test_case(self, name: str, tc_id: str, updates: dict) -> dict | None:
        wf = self.load_workflow(name)
        for tc in wf.get("test_cases", []):
            if tc.get("id") == tc_id:
                tc.update(updates)
                self.save_workflow(name, wf)
                return tc
        return None

    def delete_test_case(self, name: str, tc_id: str) -> bool:
        wf = self.load_workflow(name)
        tcs = wf.get("test_cases", [])
        new_tcs = [tc for tc in tcs if tc.get("id") != tc_id]
        if len(new_tcs) == len(tcs):
            return False
        wf["test_cases"] = new_tcs
        self.save_workflow(name, wf)
        return True

    # -----------------------------------------------------------------------
    # Action execution helper
    # -----------------------------------------------------------------------

    def _execute_action(
        self,
        action: str,
        llm_response: dict,
        elements: list[dict],
        emulator: EmulatorManager
    ) -> tuple[str, str | None]:
        """
        Execute an action from the LLM response.
        Returns (result_description, error_message_or_None).
        """
        target_id = llm_response.get("target_id")
        value = llm_response.get("value")
        explanation = llm_response.get("explanation", "")

        try:
            if action in ["click", "input_text"] and target_id is not None:
                target_el = next(
                    (el for el in elements if el.get("visual_id") == int(target_id)), None
                )
                if not target_el:
                    return "", f"Element ID {target_id} not found on screen"

                cx, cy = target_el["center"]
                label = target_el.get("text") or target_el.get("content_desc") or explanation

                if action == "click":
                    emulator.click(cx, cy)
                    return f"Clicked '{label}'", None
                else:  # input_text
                    emulator.click(cx, cy)
                    time.sleep(0.5)
                    emulator.input_text(value or "")
                    return f"Typed '{value}'", None

            elif action == "press_key":
                emulator.press_key(value)
                return f"Pressed key '{value}'", None

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
                return f"Swiped {value}", None

            elif action == "open_app":
                app_name = (value or "").strip()
                launched = emulator.launch_app_by_name(app_name)
                if launched:
                    return f"Opened app '{app_name}'", None
                else:
                    # Fallback: press home so LLM can retry navigation
                    emulator.press_key("home")
                    return f"Pressed home (could not find package for '{app_name}')", None

            else:
                return "", f"Unknown action: '{action}'"

        except Exception as e:
            return "", str(e)

    # -----------------------------------------------------------------------
    # Build selector dict from element for recording
    # -----------------------------------------------------------------------

    def _selector_from_element(self, el: dict) -> dict:
        return {
            "resource_id": el.get("resource_id"),
            "text": el.get("text"),
            "content_desc": el.get("content_desc"),
            "class_name": el.get("class_name")
        }

    # -----------------------------------------------------------------------
    # Await intervention with timeout
    # -----------------------------------------------------------------------

    def _wait_for_intervention(
        self,
        session_id: str,
        timeout: float,
        state: AgentState,
        step_callback: Callable | None
    ) -> bool:
        """Block until user sends a message or timeout expires. Returns True if got message."""
        got = self._intervention_events[session_id].wait(timeout=timeout)
        if got:
            self._intervention_events[session_id].clear()
            msg = self._intervention_messages.pop(session_id, None)
            if msg:
                state.history.append({
                    "action": "user_intervention",
                    "description": f"User guidance: {msg}",
                    "result_desc": "User provided guidance"
                })
                if step_callback:
                    step_callback({
                        "status": "intervention_received",
                        "message": f"Received user guidance: {msg}",
                        "session_id": session_id
                    })
        return got

    # -----------------------------------------------------------------------
    # Main recording loop (ReAct)
    # -----------------------------------------------------------------------

    def record_workflow(
        self,
        name: str,
        goal: str,
        emulator: EmulatorManager,
        llm: LLMClient,
        max_steps: int = 25,
        step_callback: Callable | None = None,
        plan: list | None = None
    ) -> dict:
        """
        ReAct loop: Think → Act → Validate → [Replan | Intervene].
        Records each successful action and saves the workflow JSON on completion.
        """
        import unicodedata
        name = unicodedata.normalize('NFC', name)
        session_id = name
        self.active_sessions[session_id] = llm
        self._intervention_events[session_id] = threading.Event()
        self._intervention_messages.pop(session_id, None)

        state = AgentState(goal=goal, plan=plan or [])

        try:
            # Capture initial package
            initial_package = None
            try:
                initial_package = emulator.get_current_package()
            except Exception:
                pass

            # Generate plan if not provided
            if not state.plan:
                if step_callback:
                    step_callback({"status": "starting", "message": "Generating initial plan..."})
                state.plan = self.active_sessions.get(session_id, llm).generate_initial_plan(goal)

            if step_callback:
                step_callback({"status": "plan_generated", "plan": state.plan})
                step_callback({"status": "starting", "message": f"Starting recording for: {name}"})

            # ── MAIN LOOP ──────────────────────────────────────────────────
            for step_idx in range(max_steps):

                # ① Check stop request
                if emulator.device_serial in self.stop_requested:
                    self.stop_requested.discard(emulator.device_serial)
                    if step_callback:
                        step_callback({"status": "completed", "message": "Recording stopped by user."})
                    break

                # ② Check for pending intervention
                pending_intervention = None
                if self._intervention_events[session_id].is_set():
                    self._intervention_events[session_id].clear()
                    pending_intervention = self._intervention_messages.pop(session_id, None)
                    if pending_intervention:
                        state.history.append({
                            "action": "user_intervention",
                            "description": f"User guidance: {pending_intervention}",
                            "result_desc": "User provided guidance"
                        })
                        if step_callback:
                            step_callback({
                                "status": "intervention_received",
                                "message": f"Following user guidance: {pending_intervention}",
                                "session_id": session_id
                            })

                # ③ Capture screen
                screenshot_b64, elements = emulator.get_annotated_screenshot()

                if step_callback:
                    step_callback({
                        "status": "thinking",
                        "step": step_idx + 1,
                        "message": "Agent analyzing screen..."
                    })

                active_llm = self.active_sessions.get(session_id, llm)

                # ④ Think: call LLM for next action
                llm_response = active_llm.get_next_action(
                    goal=goal,
                    plan=state.plan,
                    current_plan_idx=state.current_plan_idx,
                    history=state.history,
                    memory=state.memory,
                    elements=elements,
                    screenshot_base64=screenshot_b64,
                    intervention=pending_intervention
                )

                # Update persistent memory
                if llm_response.get("memory"):
                    state.memory = llm_response["memory"]

                action = llm_response.get("action", "stop")
                evaluation = llm_response.get("evaluation_previous_goal", "")
                next_goal_desc = llm_response.get("next_goal", "")
                explanation = llm_response.get("explanation", "")
                target_id = llm_response.get("target_id")
                value = llm_response.get("value")

                if step_callback:
                    step_callback({
                        "status": "decided",
                        "step": step_idx + 1,
                        "evaluation": evaluation,
                        "next_goal": next_goal_desc,
                        "action": action,
                        "explanation": explanation,
                        "target_id": target_id,
                        "value": value,
                        "thought": llm_response.get("thought", "")
                    })

                # ⑤ Terminal actions
                if action in ["done", "stop"]:
                    if step_callback:
                        step_callback({"status": "completed", "message": "Goal achieved! Recording stopped."})
                    break

                if action == "needs_intervention":
                    if step_callback:
                        step_callback({
                            "status": "needs_intervention",
                            "message": explanation or "Agent needs guidance to continue.",
                            "session_id": session_id
                        })
                    got = self._wait_for_intervention(session_id, timeout=300, state=state, step_callback=step_callback)
                    if not got:
                        if step_callback:
                            step_callback({"status": "completed", "message": "Intervention timeout. Recording stopped."})
                        break
                    # Re-read intervention message and inject it
                    last_intervention = state.history[-1].get("description", "") if state.history else ""
                    continue

                # ⑥ Loop detection: same action key N times in a row
                action_key = f"{action}:{target_id}:{value}"
                if action_key == state.last_action_key:
                    state.same_action_count += 1
                else:
                    state.same_action_count = 0
                    state.last_action_key = action_key

                if state.same_action_count >= 3:
                    if step_callback:
                        step_callback({
                            "status": "thinking",
                            "step": step_idx + 1,
                            "message": "Detected action repetition — pressing home to reset."
                        })
                    emulator.press_key("home")
                    time.sleep(1.5)
                    state.same_action_count = 0
                    state.last_action_key = ""
                    state.history.append({
                        "action": "press_key",
                        "description": "Pressed home to break repetition loop",
                        "result_desc": "Pressed home"
                    })
                    continue

                # ⑦ Execute action
                result_desc, error = self._execute_action(action, llm_response, elements, emulator)

                if error:
                    state.consecutive_failures += 1
                    state.history.append({
                        "action": action,
                        "description": explanation,
                        "result_desc": f"FAILED: {error}",
                        "error": error,
                        "evaluation": evaluation
                    })
                    if step_callback:
                        step_callback({
                            "status": "step_error",
                            "step": step_idx + 1,
                            "message": f"Action failed: {error}"
                        })
                    # After 4 consecutive failures → ask for user help
                    if state.consecutive_failures >= 4:
                        if step_callback:
                            step_callback({
                                "status": "needs_intervention",
                                "message": f"Agent failed {state.consecutive_failures} consecutive times. Please provide guidance.",
                                "session_id": session_id
                            })
                        got = self._wait_for_intervention(session_id, timeout=120, state=state, step_callback=step_callback)
                        state.consecutive_failures = 0
                    continue

                state.consecutive_failures = 0
                state.total_actions += 1

                # Build selector for recording (only for click/input_text)
                selector = None
                if action in ["click", "input_text"] and target_id is not None:
                    for el in elements:
                        if el.get("visual_id") == int(target_id):
                            selector = self._selector_from_element(el)
                            break

                # Record step
                state.steps.append({
                    "step_number": state.total_actions,
                    "action": action,
                    "selector": selector,
                    "value": value,
                    "description": explanation
                })

                state.history.append({
                    "action": action,
                    "description": explanation,
                    "result_desc": result_desc,
                    "evaluation": evaluation
                })

                if step_callback:
                    step_callback({
                        "status": "decided",
                        "step": step_idx + 1,
                        "action": action,
                        "explanation": explanation,
                        "thought": next_goal_desc
                    })

                # Wait for UI transition
                time.sleep(1.5)

                # ⑧ Validate progress after each action
                try:
                    val_screenshot, val_elements = emulator.get_annotated_screenshot()

                    val_res = active_llm.validate_step_progress(
                        goal=goal,
                        plan=state.plan,
                        history=state.history,
                        elements=val_elements,
                        screenshot_base64=val_screenshot
                    )

                    completed_indices = val_res.get("completed_indices", [])
                    current_index = val_res.get("current_index", state.current_plan_idx)
                    goal_achieved = val_res.get("goal_achieved", False)
                    is_looping = val_res.get("is_looping", False)
                    needs_replan = val_res.get("needs_replan", False)
                    val_reason = val_res.get("reason", "")

                    state.current_plan_idx = current_index

                    if step_callback:
                        step_callback({
                            "status": "plan_update",
                            "completed_indices": completed_indices,
                            "current_index": current_index,
                            "goal_achieved": goal_achieved
                        })

                    if goal_achieved:
                        if step_callback:
                            step_callback({"status": "completed", "message": "Goal fully achieved!"})
                        break

                    # ⑨ Emergency replan if stuck
                    if is_looping or needs_replan:
                        if step_callback:
                            step_callback({
                                "status": "replanning",
                                "message": f"Replanning: {val_reason}"
                            })
                        try:
                            recovery = active_llm.replan_from_state(
                                goal=goal,
                                history=state.history,
                                elements=val_elements,
                                screenshot_base64=val_screenshot
                            )
                            recovery_steps = recovery.get("recovery_steps", [])
                            if recovery_steps:
                                # Insert recovery steps right after current plan position
                                insert_at = min(state.current_plan_idx + 1, len(state.plan))
                                state.plan = (
                                    state.plan[:insert_at]
                                    + recovery_steps
                                    + state.plan[insert_at:]
                                )
                                if step_callback:
                                    step_callback({
                                        "status": "plan_updated",
                                        "plan": state.plan,
                                        "message": recovery.get("diagnosis", "Plan updated.")
                                    })
                        except Exception as replan_err:
                            print(f"Replan error: {replan_err}")

                except Exception as val_err:
                    print(f"Validation error: {val_err}")

            # ── END LOOP ───────────────────────────────────────────────────
            workflow_data = {
                "name": name,
                "goal": goal,
                "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "initial_package": initial_package,
                "steps": state.steps,
                "test_cases": []
            }
            self.save_workflow(name, workflow_data)
            return workflow_data

        finally:
            self.active_sessions.pop(session_id, None)
            self._intervention_events.pop(session_id, None)
            self._intervention_messages.pop(session_id, None)

    # -----------------------------------------------------------------------
    # Test case runner
    # -----------------------------------------------------------------------

    def run_test_cases(
        self,
        name: str,
        emulator: EmulatorManager,
        llm: LLMClient,
        step_callback: Callable | None = None
    ) -> list[dict]:
        """Run all test cases for a workflow against the current emulator state."""
        wf = self.load_workflow(name)
        test_cases = wf.get("test_cases", [])

        if not test_cases:
            return []

        results = []
        for tc in test_cases:
            if step_callback:
                step_callback({
                    "status": "test_running",
                    "test_id": tc["id"],
                    "test_name": tc.get("name", "")
                })

            try:
                screenshot_b64, elements = emulator.get_annotated_screenshot()
                check_type = tc.get("check_type", "llm_assert")

                if check_type == "element_present":
                    result = self._check_element_present(tc, elements, must_present=True)
                elif check_type == "element_not_present":
                    result = self._check_element_present(tc, elements, must_present=False)
                elif check_type == "element_text_contains":
                    result = self._check_element_text(tc, elements)
                else:  # llm_assert (default)
                    result = llm.evaluate_test_case(tc, elements, screenshot_b64)

                tc["status"] = "passed" if result.get("passed") else "failed"
                tc["last_result"] = result
                tc["last_run_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

                entry = {
                    "id": tc["id"],
                    "name": tc.get("name", ""),
                    "passed": result.get("passed", False),
                    "confidence": result.get("confidence", ""),
                    "reason": result.get("reason", ""),
                    "evidence": result.get("evidence", "")
                }
                results.append(entry)

                if step_callback:
                    step_callback({
                        "status": "test_result",
                        **entry
                    })

            except Exception as e:
                tc["status"] = "error"
                tc["last_result"] = {"passed": False, "reason": str(e)}
                entry = {
                    "id": tc["id"],
                    "name": tc.get("name", ""),
                    "passed": False,
                    "reason": f"Error: {e}"
                }
                results.append(entry)
                if step_callback:
                    step_callback({"status": "test_result", **entry})

        wf["test_cases"] = test_cases
        self.save_workflow(name, wf)

        if step_callback:
            passed = sum(1 for r in results if r.get("passed"))
            step_callback({
                "status": "tests_complete",
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed
            })

        return results

    # -----------------------------------------------------------------------
    # Deterministic test checks
    # -----------------------------------------------------------------------

    def _check_element_present(self, tc: dict, elements: list, must_present: bool) -> dict:
        selector = tc.get("selector", {})
        for el in elements:
            if self._selector_matches(selector, el):
                label = el.get("text") or el.get("content_desc") or "element"
                if must_present:
                    return {"passed": True, "confidence": "high", "reason": f"Element found: '{label}'", "evidence": label}
                else:
                    return {"passed": False, "confidence": "high", "reason": f"Element should not be present but was found: '{label}'", "evidence": label}
        if must_present:
            return {"passed": False, "confidence": "high", "reason": "Element not found on screen", "evidence": ""}
        return {"passed": True, "confidence": "high", "reason": "Element correctly absent from screen", "evidence": ""}

    def _check_element_text(self, tc: dict, elements: list) -> dict:
        selector = tc.get("selector", {})
        expected = tc.get("expected_value", "")
        for el in elements:
            if self._selector_matches(selector, el) and expected in (el.get("text") or ""):
                return {"passed": True, "confidence": "high", "reason": f"Element text contains '{expected}'", "evidence": el.get("text")}
        return {"passed": False, "confidence": "high", "reason": f"No element found containing text '{expected}'", "evidence": ""}

    def _selector_matches(self, selector: dict, el: dict) -> bool:
        if selector.get("resource_id") and selector["resource_id"] not in (el.get("resource_id") or ""):
            return False
        if selector.get("text") and selector["text"] not in (el.get("text") or ""):
            return False
        if selector.get("content_desc") and selector["content_desc"] not in (el.get("content_desc") or ""):
            return False
        return True

    # -----------------------------------------------------------------------
    # Element matching for playback
    # -----------------------------------------------------------------------

    def find_matching_element(self, selector: dict, current_elements: list[dict]) -> dict | None:
        """Finds the best matching element for a recorded selector."""
        best_match = None
        best_score = 0

        for el in current_elements:
            score = 0
            weight_total = 0

            if selector.get("resource_id"):
                weight_total += 5
                if el.get("resource_id") == selector["resource_id"]:
                    score += 5
            if selector.get("text"):
                weight_total += 4
                if el.get("text") == selector["text"]:
                    score += 4
            if selector.get("content_desc"):
                weight_total += 4
                if el.get("content_desc") == selector["content_desc"]:
                    score += 4
            if selector.get("class_name"):
                weight_total += 1
                if el.get("class_name") == selector["class_name"]:
                    score += 1

            if weight_total > 0 and score / weight_total >= 0.6 and score > best_score:
                best_score = score
                best_match = el

        return best_match

    # -----------------------------------------------------------------------
    # Reset emulator to initial state (for playback)
    # -----------------------------------------------------------------------

    def reset_to_initial_state(self, initial_package: str | None, emulator: EmulatorManager):
        if not initial_package:
            emulator.press_key("home")
            time.sleep(2.0)
            return

        is_launcher = any(k in initial_package for k in ["launcher", "trebuchet", "desktop", "carousellauncher", "com.android.systemui"])
        if is_launcher:
            emulator.press_key("home")
        else:
            try:
                emulator.stop_app(initial_package)
                time.sleep(1.0)
                emulator.launch_app(initial_package)
            except Exception:
                emulator.press_key("home")
        time.sleep(3.0)

    # -----------------------------------------------------------------------
    # Playback workflow
    # -----------------------------------------------------------------------

    def playback_workflow(
        self,
        name: str,
        emulator: EmulatorManager,
        step_callback: Callable | None = None,
        is_refining: bool = False
    ) -> bool:
        """
        Execute a recorded workflow.
        Resolves semantic selectors; uses LLM self-healing if an element is missing.
        """
        workflow = self.load_workflow(name)
        steps = workflow.get("steps", [])
        initial_package = workflow.get("initial_package")

        if step_callback:
            step_callback({"status": "starting", "message": f"Starting playback of workflow '{name}'"})

        if initial_package or is_refining:
            if step_callback:
                step_callback({"status": "starting", "message": "Resetting emulator to initial state..."})
            self.reset_to_initial_state(initial_package, emulator)

        steps_for_execution = list(steps)

        for idx, step in enumerate(steps_for_execution):
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
                if action in ["click", "input_text"] and selector:
                    matched_el = None
                    for _ in range(3):
                        elements = emulator.extract_elements()
                        matched_el = self.find_matching_element(selector, elements)
                        if matched_el:
                            break
                        time.sleep(1.0)

                    if not matched_el:
                        # Self-heal via LLM
                        passed = False
                        llm = self._get_default_llm()
                        for heal_attempt in range(3):
                            if step_callback:
                                step_callback({
                                    "status": "healing",
                                    "step": step_num,
                                    "message": f"Element not found. LLM Self-Healing attempt {heal_attempt + 1}/3..."
                                })

                            screenshot_b64, current_elements = emulator.get_annotated_screenshot()
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
                                    "message": f"LLM decided: {heal_action.upper()} ({heal_type}) — {heal_explanation}"
                                })

                            if heal_action == "skip":
                                passed = True
                                break

                            healed_el = None
                            if heal_action in ["click", "input_text"] and heal_target_id is not None:
                                healed_el = next(
                                    (el for el in current_elements if el.get("visual_id") == int(heal_target_id)), None
                                )
                                if not healed_el:
                                    time.sleep(1.0)
                                    continue
                                cx, cy = healed_el["center"]
                                if heal_action == "click":
                                    emulator.click(cx, cy)
                                else:
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
                                time.sleep(1.0)
                                continue

                            time.sleep(2.0)

                            if heal_type == "selector_update":
                                if is_refining and healed_el:
                                    for s in workflow["steps"]:
                                        if s is step:
                                            s["selector"] = self._selector_from_element(healed_el)
                                            break
                                    self.save_workflow(name, workflow)
                                    if step_callback:
                                        step_callback({
                                            "status": "healed",
                                            "step": step_num,
                                            "message": "Workflow self-healed (selector updated)."
                                        })
                                passed = True
                                break
                            else:
                                elements = emulator.extract_elements()
                                matched_el = self.find_matching_element(selector, elements)
                                if matched_el:
                                    cx, cy = matched_el["center"]
                                    if action == "click":
                                        emulator.click(cx, cy)
                                    else:
                                        emulator.click(cx, cy)
                                        time.sleep(0.5)
                                        emulator.input_text(value)
                                    if is_refining and healed_el:
                                        recovery_step = {
                                            "step_number": idx + 1,
                                            "action": heal_action,
                                            "selector": self._selector_from_element(healed_el) if healed_el else None,
                                            "value": heal_value,
                                            "description": f"Recovery: {heal_explanation}"
                                        }
                                        target_idx = next((i for i, s in enumerate(workflow["steps"]) if s is step), -1)
                                        if target_idx != -1:
                                            workflow["steps"].insert(target_idx, recovery_step)
                                            for i, s in enumerate(workflow["steps"]):
                                                s["step_number"] = i + 1
                                            self.save_workflow(name, workflow)
                                    passed = True
                                    if step_callback:
                                        step_callback({
                                            "status": "success",
                                            "step": step_num,
                                            "message": "Step executed after recovery."
                                        })
                                    time.sleep(2.0)
                                    break

                        if not passed:
                            if step_callback:
                                step_callback({
                                    "status": "failed",
                                    "step": step_num,
                                    "message": f"Step {step_num} failed after all healing attempts. Skipping."
                                })
                            continue
                    else:
                        cx, cy = matched_el["center"]
                        if action == "click":
                            emulator.click(cx, cy)
                        else:
                            emulator.click(cx, cy)
                            time.sleep(0.5)
                            emulator.input_text(value)

                elif action == "press_key":
                    emulator.press_key(value)

                elif action == "open_app":
                    emulator.launch_app_by_name(value or "")

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

                time.sleep(2.0)

            except Exception as e:
                if step_callback:
                    step_callback({"status": "failed", "step": step_num, "message": str(e)})
                print(f"Playback error at step {step_num}: {e}")
                continue

        if step_callback:
            step_callback({"status": "completed", "message": "Playback completed."})
        return True

    # -----------------------------------------------------------------------
    # Helper: get a default LLM client for self-healing during playback
    # -----------------------------------------------------------------------

    def _get_default_llm(self) -> LLMClient:
        if settings.gemini_api_key:
            return LLMClient(provider="gemini", api_key=settings.gemini_api_key)
        if settings.openai_api_key:
            return LLMClient(provider="openai", api_key=settings.openai_api_key)
        if settings.anthropic_api_key:
            return LLMClient(provider="anthropic", api_key=settings.anthropic_api_key)
        return LLMClient(provider="local")
