from __future__ import annotations

import atexit
import io
import os
import secrets
from typing import Any

import mss
from PIL import Image as PILImage
from mcp.server.fastmcp import FastMCP, Image as MCPImage

from desktop import X11Desktop

HOST = os.getenv("DESKTOPMCP_HOST", "127.0.0.1")
PORT = int(os.getenv("DESKTOPMCP_PORT", "8766"))
TOKEN = os.getenv("DESKTOPMCP_TOKEN", "")
MAX_TYPE_CHARS = 2000

mcp = FastMCP("DesktopMCP")
desktop: X11Desktop | None = None


def get_desktop() -> X11Desktop:
    global desktop
    if desktop is None:
        desktop = X11Desktop()
    return desktop


def cleanup() -> None:
    global desktop
    if desktop is not None:
        desktop.close()
        desktop = None


atexit.register(cleanup)


@mcp.tool()
def screen_info() -> dict[str, Any]:
    """Return the primary desktop dimensions and current session type."""
    with mss.mss() as capture:
        monitor = capture.monitors[1]
        return {
            "width": monitor["width"],
            "height": monitor["height"],
            "session_type": os.getenv("XDG_SESSION_TYPE", "unknown"),
            "desktop": os.getenv("XDG_CURRENT_DESKTOP", "unknown"),
        }


@mcp.tool()
def see_screen() -> MCPImage:
    """Capture the primary monitor and return a PNG screenshot."""
    with mss.mss() as capture:
        monitor = capture.monitors[1]
        shot = capture.grab(monitor)
        image = PILImage.frombytes("RGB", shot.size, shot.rgb)
        image.thumbnail((1920, 1080))
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return MCPImage(data=output.getvalue(), format="png")


@mcp.tool()
def move_cursor(dx: int, dy: int) -> str:
    """Move the independent DesktopMCP pointer by relative screen pixels."""
    if abs(dx) > 3000 or abs(dy) > 3000:
        raise ValueError("Movement is limited to 3000 pixels per action.")
    get_desktop().move(dx, dy)
    return f"Moved independent pointer by ({dx}, {dy}) pixels."


@mcp.tool()
def click(button: str = "left", double: bool = False) -> str:
    """Click with the independent pointer. button must be left, right or middle."""
    get_desktop().click(button, double)
    return f"Clicked {button}."


@mcp.tool()
def mouse_button(button: str, down: bool) -> str:
    """Press or release a mouse button. Use for dragging and always release afterwards."""
    get_desktop().button(button, down)
    return f"{button} button {'pressed' if down else 'released'}."


@mcp.tool()
def scroll(vertical: int = 0, horizontal: int = 0) -> str:
    """Scroll with the independent pointer. Positive vertical values scroll up."""
    if abs(vertical) > 20 or abs(horizontal) > 20:
        raise ValueError("Scroll is limited to 20 wheel steps per action.")
    get_desktop().scroll(vertical, horizontal)
    return "Scroll sent."


@mcp.tool()
def type_text(text: str) -> str:
    """Type text using the independent virtual keyboard and the current US keyboard layout."""
    if len(text) > MAX_TYPE_CHARS:
        raise ValueError(f"Text is limited to {MAX_TYPE_CHARS} characters per call.")
    get_desktop().type_text(text)
    return f"Typed {len(text)} characters. Unsupported characters were skipped."


@mcp.tool()
def key_press(key: str) -> str:
    """Tap a key such as ENTER, ESC, TAB, CTRL, SHIFT, ALT, LEFT, F5 or KEY_A."""
    device = get_desktop()
    device.key(key, True)
    device.key(key, False)
    return f"Pressed {key}."


@mcp.tool()
def release_inputs() -> str:
    """Release mouse buttons and modifier keys after a drag or interrupted action."""
    device = get_desktop()
    for button in ("left", "right", "middle"):
        try:
            device.button(button, False)
        except Exception:
            pass
    for key in ("CTRL", "SHIFT", "ALT", "SUPER"):
        try:
            device.key(key, False)
        except Exception:
            pass
    return "Released held buttons and modifiers."


class BearerGuard:
    """Optional bearer-token guard for the HTTP MCP endpoint."""
    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") != "/health":
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"authorization", b"").decode("utf-8", "ignore")
            if not secrets.compare_digest(supplied, "Bearer " + self.token):
                body = b'{"error":"Unauthorized"}'
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    import uvicorn

    if HOST not in ("127.0.0.1", "localhost", "::1") and not TOKEN:
        raise SystemExit("Refusing non-loopback binding without DESKTOPMCP_TOKEN.")
    app = mcp.streamable_http_app()
    if TOKEN:
        app = BearerGuard(app, TOKEN)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
