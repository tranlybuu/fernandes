from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio
import os

from .config import settings
from .emulator import EmulatorManager
from .llm_client import LLMClient
from .workflow_engine import WorkflowEngine

from .mcp_server import mcp
from contextlib import asynccontextmanager

mcp_http_app = mcp.streamable_http_app()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="Fernandes — Android Automation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", mcp.sse_app())

engine = WorkflowEngine()

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class RecordRequest(BaseModel):
    workflow_name: str
    goal: str
    device_serial: str
    llm_provider: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    max_steps: int = 25
    plan: list | None = None

class PlaybackRequest(BaseModel):
    workflow_name: str
    device_serial: str

class DirectActionRequest(BaseModel):
    device_serial: str
    action: str
    x: int | None = None
    y: int | None = None
    value: str | None = None

class SettingsRequest(BaseModel):
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    local_llm_url: str | None = None
    local_llm_model: str | None = None

class StopRequest(BaseModel):
    device_serial: str

class UpdateWorkflowRequest(BaseModel):
    goal: str | None = None
    steps: list[dict] | None = None
    initial_package: str | None = None

class ActiveLLMRequest(BaseModel):
    llm_provider: str
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None


class PlanGenerateRequest(BaseModel):
    goal: str
    llm_provider: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    prompt: str | None = None

class PlanRefineRequest(BaseModel):
    goal: str
    current_plan: list
    feedback: str
    llm_provider: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    prompt: str | None = None

class InterventionRequest(BaseModel):
    message: str

class TestCaseRequest(BaseModel):
    name: str
    description: str                           # Natural language assertion
    check_type: str = "llm_assert"             # llm_assert | element_present | element_not_present | element_text_contains
    selector: dict | None = None               # For deterministic checks
    expected_value: str | None = None          # For element_text_contains

class RunTestsRequest(BaseModel):
    device_serial: str
    llm_provider: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None

class GenerateTestCasesRequest(BaseModel):
    workflow_name: str
    goal: str
    description: str                           # User describes what they want to test
    llm_provider: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None

# ---------------------------------------------------------------------------
# LLM factory helper
# ---------------------------------------------------------------------------

def _make_llm(provider: str, api_key=None, base_url=None, model=None) -> LLMClient:
    resolved_key = api_key or (
        settings.gemini_api_key if provider == "gemini" else
        settings.openai_api_key if provider == "openai" else
        settings.anthropic_api_key if provider == "anthropic" else None
    )
    resolved_url = base_url or (settings.local_llm_url if provider in ["local", "ollama", "vllm"] else None)
    resolved_model = model or (settings.local_llm_model if provider in ["local", "ollama", "vllm"] else None)
    return LLMClient(provider=provider, api_key=resolved_key, base_url=resolved_url, model=resolved_model)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    from .config import load_persistent_config
    return load_persistent_config()

@app.post("/api/settings")
def post_settings(req: SettingsRequest):
    from .config import update_settings_in_runtime
    update_settings_in_runtime(req.model_dump(exclude_unset=True))
    return {"status": "success"}

# ---------------------------------------------------------------------------
# Devices & models
# ---------------------------------------------------------------------------

@app.get("/api/devices")
def list_devices():
    return EmulatorManager.list_devices()

