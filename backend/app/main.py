from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import os
import json
import io
import base64
from contextlib import asynccontextmanager

from .emulator import EmulatorManager
from .mcp_server import mcp, device_elements_cache

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

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class DirectActionRequest(BaseModel):
    device_serial: str
    action: str
    x: int | None = None
    y: int | None = None
    value: str | None = None
    visual_id: int | None = None
    start_x: int | None = None
    start_y: int | None = None
    end_x: int | None = None
    end_y: int | None = None
    steps: int | None = 10

# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

@app.get("/api/devices")
def list_devices():
    return EmulatorManager.list_devices()

# ---------------------------------------------------------------------------
# Screenshots & Live WebSocket Stream
# ---------------------------------------------------------------------------

@app.get("/api/screenshot/{device_serial}")
def get_screenshot(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        return {"screenshot": emulator.get_screenshot("base64")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/screenshot/{device_serial}/raw")
def get_screenshot_raw(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        img = emulator.get_screenshot("pil")
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=70)
        return Response(content=buffered.getvalue(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/annotated-screenshot/{device_serial}")
def get_annotated_screenshot(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        img_b64, elements = emulator.get_annotated_screenshot()
        device_elements_cache[device_serial] = elements
        return {"screenshot": img_b64, "elements": elements}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/annotated-screenshot/{device_serial}/raw")
def get_annotated_screenshot_raw(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        img_b64, elements = emulator.get_annotated_screenshot()
        device_elements_cache[device_serial] = elements
        img_bytes = base64.b64decode(img_b64)
        return Response(content=img_bytes, media_type="image/jpeg")
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
                device_elements_cache[device_serial] = elements
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

# ---------------------------------------------------------------------------
# Direct Action (Manual Control)
# ---------------------------------------------------------------------------

@app.post("/api/action")
def execute_direct_action(req: DirectActionRequest):
    try:
        emulator = EmulatorManager(req.device_serial)
        if req.action != "connect":
            emulator.connect()
            if not emulator.d:
                raise HTTPException(status_code=500, detail="Failed to connect to device")

        if req.action == "connect":
            success = emulator.connect()
            if success:
                return {"status": "success", "detail": f"Successfully connected to device: {req.device_serial}"}
            else:
                raise HTTPException(status_code=500, detail=f"Failed to connect to device: {req.device_serial}")
        elif req.action == "click":
            if req.x is None or req.y is None:
                raise HTTPException(status_code=400, detail="Click requires x and y")
            emulator.click(req.x, req.y)
        elif req.action == "click_element":
            if req.visual_id is None:
                raise HTTPException(status_code=400, detail="click_element requires visual_id")
            elements = device_elements_cache.get(req.device_serial, [])
            if not elements:
                raise HTTPException(status_code=400, detail="No element cache found for this device. Please capture an annotated screenshot first.")
            target_el = next((el for el in elements if el.get("visual_id") == req.visual_id), None)
            if not target_el:
                raise HTTPException(status_code=404, detail=f"Element with visual ID {req.visual_id} not found in cache. Refresh screenshot.")
            cx, cy = target_el["center"]
            emulator.click(cx, cy)
            label = target_el.get("text") or target_el.get("content_desc") or f"element {req.visual_id}"
            return {"status": "success", "detail": f"Successfully clicked on '{label}' at ({cx}, {cy})"}
        elif req.action == "input_text":
            if req.value is None:
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
            else:
                raise HTTPException(status_code=400, detail=f"Invalid swipe direction: {req.value}")
        elif req.action == "swipe_coordinates":
            if req.start_x is None or req.start_y is None or req.end_x is None or req.end_y is None:
                raise HTTPException(status_code=400, detail="swipe_coordinates requires start_x, start_y, end_x, and end_y")
            steps = req.steps if req.steps is not None else 10
            emulator.swipe(req.start_x, req.start_y, req.end_x, req.end_y, steps=steps)
        elif req.action == "open_app":
            if not req.value:
                raise HTTPException(status_code=400, detail="open_app requires app name or package as value")
            if "." in req.value:
                try:
                    emulator.launch_app(req.value)
                    return {"status": "success", "detail": f"Successfully launched app package: {req.value}"}
                except Exception as e:
                    print(f"Direct package launch failed, falling back to name search: {e}")
            success = emulator.launch_app_by_name(req.value)
            if success:
                return {"status": "success", "detail": f"Successfully launched app: '{req.value}'"}
            else:
                raise HTTPException(status_code=500, detail=f"Failed to launch app: '{req.value}'")
        elif req.action == "stop_app":
            if not req.value:
                raise HTTPException(status_code=400, detail="stop_app requires package name as value")
            emulator.stop_app(req.value)
            return {"status": "success", "detail": f"Successfully stopped app package: {req.value}"}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/current-package/{device_serial}")
def get_current_package(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        pkg = emulator.get_current_package()
        return {"package": pkg if pkg else "unknown"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/connect/{device_serial}")
def connect_device(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial, auto_connect=False)
        success = emulator.connect()
        if success:
            return {"status": "success", "detail": f"Successfully connected to device: {device_serial}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to connect to device: {device_serial}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hierarchy/{device_serial}")
def get_ui_hierarchy(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        xml_data = emulator.get_ui_hierarchy()
        return Response(content=xml_data, media_type="application/xml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/info/{device_serial}")
def get_device_info(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            raise HTTPException(status_code=500, detail="Failed to connect to device")
        return emulator.d.info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/window-size/{device_serial}")
def get_window_size(device_serial: str):
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            raise HTTPException(status_code=500, detail="Failed to connect to device")
        width, height = emulator.d.window_size()
        return {"width": width, "height": height}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Frontend Static Files Serving & Catch-All Routing
# ---------------------------------------------------------------------------

dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
assets_dir = os.path.join(dist_dir, "assets")

if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/{catchall:path}")
async def serve_frontend(catchall: str):
    index_file = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Frontend build not found. Run npm run build."}

# Mount MCP HTTP app as fallback
app.mount("/mcp-http", mcp_http_app)
