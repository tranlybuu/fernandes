# US-prompt-updates Enhance Backend System Prompts and Input Clearing

## Status

implemented

## Lane

normal

## Product Contract

The system prompts for next action generation and script healing must incorporate browser-use best practices (popup handling, text input clearing, query submission, autocomplete handling, loop detection) and the emulator must automatically clear text fields before input.

## Relevant Product Docs

- `docs/ARCHITECTURE.md`

## Acceptance Criteria

- [x] Convert all `.txt` system prompts in the backend to markdown `.md` files.
- [x] Update `get_next_action.md` to instruct the agent to clear text inputs, submit queries, handle autocomplete dropdowns, manage overlays/popups, and avoid loops.
- [x] Update `heal_step.md` to include script healing-specific guidelines for input clearing, search submission, autocomplete, popup recovery, and loop avoidance.
- [x] Update `llm_client.py` to correctly load the new `.md` files.
- [x] Modify `emulator.py` to automatically call `self.d.clear_text()` before `self.d.send_keys(text)` in the `input_text` function to ensure programmatic clearing.
- [x] Verify backend server starts up and runs without syntax/import errors.

## Design Notes

- **Prompts**: `backend/app/prompts/` now contains `.md` files.
- **LLM Client**: `backend/app/llm_client.py` loads `.md` prompt templates instead of `.txt`.
- **Emulator Manager**: `backend/app/emulator.py` calls `clear_text()` on the uiautomator2 device instance.

## Validation

| Layer | Expected proof | Status |
| --- | --- | --- |
| Unit | No unit tests exist | N/A |
| Integration | Verify FastAPI backend runs | passed |
| E2E | Manual verification of prompt loads | passed |
| Platform | N/A | N/A |
| Release | N/A | N/A |

## Harness Delta

- Updated backend system prompts from `.txt` to `.md` format and enhanced them with advanced agent instructions.

## Evidence

Completed successfully. Verified that the backend service starts and the prompts are loaded correctly.