@app.get("/api/models")
def get_models(provider: str):
    provider = provider.lower()
    import requests as req_lib
    from .config import settings

    if provider == "gemini":
        key = settings.gemini_api_key
        if not key:
            return ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-flash"]
        try:
            res = req_lib.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=5
            )
            if res.status_code == 200:
                data = res.json()
                models = [
                    m["name"].replace("models/", "")
                    for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                models = [m for m in models if m.startswith("gemini-")]
                return models or ["gemini-2.5-flash", "gemini-2.5-pro"]
            else:
                print(f"Error fetching Gemini models via REST (status {res.status_code}): {res.text}")
                return ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
        except Exception as e:
            print(f"Error fetching Gemini models via REST: {e}")
            return ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

    elif provider == "openai":
        key = settings.openai_api_key
        if not key:
            return ["gpt-4o-mini", "gpt-4o", "o1-mini", "o3-mini"]
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            models = [m.id for m in client.models.list().data]
            filtered = sorted([m for m in models if m.startswith(("gpt-", "o1-", "o3-"))])
            return filtered or sorted(models)
        except Exception as e:
            print(f"Error fetching OpenAI models: {e}")
            return ["gpt-4o-mini", "gpt-4o", "o1-mini"]

    elif provider == "anthropic":
        return [
            "claude-3-5-sonnet-latest",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
        ]

    elif provider in ["local", "ollama", "vllm"]:
        url = settings.local_llm_url
        try:
            from openai import OpenAI
            client = OpenAI(base_url=url, api_key="none")
            return sorted([m.id for m in client.models.list().data])
        except Exception as e:
            print(f"Error fetching local models via OpenAI: {e}")
            try:
                base_url = url.split("/v1")[0]
                res = req_lib.get(f"{base_url}/api/tags", timeout=2)
                if res.status_code == 200:
                    return sorted([m["name"] for m in res.json().get("models", [])])
            except Exception:
                pass
            return ["llama3", "qwen2.5", "mistral", "phi3"]

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

@app.get("/api/workflows")
def list_workflows():
    return engine.list_workflows()

@app.get("/api/workflows/{name}")
def get_workflow(name: str):
    try:
        return engine.load_workflow(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.put("/api/workflows/{name}")
def update_workflow(name: str, req: UpdateWorkflowRequest):
    try:
        import unicodedata
        name = unicodedata.normalize('NFC', name)
        workflow = engine.load_workflow(name)
        if req.goal is not None:
            workflow["goal"] = req.goal
        if req.steps is not None:
            workflow["steps"] = req.steps
        if req.initial_package is not None:
            workflow["initial_package"] = req.initial_package
        engine.save_workflow(name, workflow)
        return {"status": "success", "workflow": workflow}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")


@app.delete("/api/workflows/{name}")
def delete_workflow(name: str):
    engine.delete_workflow(name)
    return {"status": "success", "message": f"Workflow '{name}' deleted"}

# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

@app.get("/api/screenshot/{device_serial}")
def get_screenshot(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        return {"screenshot": emulator.get_screenshot("base64")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/annotated-screenshot/{device_serial}")
def get_annotated_screenshot(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        img_b64, elements = emulator.get_annotated_screenshot()
        return {"screenshot": img_b64, "elements": elements}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/live/{device_serial}")
async def websocket_live_view(websocket: WebSocket, device_serial: str):
    await websocket.accept()
    show_annotated = websocket.query_params.get("showAnnotated", "false").lower() == "true"
    
    refresh_event = asyncio.Event()
    refresh_event.set()
    
    async def receive_commands():
        nonlocal show_annotated
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("action") == "refresh":
                    if "showAnnotated" in data:
                        show_annotated = bool(data["showAnnotated"])
                    refresh_event.set()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"WS command receiver error: {e}")
            
    receiver_task = asyncio.create_task(receive_commands())
    
    try:
        from fastapi.websockets import WebSocketState
        emulator = EmulatorManager(device_serial, auto_connect=False)
        loop = asyncio.get_running_loop()
        
        connected = await loop.run_in_executor(None, emulator.connect)
        if not connected:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.send_json({"error": "Failed to connect to device"})
            return
            
        while True:
            if websocket.client_state == WebSocketState.DISCONNECTED:
                break
            try:
                await asyncio.wait_for(refresh_event.wait(), timeout=1.5)
                refresh_event.clear()
            except asyncio.TimeoutError:
                pass
                
            if show_annotated:
                img_b64, elements = await loop.run_in_executor(None, emulator.get_annotated_screenshot)
                payload = {"screenshot": img_b64, "elements": elements}
            else:
                img_b64 = await loop.run_in_executor(None, lambda: emulator.get_screenshot("base64"))
                payload = {"screenshot": img_b64}
                
            if websocket.client_state == WebSocketState.DISCONNECTED:
                break
            await websocket.send_json(payload)
            
    except WebSocketDisconnect:
        pass
    except RuntimeError as e:
        if "websocket.send" in str(e) or "websocket.close" in str(e) or "response already completed" in str(e):
            pass
        else:
            print(f"WebSocket live connection error (RuntimeError): {e}")
    except Exception as e:
        print(f"WebSocket live connection error: {e}")
    finally:
        receiver_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass

@app.post("/api/session/{session_id}/llm")
def update_session_llm(session_id: str, req: ActiveLLMRequest):
    import unicodedata
    session_id = unicodedata.normalize('NFC', session_id)
    if session_id not in engine.active_sessions:
        raise HTTPException(
            status_code=404,
            detail=f"No active recording session found for '{session_id}'"
        )
    try:
        new_llm = _make_llm(req.llm_provider, req.llm_api_key, req.llm_base_url, req.llm_model)
        engine.active_sessions[session_id] = new_llm
        return {"status": "success", "message": f"LLM updated to {req.llm_provider} / {req.llm_model}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------------------------
# Direct action (manual control)
# ---------------------------------------------------------------------------

@app.post("/api/action")
def execute_direct_action(req: DirectActionRequest):
    try:
        emulator = EmulatorManager(req.device_serial)
        emulator.connect()
        if req.action == "click":
            if req.x is None or req.y is None:
                raise HTTPException(status_code=400, detail="Click requires x and y")
            emulator.click(req.x, req.y)
        elif req.action == "input_text":
            if not req.value:
                raise HTTPException(status_code=400, detail="input_text requires value")
            emulator.input_text(req.value)
        elif req.action == "press_key":
            if not req.value:
                raise HTTPException(status_code=400, detail="press_key requires value")
            emulator.press_key(req.value)
        elif req.action == "swipe":
            if not req.value:
                raise HTTPException(status_code=400, detail="swipe requires direction value")
            width, height = emulator.d.window_size()
            cx, cy = width // 2, height // 2
            if req.value == "up":
                emulator.swipe(cx, cy + int(height * 0.25), cx, cy - int(height * 0.25))
            elif req.value == "down":
                emulator.swipe(cx, cy - int(height * 0.25), cx, cy + int(height * 0.25))
            elif req.value == "left":
                emulator.swipe(cx + int(width * 0.25), cy, cx - int(width * 0.25), cy)
            elif req.value == "right":
                emulator.swipe(cx - int(width * 0.25), cy, cx + int(width * 0.25), cy)
        elif req.action == "open_app":
            if not req.value:
                raise HTTPException(status_code=400, detail="open_app requires app name as value")
            emulator.launch_app_by_name(req.value)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Recording (SSE stream)
# ---------------------------------------------------------------------------

@app.post("/api/record")
def record_workflow_stream(req: RecordRequest):
    """Stream the recording process via Server-Sent Events."""
    async def sse_generator():
        emulator = EmulatorManager(req.device_serial)
        connected = emulator.connect()
        if not connected:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Failed to connect to emulator'})}\n\n"
            return

        try:
            llm = _make_llm(req.llm_provider, req.llm_api_key, req.llm_base_url, req.llm_model)
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'LLM init failed: {e}'})}\n\n"
            return

        event_queue = asyncio.Queue()
        main_loop = asyncio.get_running_loop()

        def step_callback(event_data):
            asyncio.run_coroutine_threadsafe(event_queue.put(event_data), main_loop)

        def run_recording():
            try:
                workflow_data = engine.record_workflow(
                    name=req.workflow_name,
                    goal=req.goal,
                    emulator=emulator,
                    llm=llm,
                    max_steps=req.max_steps,
                    step_callback=step_callback,
                    plan=req.plan
                )
                step_callback({"status": "saved", "workflow": workflow_data})
            except Exception as e:
                step_callback({"status": "error", "message": f"Recording failed: {e}"})

        main_loop.run_in_executor(None, run_recording)

        while True:
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["saved", "error"]:
                break

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

# ---------------------------------------------------------------------------
# Intervention endpoint (inject user message into running session)
# ---------------------------------------------------------------------------

@app.post("/api/intervention/{session_id}")
def post_intervention(session_id: str, req: InterventionRequest):
    """Send a user instruction to a running recording session."""
    import unicodedata
    session_id = unicodedata.normalize('NFC', session_id)
    delivered = engine.post_intervention(session_id, req.message)
    if delivered:
        return {"status": "success", "message": "Instruction delivered to running session"}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No active recording session found for '{session_id}'. The session may have ended."
        )

# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

@app.post("/api/stop")
def stop_execution(req: StopRequest):
    engine.request_stop(req.device_serial)
    return {"status": "success", "message": f"Stop requested for device {req.device_serial}"}

# ---------------------------------------------------------------------------
# Playback (SSE stream)
# ---------------------------------------------------------------------------

@app.post("/api/playback")
def playback_workflow_stream(req: PlaybackRequest):
    """Stream the playback process via Server-Sent Events."""
    async def sse_generator():
        emulator = EmulatorManager(req.device_serial)
        connected = emulator.connect()
        if not connected:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Failed to connect to emulator'})}\n\n"
            return

        event_queue = asyncio.Queue()
        main_loop = asyncio.get_running_loop()

        def step_callback(event_data):
            asyncio.run_coroutine_threadsafe(event_queue.put(event_data), main_loop)

        def run_playback():
            try:
                success = engine.playback_workflow(
                    name=req.workflow_name,
                    emulator=emulator,
                    step_callback=step_callback
                )
                if success:
                    step_callback({"status": "done", "message": "Playback finished successfully"})
                else:
                    step_callback({"status": "error", "message": "Playback encountered issues"})
            except Exception as e:
                step_callback({"status": "error", "message": f"Playback failed: {e}"})

        main_loop.run_in_executor(None, run_playback)

        while True:
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["done", "error", "completed"]:
                break

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

# ---------------------------------------------------------------------------
# Test cases CRUD
# ---------------------------------------------------------------------------

@app.get("/api/workflows/{name}/test-cases")
def get_test_cases(name: str):
    try:
        return engine.get_test_cases(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.post("/api/workflows/{name}/test-cases")
def add_test_case(name: str, req: TestCaseRequest):
    try:
        tc = engine.add_test_case(name, req.model_dump())
        return tc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.put("/api/workflows/{name}/test-cases/{tc_id}")
def update_test_case(name: str, tc_id: str, req: TestCaseRequest):
    try:
        updated = engine.update_test_case(name, tc_id, req.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Test case not found")
        return updated
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.delete("/api/workflows/{name}/test-cases/{tc_id}")
def delete_test_case(name: str, tc_id: str):
    try:
        deleted = engine.delete_test_case(name, tc_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Test case not found")
        return {"status": "success"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")

# ---------------------------------------------------------------------------
# Run test cases (SSE stream)
# ---------------------------------------------------------------------------

@app.post("/api/workflows/{name}/run-tests")
def run_test_cases_stream(name: str, req: RunTestsRequest):
    """Run all test cases against the live emulator and stream results."""
    async def sse_generator():
        emulator = EmulatorManager(req.device_serial)
        connected = emulator.connect()
        if not connected:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Failed to connect to emulator'})}\n\n"
            return

        try:
            llm = _make_llm(req.llm_provider, req.llm_api_key, req.llm_base_url, req.llm_model)
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'LLM init failed: {e}'})}\n\n"
            return

        event_queue = asyncio.Queue()
        main_loop = asyncio.get_running_loop()

        def step_callback(event_data):
            asyncio.run_coroutine_threadsafe(event_queue.put(event_data), main_loop)

        def run_tests():
            try:
                engine.run_test_cases(
                    name=name,
                    emulator=emulator,
                    llm=llm,
                    step_callback=step_callback
                )
            except Exception as e:
                step_callback({"status": "error", "message": f"Test run failed: {e}"})

        main_loop.run_in_executor(None, run_tests)

        while True:
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["tests_complete", "error"]:
                break

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

# ---------------------------------------------------------------------------
# LLM-generated test cases from natural language description
# ---------------------------------------------------------------------------

@app.post("/api/test-cases/generate")
def generate_test_cases(req: GenerateTestCasesRequest):
    """Use LLM to generate test case definitions from a natural language description."""
    try:
        llm = _make_llm(req.llm_provider, req.llm_api_key, req.llm_base_url, req.llm_model)

        system_prompt = """You are an Android automation test designer.
Given a workflow goal and a user's description of what they want to verify, generate a list of concrete test case assertions.

Each test case should be:
- A specific, verifiable assertion about the device screen state
- Clear and unambiguous
- Testable by looking at the screen

Return JSON only:
{
  "test_cases": [
    {
      "name": "Short test case name",
      "description": "Natural language assertion to evaluate against the screen"
    }
  ]
}"""

        user_content = f"Workflow Goal: {req.goal}\n\nWhat to test: {req.description}"

        res = llm._dispatch(system_prompt, user_content)
        generated = res.get("test_cases", [])

        # Add to workflow if name is provided
        saved = []
        if req.workflow_name:
            try:
                for tc in generated:
                    saved.append(engine.add_test_case(req.workflow_name, {
                        "name": tc.get("name", "Test"),
                        "description": tc.get("description", ""),
                        "check_type": "llm_assert"
                    }))
            except FileNotFoundError:
                pass  # Workflow may not exist yet (pre-recording)

        return {
            "test_cases": saved if saved else generated,
            "saved_to_workflow": bool(saved)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Prompts API
# ---------------------------------------------------------------------------

@app.get("/api/prompts/{name}")
def get_prompt_content(name: str):
    try:
        from .llm_client import load_prompt
        return {"content": load_prompt(f"{name}.md")}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")

# ---------------------------------------------------------------------------
# Plan generation / refinement
# ---------------------------------------------------------------------------

@app.post("/api/plan/generate")
def generate_plan_api(req: PlanGenerateRequest):
    try:
        llm = _make_llm(req.llm_provider, req.llm_api_key, req.llm_base_url, req.llm_model)
        plan = llm.generate_initial_plan(req.goal, custom_prompt=req.prompt)
        return {"plan": plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/plan/refine")
def refine_plan_api(req: PlanRefineRequest):
    try:
        llm = _make_llm(req.llm_provider, req.llm_api_key, req.llm_base_url, req.llm_model)
        res = llm.refine_plan(
            goal=req.goal,
            current_plan=req.current_plan,
            feedback=req.feedback,
            custom_prompt=req.prompt
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount MCP HTTP app at the very end to prevent it from intercepting other routes
app.mount("/", mcp_http_app)
