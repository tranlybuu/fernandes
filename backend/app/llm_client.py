import json
import base64
import requests
from .config import settings
import os

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

def load_prompt(filename: str) -> str:
    prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
    filepath = os.path.join(prompts_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


class LLMClient:
    def __init__(
        self,
        provider: str,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

        if self.provider == "openai":
            model_to_use = self.model or "gpt-4o-mini"
            self.llm = ChatOpenAI(
                model=model_to_use,
                api_key=api_key or settings.openai_api_key,
                temperature=0.1,
                timeout=30.0,
                model_kwargs={"response_format": {"type": "json_object"}} if "gpt" in model_to_use else {}
            )
            self.model = model_to_use
        elif self.provider == "gemini":
            model_to_use = self.model or "gemini-2.5-flash"
            self.llm = ChatGoogleGenerativeAI(
                model=model_to_use,
                api_key=api_key or settings.gemini_api_key,
                temperature=0.1,
                timeout=30.0,
                response_mime_type="application/json",
                model_kwargs={"transport": "rest"}
            )
            self.model = model_to_use
        elif self.provider == "anthropic":
            model_to_use = self.model or "claude-3-5-sonnet-20241022"
            self.llm = ChatAnthropic(
                model=model_to_use,
                api_key=api_key or settings.anthropic_api_key,
                temperature=0.1,
                timeout=30.0,
                max_tokens=2000
            )
            self.model = model_to_use
        elif self.provider in ["local", "ollama", "vllm"]:
            model_to_use = self.model or settings.local_llm_model
            self.llm = ChatOpenAI(
                model=model_to_use,
                base_url=base_url or settings.local_llm_url,
                api_key="none",
                temperature=0.1,
                timeout=30.0
            )
            self.model = model_to_use
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    # ─────────────────────────────────────────────────────────────────────
    # Core LLM dispatch helpers
    # ─────────────────────────────────────────────────────────────────────

    def _clean_json(self, text) -> dict:
        """Cleans LLM response and parses it into JSON."""
        if not isinstance(text, str):
            if isinstance(text, list):
                extracted = []
                for item in text:
                    if isinstance(item, dict):
                        if "text" in item:
                            extracted.append(item["text"])
                    elif isinstance(item, str):
                        extracted.append(item)
                text = "".join(extracted)
            else:
                text = str(text)

        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            raise Exception(f"Failed to parse JSON from LLM response: {text[:200]}")

    def _dispatch(self, system_prompt: str, user_content: str, screenshot_base64: str | None = None) -> dict:
        """Route to the langchain model."""
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = [
            SystemMessage(content=system_prompt)
        ]
        
        if screenshot_base64:
            user_msg_content = [
                {"type": "text", "text": user_content},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}
                }
            ]
            messages.append(HumanMessage(content=user_msg_content))
        else:
            messages.append(HumanMessage(content=user_content))
            
        response = self.llm.invoke(messages)
        return self._clean_json(response.content)

    # ─────────────────────────────────────────────────────────────────────
    # Helper: format elements list for prompts
    # ─────────────────────────────────────────────────────────────────────

    def _format_elements(self, elements: list[dict]) -> str:
        elements_str = ""
        for el in elements:
            el_desc = f"ID: {el.get('visual_id', el.get('id'))} | Class: {el['class_name']}"
            if el.get("text"):
                el_desc += f" | Text: '{el['text']}'"
            if el.get("content_desc"):
                el_desc += f" | Desc: '{el['content_desc']}'"
            if el.get("resource_id"):
                el_desc += f" | ResourceId: '{el['resource_id']}'"
            el_desc += f" | Clickable: {el.get('clickable', False)}"
            elements_str += el_desc + "\n"
        return elements_str

    def _format_plan(self, plan: list) -> str:
        plan_str = ""
        for i, step in enumerate(plan):
            if isinstance(step, dict):
                plan_str += f"{i}. [CONDITIONAL] {step.get('description', '')}\n"
                plan_str += f"   If: {step.get('condition', '')}\n"
                plan_str += f"   Then: {step.get('on_true', 'skip')}\n"
                plan_str += f"   Else: {step.get('on_false', 'skip')}\n"
            else:
                plan_str += f"{i}. {step}\n"
        return plan_str

    def _format_history(self, history: list[dict]) -> str:
        history_str = ""
        for idx, h in enumerate(history):
            action = h.get("action", "unknown")
            desc = h.get("description", "")
            result = h.get("result_desc", "done")
            evaluation = h.get("evaluation", "")
            if action == "user_intervention":
                history_str += f"[USER INSTRUCTION] {desc}\n"
            else:
                history_str += f"Step {idx+1}: {action.upper()} - {desc} → {result}"
                if evaluation:
                    history_str += f" | Eval: {evaluation}"
                history_str += "\n"
        return history_str

    # ─────────────────────────────────────────────────────────────────────
    # Main agent action (ReAct loop)
    # ─────────────────────────────────────────────────────────────────────

    def get_next_action(
        self,
        goal: str,
        history: list[dict],
        elements: list[dict],
        screenshot_base64: str | None = None,
        plan: list | None = None,
        current_plan_idx: int = 0,
        memory: str = "",
        intervention: str | None = None
    ) -> dict:
        """
        ReAct loop: Think → Act.
        Returns structured JSON with evaluation, memory, next_goal, and action fields.
        """
        elements_str = self._format_elements(elements)
        system_prompt = load_prompt("get_next_action.md").replace("__ELEMENTS_STR__", elements_str)

        # Build user message
        user_content = f"Goal: {goal}\n"

        if plan:
            plan_str = self._format_plan(plan)
            user_content += f"\nHigh-Level Plan:\n{plan_str}"
            user_content += f"\nCurrently working on step index: {current_plan_idx}\n"

        if memory:
            user_content += f"\nAgent Memory (persistent context):\n{memory}\n"

        if intervention:
            user_content += f"\n⚠️ USER INSTRUCTION (follow immediately): {intervention}\n"

        history_str = self._format_history(history)
        user_content += f"\nExecution History:\n{history_str or 'No actions taken yet.'}\n"
        user_content += "\nAnalyze the screen and decide the next action."

        try:
            return self._dispatch(system_prompt, user_content, screenshot_base64)
        except Exception as e:
            print(f"LLM get_next_action failed: {e}")
            return {
                "evaluation_previous_goal": f"LLM error: {e}",
                "memory": memory,
                "next_goal": "Stop due to error",
                "action": "needs_intervention",
                "target_id": None,
                "value": None,
                "explanation": f"LLM API error: {e}"
            }

    # ─────────────────────────────────────────────────────────────────────
    # Emergency replan
    # ─────────────────────────────────────────────────────────────────────

    def replan_from_state(
        self,
        goal: str,
        history: list[dict],
        elements: list[dict],
        screenshot_base64: str | None = None
    ) -> dict:
        """
        Emergency replan when the agent is stuck or on the wrong screen.
        Returns: {diagnosis: str, recovery_steps: list[str]}
        """
        elements_str = self._format_elements(elements)
        system_prompt = load_prompt("replan.md")
        history_str = self._format_history(history)

        user_content = (
            f"Original Goal: {goal}\n\n"
            f"Execution History (recent actions):\n{history_str or 'No actions yet.'}\n\n"
            f"Current Screen Elements:\n{elements_str}\n\n"
            "The agent is stuck. Generate recovery steps to get back on track."
        )

        try:
            result = self._dispatch(system_prompt, user_content, screenshot_base64)
            if not isinstance(result.get("recovery_steps"), list):
                result["recovery_steps"] = [goal]
            return result
        except Exception as e:
            print(f"Replan failed: {e}")
            return {
                "diagnosis": f"Replan LLM call failed: {e}",
                "recovery_steps": ["Press home button", "Continue with the original goal"]
            }

    # ─────────────────────────────────────────────────────────────────────
    # Step progress validation
    # ─────────────────────────────────────────────────────────────────────

    def validate_step_progress(
        self,
        goal: str,
        plan: list,
        history: list[dict],
        elements: list[dict],
        screenshot_base64: str | None = None
    ) -> dict:
        """
        Validates progress after a step is executed.
        Returns: {completed_indices, current_index, goal_achieved, is_looping, needs_replan, reason}
        """
        elements_str = self._format_elements(elements)
        system_prompt = load_prompt("validate_progress.md").replace("__ELEMENTS_STR__", elements_str)

        plan_str = self._format_plan(plan)
        history_str = self._format_history(history)

        user_content = (
            f"Goal: {goal}\n\n"
            f"Plan:\n{plan_str}\n\n"
            f"Execution History:\n{history_str or 'None'}\n\n"
            "Assess the current progress."
        )

        try:
            return self._dispatch(system_prompt, user_content, screenshot_base64)
        except Exception as e:
            print(f"Progress validation failed: {e}")
            return {
                "completed_indices": [],
                "current_index": 0,
                "goal_achieved": False,
                "is_looping": False,
                "needs_replan": False,
                "reason": f"Validation error: {e}"
            }

    # ─────────────────────────────────────────────────────────────────────
    # Test case evaluation
    # ─────────────────────────────────────────────────────────────────────

    def evaluate_test_case(
        self,
        test_case: dict,
        elements: list[dict],
        screenshot_base64: str | None = None
    ) -> dict:
        """
        Evaluates a test case assertion against current screen state.
        Returns: {passed: bool, confidence: str, reason: str, evidence: str}
        """
        elements_str = self._format_elements(elements)
        system_prompt = load_prompt("evaluate_test_case.md").replace("__ELEMENTS_STR__", elements_str)

        user_content = (
            f"Test Case Name: {test_case.get('name', 'Unnamed')}\n"
            f"Assertion to evaluate: {test_case.get('description', '')}\n\n"
            "Does the current screen satisfy this assertion? Evaluate carefully."
        )

        try:
            result = self._dispatch(system_prompt, user_content, screenshot_base64)
            if "passed" not in result:
                result["passed"] = False
            return result
        except Exception as e:
            print(f"Test case evaluation failed: {e}")
            return {
                "passed": False,
                "confidence": "low",
                "reason": f"Evaluation error: {e}",
                "evidence": ""
            }

    # ─────────────────────────────────────────────────────────────────────
    # Plan generation
    # ─────────────────────────────────────────────────────────────────────

    def generate_initial_plan(self, goal: str, custom_prompt: str | None = None) -> list:
        """Generates an initial high-level plan (with optional conditional steps)."""
        system_prompt = custom_prompt if custom_prompt is not None else load_prompt("generate_plan.md")
        user_content = f"Goal: {goal}"
        try:
            res = self._dispatch(system_prompt, user_content)
            plan = res.get("plan", [])
            if not isinstance(plan, list):
                plan = [goal]
            return plan
        except Exception as e:
            print(f"Plan generation failed: {e}")
            return [goal]

    def refine_plan(
        self,
        goal: str,
        current_plan: list,
        feedback: str,
        custom_prompt: str | None = None
    ) -> dict:
        """Refines the current plan based on user feedback."""
        system_prompt = custom_prompt if custom_prompt is not None else load_prompt("refine_plan.md")
        plan_str = "\n".join([
            f"- {step if isinstance(step, str) else step.get('description', str(step))}"
            for step in current_plan
        ])
        user_content = (
            f"Goal: {goal}\n\n"
            f"Current Plan:\n{plan_str}\n\n"
            f"User Feedback: {feedback}"
        )
        try:
            res = self._dispatch(system_prompt, user_content)
            return {
                "plan": res.get("plan", current_plan),
                "response": res.get("response", "Plan updated.")
            }
        except Exception as e:
            print(f"Plan refinement failed: {e}")
            return {"plan": current_plan, "response": f"Failed to refine plan: {e}"}

    # ─────────────────────────────────────────────────────────────────────
    # Self-healing for playback
    # ─────────────────────────────────────────────────────────────────────

    def heal_step(
        self,
        goal: str,
        failed_step: dict,
        elements: list[dict],
        screenshot_base64: str | None = None
    ) -> dict:
        """Asks the LLM to heal a failed playback step."""
        elements_str = self._format_elements(elements)
        system_prompt = load_prompt("heal_step.md").replace("__ELEMENTS_STR__", elements_str)

        user_content = (
            f"Original Goal: {goal}\n\n"
            f"Failed Step Details:\n"
            f"- Step Number: {failed_step.get('step_number')}\n"
            f"- Action: {failed_step.get('action')}\n"
            f"- Description: {failed_step.get('description')}\n"
            f"- Expected Selector: {json.dumps(failed_step.get('selector', {}))}\n"
            f"- Expected Value: {failed_step.get('value')}\n\n"
            "Please decide the recovery action."
        )

        try:
            return self._dispatch(system_prompt, user_content, screenshot_base64)
        except Exception as e:
            print(f"Self-healing LLM call failed: {e}")
            return {
                "thought": f"Self-healing failed: {e}.",
                "action": "skip",
                "target_id": None,
                "value": None,
                "explanation": "Error fallback skip"
            }

    def assess_refinement_runs(self, goal: str, steps: list[dict]) -> int:
        """Evaluates the recorded workflow to decide if 1 or 2 refinement runs are needed."""
        steps_str = json.dumps(steps, indent=2)
        system_prompt = load_prompt("assess_refinement.md")
        user_content = f"Goal: {goal}\n\nSteps:\n{steps_str}"
        try:
            res = self._dispatch(system_prompt, user_content)
            runs = int(res.get("runs", 1))
            if runs not in [1, 2]:
                runs = 1
            return runs
        except Exception as e:
            print(f"Refinement assessment failed: {e}")
            return 1
