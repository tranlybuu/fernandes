import json
import base64
import requests
from openai import OpenAI
import google.generativeai as genai
import anthropic
from .config import settings

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
        screenshot_base64: str | None = None
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

        system_prompt = (
            "You are an AI assistant that controls an Android Emulator to achieve a user's goal.\n"
            "You will look at the current screen elements (and visual screenshot if available) and decide the next action.\n\n"
            "Here is the list of interactive elements currently visible on the screen:\n"
            f"{elements_str}\n"
            "Your available actions are:\n"
            "1. click: Taps on an element. Specify `target_id` matching the element ID above.\n"
            "2. input_text: Enters text into an element. Specify `target_id` (the input field) and `value` (the text string).\n"
            "3. press_key: Presses an Android system key. Specify `value` as 'enter', 'back', 'home', etc. (`target_id` is null).\n"
            "4. swipe: Swipes the screen. Specify `value` as 'up', 'down', 'left', or 'right' (`target_id` is null).\n"
            "5. stop: You have completed the goal. (`target_id` and `value` are null).\n\n"
            "IMPORTANT Rules:\n"
            "- Only click elements that exist in the list. If you need to click, choose the correct ID.\n"
            "- If an input field is selected, remember to type and then possibly click search/enter.\n"
            "- Respond strictly in JSON format. Do not write anything outside the JSON block.\n\n"
            "JSON Format:\n"
            "{\n"
            "  \"thought\": \"Briefly explain your reasoning and what you see on the screen\",\n"
            "  \"action\": \"click\" | \"input_text\" | \"press_key\" | \"swipe\" | \"stop\",\n"
            "  \"target_id\": <integer_id_or_null>,\n"
            "  \"value\": \"<text_to_input_or_key_or_direction_or_null>\",\n"
            "  \"explanation\": \"Short description of the action taken (e.g. 'Click search button')\"\n"
            "}"
        )

        user_content = f"Goal: {goal}\n\nPrevious Steps Executed:\n{history_str or 'None'}\n\nDecide the next action."

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

        system_prompt = (
            "You are an AI assistant that heals automated playback scripts on Android.\n"
            "We are executing a saved workflow, but the expected element for the current step could not be found.\n"
            "You must look at the current screen elements (and screenshot if available) and decide the best action to recover and continue towards the goal.\n\n"
            "Here is the list of interactive elements currently visible on the screen:\n"
            f"{elements_str}\n"
            "Your available actions are:\n"
            "1. click: Taps on an element. Specify `target_id`.\n"
            "2. input_text: Enters text. Specify `target_id` and `value`.\n"
            "3. press_key: Presses key (e.g. 'back', 'home', 'enter'). Specify `value`.\n"
            "4. swipe: Swipes 'up', 'down', 'left', or 'right'. Specify `value`.\n"
            "5. skip: The step is no longer needed (e.g. popup didn't show up, or we are already past it). (`target_id` and `value` are null).\n\n"
            "Rules:\n"
            "- If you see that the expected button has a slightly different text, ID, or position, select it by returning the new `target_id`.\n"
            "- If the screen has already updated or the step was a dismissal of a popup that didn't appear, return 'skip'.\n"
            "- Respond strictly in JSON format.\n\n"
            "JSON Format:\n"
            "{\n"
            "  \"thought\": \"Reasoning about what changed and what to do next\",\n"
            "  \"action\": \"click\" | \"input_text\" | \"press_key\" | \"swipe\" | \"skip\",\n"
            "  \"target_id\": <integer_id_or_null>,\n"
            "  \"value\": \"<text_or_key_or_direction_or_null>\",\n"
            "  \"explanation\": \"Short description of the recovery action\"\n"
            "}"
        )

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

