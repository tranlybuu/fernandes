import builtins
import sys
import os

# Override builtins.print to write to stderr by default.
# This prevents random print statements in imported libraries (like uiautomator2)
# from corrupting the stdio JSON-RPC stream used by MCP.
_original_print = builtins.print
def safe_print(*args, **kwargs):
    kwargs.setdefault('file', sys.stderr)
    _original_print(*args, **kwargs)
builtins.print = safe_print

# Ensure backend directory is in python path so imports work correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
try:
    from .emulator import EmulatorManager
except ImportError:
    from emulator import EmulatorManager

# Create FastMCP server
mcp = FastMCP(
    "Fernandes Device Control",
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8012")),
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
)

# In-memory cache for elements from the last get_screenshot call, keyed by device_serial
device_elements_cache = {}

@mcp.tool()
def list_devices() -> list[dict]:
    """
    List all connected Android devices and emulators.
    
    Returns a list of dictionaries, each containing:
    - serial: The device serial number.
    - status: The connection status (e.g. 'device', 'unauthorized', 'offline').
    - model: The model name of the device (if authorized).
    """
    try:
        return EmulatorManager.list_devices()
    except Exception as e:
        safe_print(f"Error in list_devices: {e}")
        return []

@mcp.tool()
def connect_device(device_serial: str) -> str:
    """
    Connect to a specific Android device by its serial number and wake/unlock the screen.
    
    Args:
        device_serial: The serial number of the target Android device.
    """
    try:
        emulator = EmulatorManager(device_serial, auto_connect=False)
        connected = emulator.connect()
        if connected:
            return f"Successfully connected to device: {device_serial}"
        else:
            return f"Failed to connect to device: {device_serial}"
    except Exception as e:
        return f"Error connecting to device: {e}"

@mcp.tool()
def get_screenshot(device_serial: str, annotate: bool = True) -> dict:
    """
    Capture the screen of the specified device.
    
    Args:
        device_serial: The serial number of the target Android device.
        annotate: If true, returns an annotated JPEG screenshot (base64) with red bounding
                  boxes and visual IDs, along with interactive elements metadata.
                  If false, returns the raw unannotated JPEG screenshot (base64).
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return {"error": f"Failed to connect to device: {device_serial}. Make sure the device is active."}
        
        if annotate:
            img_b64, elements = emulator.get_annotated_screenshot()
            device_elements_cache[device_serial] = elements
            return {
                "screenshot": img_b64,
                "elements": [
                    {
                        "visual_id": el["visual_id"],
                        "text": el.get("text"),
                        "content_desc": el.get("content_desc"),
                        "resource_id": el.get("resource_id"),
                        "class_name": el.get("class_name"),
                        "bounds": el["bounds"],
                        "center": el["center"]
                    }
                    for el in elements
                ]
            }
        else:
            img_b64 = emulator.get_screenshot("base64")
            return {
                "screenshot": img_b64
            }
    except Exception as e:
        safe_print(f"Error in get_screenshot: {e}")
        return {"error": str(e)}

@mcp.tool()
def click_element(device_serial: str, visual_id: int) -> str:
    """
    Click on an interactive element by its visual ID from the last annotated screenshot.
    You must call get_screenshot with annotate=True before using this tool.
    
    Args:
        device_serial: The serial number of the target Android device.
        visual_id: The visual ID (number) of the element to click.
    """
    try:
        elements = device_elements_cache.get(device_serial, [])
        if not elements:
            return "No element cache found for this device. Please call get_screenshot(device_serial, annotate=True) first."
            
        target_el = next((el for el in elements if el.get("visual_id") == visual_id), None)
        if not target_el:
            return f"Element with visual ID {visual_id} not found in the last screenshot cache. Please call get_screenshot again to refresh."
            
        cx, cy = target_el["center"]
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        
        emulator.click(cx, cy)
        label = target_el.get("text") or target_el.get("content_desc") or f"element {visual_id}"
        return f"Successfully clicked on '{label}' at ({cx}, {cy})"
    except Exception as e:
        return f"Error clicking element: {e}"

@mcp.tool()
def click_coordinate(device_serial: str, x: int, y: int) -> str:
    """
    Click at specific screen coordinates (x, y) on the device.
    
    Args:
        device_serial: The serial number of the target Android device.
        x: The horizontal pixel coordinate.
        y: The vertical pixel coordinate.
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        emulator.click(x, y)
        return f"Successfully clicked at ({x}, {y})"
    except Exception as e:
        return f"Error clicking at coordinates: {e}"

