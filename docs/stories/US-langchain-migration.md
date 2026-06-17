# US-langchain-migration Migrate LLM Client to Langchain and Fix Startup Loading Issues

## Status

implemented

## Lane

normal

## Product Contract

1. The backend LLM client must migrate from direct provider SDKs (OpenAI, Google Generative AI, Anthropic) to unified Langchain chat models (`ChatOpenAI`, `ChatGoogleGenerativeAI`, `ChatAnthropic`) for consistency.
2. The Gemini provider must communicate via REST HTTP (`transport="rest"`) instead of gRPC to prevent POSIX `fork()` deadlock warnings/issues.
3. The server must load devices and workflows immediately on startup without hanging or timing out.

## Relevant Product Docs

- `docs/ARCHITECTURE.md`

## Acceptance Criteria

- [x] Add `langchain-core`, `langchain-openai`, `langchain-google-genai`, and `langchain-anthropic` to `backend/requirements.txt`.
- [x] Migrate `backend/app/llm_client.py` to use Langchain chat models and unify the ReAct action and validation dispatch calls.
- [x] Modify the `/api/models` endpoint for Gemini in `backend/app/main.py` to call Google's REST API directly rather than using `google.generativeai` package, eliminating gRPC from backend server threads.
- [x] Verify that devices and workflows load immediately on the frontend Dashboard upon server startup.
- [x] Verify that workflow recording, playback, and test cases function properly using the new Langchain-based client.

## Design Notes

- **LLM Client**: `backend/app/llm_client.py` uses `ChatOpenAI` (OpenAI/Local), `ChatGoogleGenerativeAI` (Gemini with REST transport), and `ChatAnthropic` (Anthropic).
- **Models Endpoint**: `backend/app/main.py` lists Gemini models using a direct `requests.get` call to the `generativelanguage.googleapis.com` HTTP API.
- **List-type Responses**: Handles case where model output is returned as list of dicts (e.g. from newer Gemini/Langchain formats) by converting it to string in `_clean_json`.

## Validation

| Layer | Expected proof | Status |
| --- | --- | --- |
| Unit | No unit tests exist | N/A |
| Integration | Verify FastAPI backend starts up successfully | passed |
| E2E | Verify device/workflow lists load immediately and recording/playback works | passed |
| Platform | N/A | N/A |
| Release | N/A | N/A |

## Harness Delta

- Added Langchain dependencies to backend requirements.
- Documented LLM migration and startup deadlock resolution.

## Evidence

- Verified backend starts successfully and handles requests immediately.
- Verified `/api/devices`, `/api/workflows`, and `/api/models?provider=gemini` load immediately without hanging or deadlock warnings.
- Executed scratch script testing Langchain client model invocation successfully.
- Resolved and verified `'list' object has no attribute 'strip'` exception by supporting list-type content blocks in JSON cleaner.
- Suppressed `Unexpected argument 'transport'` warning by passing it via `model_kwargs`.
- Suppressed verbose `Unexpected ASGI message` RuntimeError logs when client disconnects from the live view WebSocket.
- Prevented WebSocket main thread deadlocks by loading `EmulatorManager` with `auto_connect=False` and running connection asynchronously.
- Improved live view loop by breaking immediately when the client disconnects (`WebSocketState.DISCONNECTED`).

