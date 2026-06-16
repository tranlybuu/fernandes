import json
import base64
import requests
from openai import OpenAI
import google.generativeai as genai
import anthropic
from .config import settings
import os

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

        # Initialize clients based on provider
        if self.provider == "openai":
            self.client = OpenAI(api_key=api_key or settings.openai_api_key)
            self.model = model or "gpt-4o-mini"
        elif self.provider == "gemini":
            key = api_key or settings.gemini_api_key
            if key:
                genai.configure(api_key=key)
            self.model = model or "gemini-3.1-flash-lite"
        elif self.provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)
            self.model = model or "claude-3-5-sonnet-20241022"
        elif self.provider in ["local", "ollama", "vllm"]:
            self.client = OpenAI(
                base_url=base_url or settings.local_llm_url,
                api_key="none"  # Not needed for local APIs
            )
            self.model = model or settings.local_llm_model
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def get_next_action(
        self,
        goal: str,
        history: list[dict],
        elements: list[dict],
        screenshot_base64: str | None = None,
        plan: list[str] | None = None
    ) -> dict:
        """
        Sends the UI elements, screenshot, and current state to the LLM.
        Returns the parsed action dictionary.
        """
        # Format the elements for the LLM
        elements_str = ""
        for el in elements:
            el_desc = f"ID: {el.get('visual_id', el.get('id'))} | Class: {el['class_name']}"
            if el['text']:
                el_desc += f" | Text: '{el['text']}'"
            if el['content_desc']:
                el_desc += f" | Desc: '{el['content_desc']}'"
            if el['resource_id']:
                el_desc += f" | ResourceId: '{el['resource_id']}'"
            el_desc += f" | Clickable: {el['clickable']}"
            elements_str += el_desc + "\n"

        history_str = ""
        for idx, h in enumerate(history):
            history_str += f"Step {idx+1}: Action: {h['action']} on element: {h.get('description', '')} -> Result description: {h.get('result_desc', 'done')}\n"

        system_prompt = load_prompt("get_next_action.md").replace("__ELEMENTS_STR__", elements_str)

        plan_str = ""
        if plan:
            plan_str = "\nHigh-Level Plan to follow:\n"
            for i, p in enumerate(plan):
                plan_str += f"{i}. {p}\n"

        user_content = f"Goal: {goal}\n"
        if plan_str:
            user_content += plan_str
        user_content += f"\nPrevious Steps Executed:\n{history_str or 'None'}\n\nDecide the next action."

        try:
            if self.provider == "gemini":
                return self._call_gemini(system_prompt, user_content, screenshot_base64)
            elif self.provider == "openai":
                return self._call_openai(system_prompt, user_content, screenshot_base64)
            elif self.provider == "anthropic":
                return self._call_anthropic(system_prompt, user_content, screenshot_base64)
            else: # Local / Ollama / vLLM (using OpenAI API compatible format)
                # Local LLMs might not have vision or might fail with images.
                # If screenshot is provided and model supports vision, use vision. Else fall back to text.
                return self._call_openai(system_prompt, user_content, screenshot_base64)
        except Exception as e:
            print(f"LLM API Call failed: {e}")
            # Fallback action
            return {
                "thought": f"An error occurred: {e}. Stopping execution.",
                "action": "stop",
                "target_id": None,
                "value": None,
                "explanation": "Error fallback stop"
            }

    def _clean_json(self, text: str) -> dict:
        """Cleans LLM response and parses it into JSON."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try finding JSON block using regex if parsing failed
            import re
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            raise Exception(f"Failed to parse JSON from response: {text}")

    def _call_openai(self, system_prompt: str, user_content: str, screenshot_base64: str | None) -> dict:
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        if screenshot_base64 and "gpt" in self.model:
            # Multimodal messages format
            user_msg_content = [
                {"type": "text", "text": user_content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_base64}"
                    }
                }
            ]
            messages.append({"role": "user", "content": user_msg_content})
        else:
            messages.append({"role": "user", "content": user_content})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"} if "gpt" in self.model else None,
            temperature=0.1
        )
        return self._clean_json(response.choices[0].message.content)

    def _call_gemini(self, system_prompt: str, user_content: str, screenshot_base64: str | None) -> dict:
        # For Gemini SDK, we use generative models
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_prompt,
            generation_config={"response_mime_type": "application/json"}
        )

        contents = []
        if screenshot_base64:
            image_data = base64.b64decode(screenshot_base64)
            contents.append({
                "mime_type": "image/png",
                "data": image_data
            })
        
        contents.append(user_content)
        response = model.generate_content(contents)
        return self._clean_json(response.text)

    def _call_anthropic(self, system_prompt: str, user_content: str, screenshot_base64: str | None) -> dict:
        content = []
        if screenshot_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot_base64
                }
            })
        
        content.append({
            "type": "text",
            "text": user_content
        })

        response = self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=[
                {"role": "user", "content": content}
            ],
            max_tokens=1000,
            temperature=0.1
        )
        return self._clean_json(response.content[0].text)

    def heal_step(
        self,
        goal: str,
        failed_step: dict,
        elements: list[dict],
        screenshot_base64: str | None = None
    ) -> dict:
        """
        Asks the LLM to heal a failed playback step.
        """
        # Format current elements for the LLM
        elements_str = ""
        for el in elements:
            el_desc = f"ID: {el.get('visual_id', el.get('id'))} | Class: {el['class_name']}"
            if el['text']:
                el_desc += f" | Text: '{el['text']}'"
            if el['content_desc']:
                el_desc += f" | Desc: '{el['content_desc']}'"
            if el['resource_id']:
                el_desc += f" | ResourceId: '{el['resource_id']}'"
            el_desc += f" | Clickable: {el['clickable']}"
            elements_str += el_desc + "\n"

        system_prompt = load_prompt("heal_step.md").replace("__ELEMENTS_STR__", elements_str)

        user_content = (
            f"Original Goal: {goal}\n\n"
            f"Failed Step Details:\n"
            f"- Step Number: {failed_step.get('step_number')}\n"
            f"- Action: {failed_step.get('action')}\n"
            f"- Description: {failed_step.get('description')}\n"
            f"- Expected Selector: {json.dumps(failed_step.get('selector', {}))}\n"
            f"- Expected Value: {failed_step.get('value')}\n\n"
            f"Please decide the recovery action."
        )

        try:
            if self.provider == "gemini":
                return self._call_gemini(system_prompt, user_content, screenshot_base64)
            elif self.provider == "openai":
                return self._call_openai(system_prompt, user_content, screenshot_base64)
            elif self.provider == "anthropic":
                return self._call_anthropic(system_prompt, user_content, screenshot_base64)
            else:
                return self._call_openai(system_prompt, user_content, screenshot_base64)
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
        """
        Asks the LLM to evaluate the recorded workflow and decide if we need 
        1 or 2 runs to verify/refine it.
        Returns the number of runs (1 or 2).
        """
        steps_str = json.dumps(steps, indent=2)
        system_prompt = load_prompt("assess_refinement.md")
        user_content = f"Goal: {goal}\n\nSteps:\n{steps_str}"
        try:
            if self.provider == "gemini":
                res = self._call_gemini(system_prompt, user_content, None)
            elif self.provider == "openai":
                res = self._call_openai(system_prompt, user_content, None)
            elif self.provider == "anthropic":
                res = self._call_anthropic(system_prompt, user_content, None)
            else:
                res = self._call_openai(system_prompt, user_content, None)
            
            runs = int(res.get("runs", 1))
            if runs not in [1, 2]:
                runs = 1
            return runs
        except Exception as e:
            print(f"Refinement assessment failed: {e}")
            return 1

    def generate_initial_plan(self, goal: str, custom_prompt: str | None = None) -> list[str]:
        """Generates an initial high-level plan (checklist) to achieve the goal."""
        system_prompt = custom_prompt if custom_prompt is not None else load_prompt("generate_plan.md")
        user_content = f"Goal: {goal}"
        try:
            if self.provider == "gemini":
                res = self._call_gemini(system_prompt, user_content, None)
            elif self.provider == "openai":
                res = self._call_openai(system_prompt, user_content, None)
            elif self.provider == "anthropic":
                res = self._call_anthropic(system_prompt, user_content, None)
            else:
                res = self._call_openai(system_prompt, user_content, None)
            
            plan = res.get("plan", [])
            if not isinstance(plan, list):
                plan = [goal]
            return plan
        except Exception as e:
            print(f"Plan generation failed: {e}")
            return [goal]

    def validate_step_progress(
        self,
        goal: str,
        plan: list[str],
        history: list[dict],
        elements: list[dict],
        screenshot_base64: str | None = None
    ) -> dict:
        """
        Validates progress against the plan after a step is executed.
        Returns which plan steps are completed, the current active plan step, and if the overall goal is achieved.
        """
        elements_str = ""
        for el in elements:
            el_desc = f"ID: {el.get('visual_id', el.get('id'))} | Class: {el['class_name']}"
            if el['text']:
                el_desc += f" | Text: '{el['text']}'"
            if el['content_desc']:
                el_desc += f" | Desc: '{el['content_desc']}'"
            el_desc += f" | Clickable: {el['clickable']}"
            elements_str += el_desc + "\n"

        history_str = ""
        for idx, h in enumerate(history):
            history_str += f"Step {idx+1}: Action: {h['action']} -> {h.get('description', '')}\n"

        plan_str = ""
        for idx, item in enumerate(plan):
            plan_str += f"{idx}: {item}\n"

        system_prompt = load_prompt("validate_progress.md").replace("__ELEMENTS_STR__", elements_str)

        user_content = (
            f"Goal: {goal}\n\n"
            f"Plan:\n{plan_str}\n\n"
            f"Execution History:\n{history_str or 'None'}\n\n"
            "Assess the progress."
        )

        try:
            if self.provider == "gemini":
                return self._call_gemini(system_prompt, user_content, screenshot_base64)
            elif self.provider == "openai":
                return self._call_openai(system_prompt, user_content, screenshot_base64)
            elif self.provider == "anthropic":
                return self._call_anthropic(system_prompt, user_content, screenshot_base64)
            else:
                return self._call_openai(system_prompt, user_content, screenshot_base64)
        except Exception as e:
            print(f"Progress validation failed: {e}")
            return {
                "completed_indices": [],
                "current_index": 0,
                "goal_achieved": False
            }

    def refine_plan(
        self,
        goal: str,
        current_plan: list[str],
        feedback: str,
        custom_prompt: str | None = None
    ) -> dict:
        """Refines the current plan based on user feedback."""
        system_prompt = custom_prompt if custom_prompt is not None else load_prompt("refine_plan.md")
        
        plan_str = "\n".join([f"- {item}" for item in current_plan])
        user_content = (
            f"Goal: {goal}\n\n"
            f"Current Plan:\n{plan_str}\n\n"
            f"User Feedback: {feedback}"
        )
        
        try:
            if self.provider == "gemini":
                res = self._call_gemini(system_prompt, user_content, None)
            elif self.provider == "openai":
                res = self._call_openai(system_prompt, user_content, None)
            elif self.provider == "anthropic":
                res = self._call_anthropic(system_prompt, user_content, None)
            else:
                res = self._call_openai(system_prompt, user_content, None)
            
            plan = res.get("plan", current_plan)
            response = res.get("response", "I have updated the plan according to your feedback.")
            return {"plan": plan, "response": response}
        except Exception as e:
            print(f"Plan refinement failed: {e}")
            return {
                "plan": current_plan,
                "response": f"Failed to refine plan: {e}"
            }