@mcp.tool()
def input_text(device_serial: str, text: str) -> str:
    """
    Type text into the currently active/focused input field on the device.
    Usually, you should click on the input field first.
    
    Args:
        device_serial: The serial number of the target Android device.
        text: The text string to input.
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        emulator.input_text(text)
        return f"Successfully typed text: '{text}'"
    except Exception as e:
        return f"Error inputting text: {e}"

@mcp.tool()
def press_key(device_serial: str, key: str) -> str:
    """
    Press a hardware or system key on the device.
    
    Args:
        device_serial: The serial number of the target Android device.
        key: The key name (e.g. 'home', 'back', 'enter', 'menu', 'search', 'volume_up', 'volume_down').
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        emulator.press_key(key)
        return f"Successfully pressed key: '{key}'"
    except Exception as e:
        return f"Error pressing key: {e}"

@mcp.tool()
def swipe(device_serial: str, direction: str) -> str:
    """
    Swipe in a direction from the center of the screen.
    
    Args:
        device_serial: The serial number of the target Android device.
        direction: The swipe direction ('up', 'down', 'left', 'right').
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
            
        width, height = emulator.d.window_size()
        cx, cy = width // 2, height // 2
        
        if direction == "up":
            emulator.swipe(cx, cy + int(height * 0.25), cx, cy - int(height * 0.25))
        elif direction == "down":
            emulator.swipe(cx, cy - int(height * 0.25), cx, cy + int(height * 0.25))
        elif direction == "left":
            emulator.swipe(cx + int(width * 0.25), cy, cx - int(width * 0.25), cy)
        elif direction == "right":
            emulator.swipe(cx - int(width * 0.25), cy, cx + int(width * 0.25), cy)
        else:
            return f"Invalid swipe direction: {direction}. Must be 'up', 'down', 'left', or 'right'."
            
        return f"Successfully swiped {direction}"
    except Exception as e:
        return f"Error swiping: {e}"

@mcp.tool()
def swipe_coordinates(device_serial: str, start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 10) -> str:
    """
    Perform a swipe gesture from start coordinates to end coordinates.
    
    Args:
        device_serial: The serial number of the target Android device.
        start_x: The starting horizontal coordinate.
        start_y: The starting vertical coordinate.
        end_x: The ending horizontal coordinate.
        end_y: The ending vertical coordinate.
        steps: Duration of the swipe (10 steps is ~0.5 seconds).
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        emulator.swipe(start_x, start_y, end_x, end_y, steps=steps)
        return f"Successfully swiped from ({start_x}, {start_y}) to ({end_x}, {end_y})"
    except Exception as e:
        return f"Error swiping coordinates: {e}"

@mcp.tool()
def launch_app(device_serial: str, app_name_or_package: str) -> str:
    """
    Launch an application on the device.
    
    Args:
        device_serial: The serial number of the target Android device.
        app_name_or_package: Common app name (e.g. 'chrome', 'settings') or package name (e.g. 'com.android.chrome').
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
            
        # Try direct package name launch first if it looks like a package (contains dot)
        if "." in app_name_or_package:
            try:
                emulator.launch_app(app_name_or_package)
                return f"Successfully launched app package: {app_name_or_package}"
            except Exception as e:
                safe_print(f"Direct package launch failed, falling back to name search: {e}")
                
        # Launch by name search
        success = emulator.launch_app_by_name(app_name_or_package)
        if success:
            return f"Successfully launched app: '{app_name_or_package}'"
        else:
            return f"Failed to launch app: '{app_name_or_package}'"
    except Exception as e:
        return f"Error launching app: {e}"

@mcp.tool()
def stop_app(device_serial: str, package_name: str) -> str:
    """
    Force stop an application by package name.
    
    Args:
        device_serial: The serial number of the target Android device.
        package_name: The package name of the app to stop (e.g. 'com.android.chrome').
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        emulator.stop_app(package_name)
        return f"Successfully stopped app: {package_name}"
    except Exception as e:
        return f"Error stopping app: {e}"

