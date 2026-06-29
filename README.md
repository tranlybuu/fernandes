# Fernandes — Unified Android Automation Hub & AI Agent Control

Fernandes is an open-source, unified platform designed for real-time Android device control, automation, and Model Context Protocol (MCP) integration. It enables both human developers (via a clean web interface) and AI agents (such as Claude or Gemini via MCP) to interact with and control Android devices or emulators seamlessly.

---

## 🚀 Key Features

* 📱 **Interactive Web Console**: A low-latency live view of your Android device's screen streaming in real-time via WebSockets. Supports interactive mouse clicking, custom swiping, physical key injection, and app launching.
* 🤖 **Model Context Protocol (MCP)**: Native FastMCP integration enabling LLMs to list, connect, inspect, and fully control Android devices using standard tool invocations.
* 🔍 **UI Element Annotation & OCR**: Automatically retrieves, parses, and overlays the UI hierarchy and bounds on top of the live view, giving you and your AI agent precise target visual IDs to interact with.
* 🔌 **Flexible REST & WebSocket API**: Full control over connected devices using standard HTTP REST endpoints and interactive WebSockets.
* 🛠️ **Seamless Platform Support**: Automatically detects and configures standard Android SDK path locations for `adb` across macOS, Linux, and Windows.

---

## 📐 Architecture Overview

Fernandes is structured as a monorepo consisting of two primary components:

1. **Backend (`backend/`)**: A Python FastAPI service powered by `FastMCP`, `uiautomator2`, and `adb`. It handles:
   * Fetching and managing ADB connections.
   * Exposing REST APIs and WebSocket endpoints for streaming screenshots and element coordinate caching.
   * Serving the Model Context Protocol (MCP) SSE endpoints.
   * Compiling and serving the built frontend React application.
2. **Frontend (`frontend/`)**: A Vite-powered React single page application built with Tailwind CSS. It provides a visual dashboard for device selection, screen interaction, and coordinate annotations.

---

## ⚙️ Ports & Configuration

Fernandes is configured to run across multiple environments:

| Mode | Entry Command | Backend / Unified URL | Frontend Dev URL | MCP SSE Connection String |
| :--- | :--- | :--- | :--- | :--- |
| **Default Production** | `./start.sh` | `http://localhost:9999` | *Served by Backend* | `http://localhost:9999/mcp/sse` |
| **Development** | `make dev` | `http://localhost:8000` | `http://localhost:5173` | `http://localhost:8000/mcp/sse` |
| **Makefile Unified** | `make start` | `http://localhost:8000` | *Served by Backend* | `http://localhost:8000/mcp/sse` |

---

## 🛠️ Prerequisites

Ensure you have the following installed on your host machine:

* **Python 3.10+** (with virtual environment support)
* **Node.js 18+** & **npm**
* **Android SDK** (Make sure `adb` is in your system's `PATH`, or installed at standard SDK locations)
* **Android Device / Emulator** (With *USB Debugging* enabled)

---

## 🚀 Getting Started

### 1. Installation

Set up both Python virtual environments, install dependencies, and download frontend packages:

```bash
make install
```

### 2. Running Fernandes

Choose one of the run modes:

#### Option A: Unified / Default Mode (Recommended)
This compiles the frontend assets and starts the FastAPI server on port **`9999`** which hosts both the API and the user interface.
```bash
./start.sh
```
Access the dashboard at [http://localhost:9999](http://localhost:9999).

#### Option B: Development Mode
Runs the backend on port **`8000`** and the Vite development server on port **`5173`** with hot-reloading enabled.
```bash
make dev
```
Access the development interface at [http://localhost:5173](http://localhost:5173).

#### Option C: Production Server via Makefile
Compiles production assets and starts the unified server on port **`8000`**.
```bash
make start
```
Access the server at [http://localhost:8000](http://localhost:8000).

---

## 🤖 MCP Integration for AI Agents

To allow an LLM or Agent Client (like Cursor, Claude Desktop, or Windsurf) to control your Android device, register the Fernandes MCP SSE connection. 

### Claude Desktop Integration Configuration
Add the following to your `claude_desktop_config.json` (usually located at `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "fernandes": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/client-sse", "http://localhost:9999/mcp/sse"]
    }
  }
}
```
*(Note: If you launched Fernandes using the development mode on port 8000, update the connection URL to `http://localhost:8000/mcp/sse`)*

---

## 📂 Project Structure

```text
fernandes/
├── backend/                  # FastAPI Application & MCP Server
│   ├── app/
│   │   ├── emulator.py       # uiautomator2 wrapper & adb integrations
│   │   ├── main.py           # REST APIs, WebSockets, & SPA static serving
│   │   └── mcp_server.py     # FastMCP tool configurations
│   ├── requirements.txt      # Python dependencies
│   └── venv/                 # Virtual environment (ignored)
├── frontend/                 # Vite + React SPA Console
│   ├── src/
│   │   ├── components/       # LiveView, DeviceSelector components
│   │   └── App.jsx           # Main React Dashboard
│   ├── package.json          # Node dependencies
│   └── vite.config.js        # Vite configurations
├── start.sh                  # Unified script for startup on port 9999
├── Makefile                  # Build, run, and development scripts
└── README.md                 # Project documentation (this file)
```

---

## 📄 License
This project is open-source and available under the MIT License.
