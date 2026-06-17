# US-device-control-mcp Mobile Control Protocol (MCP) Server for Android Device Control

## Status

implemented

## Lane

normal

## Product Contract

1. The backend must provide a Model Context Protocol (MCP) server running over stdio.
2. The MCP server must expose tools matching the existing `EmulatorManager` device control operations.
3. The MCP server must support retrieving screen state (with bounding box annotations and visual ID assignments).
4. The MCP server must cache elements from the last annotated screenshot per device to allow clicking elements by their visual ID.
5. The workflows themselves are not included in the MCP tools; the agent decides step-by-step actions by calling device control tools.

## Relevant Product Docs

- `docs/ARCHITECTURE.md`
- `docs/TOOL_REGISTRY.md`

## Acceptance Criteria

- [x] Add `mcp` dependency to `backend/requirements.txt` and install it.
- [x] Implement `backend/app/mcp_server.py` exposing:
  - `list_devices`: lists ADB device serials and models.
  - `connect_device`: connects and unlocks device.
  - `get_screenshot`: returns screenshot (and element bounds + IDs if annotated).
  - `click_element`: clicks an element by its visual ID from last screenshot.
  - `click_coordinate`: clicks specific coordinates (x, y).
  - `input_text`: sends text input to the device.
  - `press_key`: presses a key (e.g. back, home, enter).
  - `swipe`: swipes in up, down, left, right directions.
  - `swipe_coordinates`: swipes between custom coordinates.
  - `launch_app`: starts an app by name or package name.
  - `stop_app`: stops an app package.
  - `get_current_package`: returns current app package.
- [x] Implement a scratch validation script that spawns the MCP server via JSON-RPC/stdio and exercises the main tools.
- [x] Register the MCP server as a tool in `harness.db`.

## Design Notes

- The MCP server is executed as a python module: `python -m app.mcp_server`.
- Coordinates-based click and visual-ID-based click are both supported.
- Element caching is stored in-memory in a dict keyed by `device_serial`.

## Validation

| Layer | Expected proof | Status |
| --- | --- | --- |
| Unit | N/A | N/A |
| Integration | Handshake and tool invocation tests via scratch client script | passed |
| E2E | N/A | N/A |
| Platform | harness-cli tool query and run checks | passed |
| Release | N/A | N/A |

## Harness Delta

- Fixed `harness.db` tool table schema columns mismatch.
- Registered the `device-control` MCP server tool.

## Evidence

- **JSON-RPC Handshake and Tool Listing**: Verified that running the MCP server locally over stdio completes the handshake protocol correctly. The client successfully listed all 12 registered tools:
  ```json
  "tools": ["list_devices", "connect_device", "get_screenshot", "click_element", "click_coordinate", "input_text", "press_key", "swipe", "swipe_coordinates", "launch_app", "stop_app", "get_current_package"]
  ```
- **Tool Execution (list_devices)**: Verified that calling `list_devices` returns the correct JSON containing the active emulator:
  ```json
  {
    "serial": "emulator-5554",
    "status": "device",
    "model": "sdk_gphone16k_arm64"
  }
  ```
- **Tool Check Verification**: Running `./scripts/bin/harness-cli tool check` verifies the registered MCP tool is present and matches the scan target:
  ```
  name            kind  capability      status   detail
  --------------  ----  --------------  -------  -------------------------
  device-control  mcp   device-control  present  backend/app/mcp_server.py
  ```
- **End-to-End Device Control Verification**: Verified that the MCP server successfully controls the running `emulator-5554` device via the standard stdio JSON-RPC protocol:
  - Fetched foreground application (`com.android.vending`).
  - Captured screen state and successfully identified 22 interactive elements on the screen.
  - Performed a click action (`click_element`) mapped to coordinates using the visual ID.
  - Successfully issued a Home key press (`press_key`) to reset the screen state.