@mcp.tool()
def get_current_package(device_serial: str) -> str:
    """
    Get the package name of the currently running foreground application.
    
    Args:
        device_serial: The serial number of the target Android device.
    """
    try:
        emulator = EmulatorManager(device_serial)
        if not emulator.d:
            return "Failed to connect to device."
        pkg = emulator.get_current_package()
        return pkg if pkg else "unknown"
    except Exception as e:
        return f"Error getting current package: {e}"

@mcp.resource(
    "docs://api-specification",
    name="rest_api_specification",
    title="Fernandes REST API Specification",
    description="The complete REST API specification and endpoints for controlling Android devices",
    mime_type="text/markdown"
)
def get_api_specification() -> str:
    """
    Get the REST API specification and endpoints for controlling Android devices.
    """
    return """# Fernandes Device Control REST API Specification

In addition to using direct MCP tools, you can control the connected devices using these HTTP REST endpoints. The backend server runs locally on http://127.0.0.1:9999.

## Base URL: http://127.0.0.1:9999

## Endpoints

### 1. Devices List
* **URL**: `/api/devices`
* **Method**: `GET`
* **Response**: List of connected devices.
  ```json
  [
    {
      "serial": "emulator-5554",
      "status": "device",
      "model": "sdk_gphone16k_arm64"
    }
  ]
  ```

### 2. Connect / Unlock Device
* **URL**: `/api/connect/{device_serial}`
* **Method**: `POST`
* **Response**: `{"status": "success", "detail": "..."}`

### 3. Screen Captures
* **Raw Base64 Screenshot**: `GET /api/screenshot/{device_serial}` -> returns `{"screenshot": "<base64>"}`
* **Raw Binary Image**: `GET /api/screenshot/{device_serial}/raw` -> returns binary `image/jpeg`
* **Annotated Base64 Screenshot**: `GET /api/annotated-screenshot/{device_serial}` -> returns `{"screenshot": "<base64>", "elements": [...]}` and populates/updates the visual element ID cache.
* **Annotated Binary Image**: `GET /api/annotated-screenshot/{device_serial}/raw` -> returns binary `image/jpeg`

### 4. Device Layout & Properties
* **UI Hierarchy XML**: `GET /api/hierarchy/{device_serial}` -> returns `application/xml` representation of active screen.
* **Device System Info**: `GET /api/info/{device_serial}` -> returns device system parameters.
* **Window Size**: `GET /api/window-size/{device_serial}` -> returns `{"width": 1080, "height": 1920}`.
* **Current Foreground Package**: `GET /api/current-package/{device_serial}` -> returns `{"package": "com.android.settings"}`.

### 5. Execute Action
* **URL**: `/api/action`
* **Method**: `POST`
* **Content-Type**: `application/json`
* **Body Model**:
  ```json
  {
    "device_serial": "string",
    "action": "string",
    "x": "integer (optional)",
    "y": "integer (optional)",
    "value": "string (optional)",
    "visual_id": "integer (optional)",
    "start_x": "integer (optional)",
    "start_y": "integer (optional)",
    "end_x": "integer (optional)",
    "end_y": "integer (optional)",
    "steps": "integer (optional, default: 10)"
  }
  ```
* **Supported Action Values**:
  * `"connect"`: Connects and unlocks device.
  * `"click"`: Clicks at coordinates `(x, y)`.
  * `"click_element"`: Clicks cached element center using `visual_id` (must run an annotated screenshot first).
  * `"input_text"`: Types text passed in `value`.
  * `"press_key"`: Presses system key passed in `value` (e.g., `"home"`, `"back"`, `"enter"`).
  * `"swipe"`: Swipes in direction passed in `value` (`"up"`, `"down"`, `"left"`, `"right"`).
  * `"swipe_coordinates"`: Swipes from `(start_x, start_y)` to `(end_x, end_y)` in `steps`.
  * `"open_app"`: Launches app by package name or common app name in `value`.
  * `"stop_app"`: Forces app package in `value` to stop.

### 6. Live WebSocket View
* **URL**: `/ws/live/{device_serial}?showAnnotated=true`
* **Protocol**: `ws://` / `wss://`
* **Description**: WebSocket stream serving live screen frames and updating the element ID cache.
"""

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run()
