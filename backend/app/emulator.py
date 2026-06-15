import subprocess
import uiautomator2 as u2
import re
import os
import shutil
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
import io
import base64

# Automatically resolve and add standard Android SDK platform-tools paths to PATH
# to support environments where adb is not added to ~/.zshrc or ~/.bashrc
home = os.path.expanduser("~")
platform_tools_paths = [
    os.path.join(home, "Library/Android/sdk/platform-tools"),
    os.path.join(home, "AppData/Local/Android/Sdk/platform-tools"),
    os.path.join(home, "Android/Sdk/platform-tools")
]
for pt_path in platform_tools_paths:
    if os.path.exists(pt_path):
        os.environ["PATH"] = pt_path + os.pathsep + os.environ.get("PATH", "")
        break

class EmulatorManager:
    def __init__(self, device_serial: str | None = None):
        self.device_serial = device_serial
        self.d = None
        if device_serial:
            self.connect()

    def connect(self):
        try:
            self.d = u2.connect(self.device_serial)
            # Wake up screen if off
            if not self.d.info.get("screenOn", True):
                self.d.screen_on()
                self.d.unlock()
            return True
        except Exception as e:
            print(f"Error connecting to device {self.device_serial}: {e}")
            return False

    @staticmethod
    def list_devices() -> list[dict]:
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")[1:]
            devices = []
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    status = parts[1]
                    # Get model/name if device is authorized
                    model = "Unknown Device"
                    if status == "device":
                        try:
                            prop_res = subprocess.run(
                                ["adb", "-s", serial, "shell", "getprop", "ro.product.model"],
                                capture_output=True, text=True, timeout=2
                            )
                            model = prop_res.stdout.strip() or serial
                        except Exception:
                            model = serial
                    devices.append({
                        "serial": serial,
                        "status": status,
                        "model": model
                    })
            return devices
        except Exception as e:
            print(f"Error listing adb devices: {e}")
            return []

    def get_screenshot(self, format: str = "pil"):
        """Gets screenshot of the active screen."""
        if not self.d:
            raise Exception("Device not connected")
        img = self.d.screenshot()
        if format == "pil":
            return img
        elif format == "base64":
            # Convert to RGB (JPEG doesn't support Alpha/transparency)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return img_str
        return img

    def get_ui_hierarchy(self) -> str:
        """Gets the XML view hierarchy."""
        if not self.d:
            raise Exception("Device not connected")
        return self.d.dump_hierarchy()

    def parse_bounds(self, bounds_str: str) -> tuple[int, int, int, int]:
        """Parses bounds string '[x1,y1][x2,y2]' to (x1, y1, x2, y2)."""
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
        if match:
            return tuple(map(int, match.groups()))
        return (0, 0, 0, 0)

    def extract_elements(self) -> list[dict]:
        """Parses the hierarchy and extracts interactive elements."""
        xml_data = self.get_ui_hierarchy()
        try:
            root = ET.fromstring(xml_data.encode("utf-8"))
        except Exception as e:
            print(f"Failed to parse UI XML: {e}")
            return []

        elements = []
        element_id = 0

        # Traverse hierarchy tree
        for node in root.iter("node"):
            attrib = node.attrib
            clickable = attrib.get("clickable") == "true"
            checkable = attrib.get("checkable") == "true"
            scrollable = attrib.get("scrollable") == "true"
            long_clickable = attrib.get("long-clickable") == "true"
            focusable = attrib.get("focusable") == "true"
            
            text = attrib.get("text", "").strip()
            content_desc = attrib.get("content-desc", "").strip()
            resource_id = attrib.get("resource-id", "").strip()
            class_name = attrib.get("class", "").strip()
            bounds_str = attrib.get("bounds", "")

            # Filter interactive or text-bearing nodes
            is_interactive = clickable or checkable or scrollable or long_clickable or focusable
            has_content = text or content_desc
            
            # Skip if it is not interactive, has no content, or is a top-level container with no content
            if not (is_interactive or has_content):
                continue
                
            # If it's a layout container without specific text/id, skip unless it's clickable
            if class_name in ["android.widget.FrameLayout", "android.widget.LinearLayout", 
                             "android.widget.RelativeLayout", "android.view.ViewGroup"] and not is_interactive and not has_content:
                continue

            x1, y1, x2, y2 = self.parse_bounds(bounds_str)
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                continue # ignore elements with no area

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            elements.append({
                "id": element_id,
                "text": text,
                "content_desc": content_desc,
                "resource_id": resource_id,
                "class_name": class_name,
                "bounds": [x1, y1, x2, y2],
                "center": [cx, cy],
                "clickable": clickable,
                "scrollable": scrollable,
                "focusable": focusable
            })
            element_id += 1

        return elements

    def get_annotated_screenshot(self) -> tuple[str, list[dict]]:
        """Takes screenshot and draws bounding boxes + IDs for interactive elements."""
        img = self.get_screenshot("pil")
        elements = self.extract_elements()
        
        # Filter elements: keep clickable/focusable elements to avoid too much noise
        interactive_elements = [e for e in elements if e["clickable"] or e["focusable"] or e["scrollable"] or e["text"]]
        
        # We re-assign IDs sequentially for visual clarity in the annotated image
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, otherwise fallback to default
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        annotated_elements = []
        for idx, el in enumerate(interactive_elements):
            el_copy = el.copy()
            el_copy["visual_id"] = idx
            annotated_elements.append(el_copy)
            
            x1, y1, x2, y2 = el["bounds"]
            
            # Draw red bounding box
            draw.rectangle([x1, y1, x2, y2], outline="red", width=2)
            
            # Draw visual ID label
            label = str(idx)
            # Use small black rectangle with white text for readability
            label_w = 20
            label_h = 20
            draw.rectangle([x1, y1, x1 + label_w, y1 + label_h], fill="black")
            draw.text((x1 + 3, y1 + 3), label, fill="white", font=font)
            
        # Convert to RGB if RGBA
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=70)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str, annotated_elements

    def click(self, x: int, y: int):
        if not self.d:
            raise Exception("Device not connected")
        self.d.click(x, y)

    def input_text(self, text: str):
        if not self.d:
            raise Exception("Device not connected")
        try:
            self.d.clear_text()
        except Exception as e:
            print(f"Warning: Failed to clear text: {e}")
        self.d.send_keys(text)

    def press_key(self, key: str):
        if not self.d:
            raise Exception("Device not connected")
        # key can be "enter", "back", "home", "search", etc.
        self.d.press(key)

    def swipe(self, sx: int, sy: int, ex: int, ey: int, steps: int = 10):
        if not self.d:
            raise Exception("Device not connected")
        self.d.swipe(sx, sy, ex, ey, steps=steps)

    def launch_app(self, package_name: str):
        if not self.d:
            raise Exception("Device not connected")
        self.d.app_start(package_name)

    def stop_app(self, package_name: str):
        if not self.d:
            raise Exception("Device not connected")
        self.d.app_stop(package_name)

    def get_current_package(self) -> str | None:
        if not self.d:
            raise Exception("Device not connected")
        try:
            curr = self.d.app_current()
            return curr.get("package") if curr else None
        except Exception:
            return None
