from fastapi import FastAPI, HTTPException, BackgroundTasks
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

app = FastAPI(title="Android Simulator Automation API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = WorkflowEngine()

class RecordRequest(BaseModel):
    workflow_name: str
    goal: str
    device_serial: str
    llm_provider: str
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    max_steps: int = 15

class PlaybackRequest(BaseModel):
    workflow_name: str
    device_serial: str

class DirectActionRequest(BaseModel):
    device_serial: str
    action: str  # click, input_text, press_key, swipe
    x: int | None = None
    y: int | None = None
    value: str | None = None

class SettingsRequest(BaseModel):
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    local_llm_url: str | None = None
    local_llm_model: str | None = None

@app.get("/api/settings")
def get_settings():
    from .config import load_persistent_config
    return load_persistent_config()

@app.post("/api/settings")
def post_settings(req: SettingsRequest):
    from .config import update_settings_in_runtime
    update_settings_in_runtime(req.model_dump(exclude_unset=True))
    return {"status": "success"}

@app.get("/api/devices")
def list_devices():
    return EmulatorManager.list_devices()

@app.get("/api/workflows")
def list_workflows():
    return engine.list_workflows()

@app.get("/api/workflows/{name}")
def get_workflow(name: str):
    try:
        return engine.load_workflow(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.delete("/api/workflows/{name}")
def delete_workflow(name: str):
    engine.delete_workflow(name)
    return {"status": "success", "message": f"Workflow {name} deleted"}

@app.get("/api/screenshot/{device_serial}")
def get_screenshot(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        img_b64 = emulator.get_screenshot("base64")
        return {"screenshot": img_b64}
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

@app.post("/api/action")
def execute_direct_action(req: DirectActionRequest):
    try:
        emulator = EmulatorManager(req.device_serial)
        emulator.connect()
        
        if req.action == "click":
            if req.x is None or req.y is None:
                raise HTTPException(status_code=400, detail="Click requires x and y coordinates")
            emulator.click(req.x, req.y)
        elif req.action == "input_text":
            if not req.value:
                raise HTTPException(status_code=400, detail="Input requires value")
            emulator.input_text(req.value)
        elif req.action == "press_key":
            if not req.value:
                raise HTTPException(status_code=400, detail="Press key requires value")
            emulator.press_key(req.value)
        elif req.action == "swipe":
            if not req.value:
                raise HTTPException(status_code=400, detail="Swipe requires direction (value) 'up', 'down', 'left', or 'right'")
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
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/record")
def record_workflow_stream(req: RecordRequest):
    """Streams the record process to the client via Server-Sent Events (SSE)."""
    async def sse_generator():
        # Setup clients
        emulator = EmulatorManager(req.device_serial)
        connected = emulator.connect()
        if not connected:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Failed to connect to emulator'})}\n\n"
            return

        try:
            # Fallback to backend config.json if keys aren't passed in request
            api_key = req.llm_api_key or (
                settings.gemini_api_key if req.llm_provider == "gemini" else
                settings.openai_api_key if req.llm_provider == "openai" else
                settings.anthropic_api_key if req.llm_provider == "anthropic" else None
            )
            base_url = req.llm_base_url or (settings.local_llm_url if req.llm_provider in ["local", "ollama", "vllm"] else None)
            model = req.llm_model or (settings.local_llm_model if req.llm_provider in ["local", "ollama", "vllm"] else None)

            llm = LLMClient(
                provider=req.llm_provider,
                api_key=api_key,
                base_url=base_url,
                model=model
            )
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Failed to init LLM client: {e}'})}\n\n"
            return

        event_queue = asyncio.Queue()
        main_loop = asyncio.get_running_loop()

        def step_callback(event_data):
            # Put in queue in thread-safe way using the captured main_loop
            asyncio.run_coroutine_threadsafe(event_queue.put(event_data), main_loop)

        # Run recording in a separate thread because uiautomator2/LLM SDK calls are blocking
        def run_recording():
            try:
                workflow_data = engine.record_workflow(
                    name=req.workflow_name,
                    goal=req.goal,
                    emulator=emulator,
                    llm=llm,
                    max_steps=req.max_steps,
                    step_callback=step_callback
                )
                step_callback({"status": "saved", "workflow": workflow_data})
            except Exception as e:
                step_callback({"status": "error", "message": f"Recording failed: {str(e)}"})

        # Start background recording
        main_loop.run_in_executor(None, run_recording)

        # Stream queue elements to client
        while True:
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["saved", "error", "completed"]:
                break

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.post("/api/playback")
def playback_workflow_stream(req: PlaybackRequest):
    """Streams the playback process to the client via Server-Sent Events (SSE)."""
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
                step_callback({"status": "error", "message": f"Playback failed: {str(e)}"})

        # Start background playback
        main_loop.run_in_executor(None, run_playback)

        # Stream queue elements to client
        while True:
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["done", "error", "completed"]:
                break

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
