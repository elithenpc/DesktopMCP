from __future__ import annotations
import os, re, shutil, subprocess, time
from typing import Optional
try:
    from evdev import UInput, ecodes as e
except ImportError:
    UInput = None
    e = None

class DesktopError(RuntimeError):
    pass

class X11Desktop:
    """Separate XInput master pointer/keyboard backed by virtual uinput devices."""
    def __init__(self):
        self.master_pointer: Optional[int] = None
        self.master_keyboard: Optional[int] = None
        self.mouse = self.keyboard = None
        self._closed = False
        self._check_environment()
        self._create_master()
        try:
            self._create_virtual_devices()
            self._attach_devices()
        except Exception:
            self.close()
            raise

    @staticmethod
    def _run(args, check=True):
        p = subprocess.run(args, text=True, capture_output=True)
        if check and p.returncode:
            raise DesktopError((p.stderr or p.stdout).strip() or "Command failed: " + " ".join(args))
        return p.stdout

    @staticmethod
    def _check_environment():
        if os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
            raise DesktopError("Independent virtual cursors currently require an X11 session.")
        if not os.environ.get("DISPLAY"):
            raise DesktopError("DISPLAY is not set. Start DesktopMCP from your logged-in desktop session.")
        if not shutil.which("xinput"):
            raise DesktopError("xinput is missing. Install it with: sudo apt install xinput")
        if UInput is None:
            raise DesktopError("python-evdev is missing. Install dependencies with: pip install -r requirements.txt")
        if not os.path.exists("/dev/uinput"):
            raise DesktopError("/dev/uinput is unavailable. Run: sudo modprobe uinput")

    def _devices(self):
        return self._run(["xinput", "list", "--short"])

    def _create_master(self):
        self._run(["xinput", "create-master", "DesktopMCP AI"])
        deadline = time.time() + 3
        while time.time() < deadline:
            output = self._devices()
            p = re.search(r"DesktopMCP AI pointer\s+id=(\d+)", output)
            k = re.search(r"DesktopMCP AI keyboard\s+id=(\d+)", output)
            if p and k:
                self.master_pointer, self.master_keyboard = int(p.group(1)), int(k.group(1))
                return
            time.sleep(0.1)
        raise DesktopError("Xorg did not create the DesktopMCP master pointer and keyboard.")

    def _wait_slave(self, name):
        deadline = time.time() + 5
        while time.time() < deadline:
            output = self._devices()
            match = re.search(re.escape(name) + r".*id=(\d+)\s+\[slave\s+(?:pointer|keyboard)", output)
            if match:
                return int(match.group(1))
            time.sleep(0.1)
        raise DesktopError("Xorg did not expose virtual input device: " + name)

    def _create_virtual_devices(self):
        mouse_caps = {
            e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL],
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA],
        }
        keyboard_caps = {e.EV_KEY: list(range(e.KEY_ESC, e.KEY_MICMUTE + 1))}
        self.mouse = UInput(mouse_caps, name="DesktopMCP Virtual Mouse", version=1)
        self.keyboard = UInput(keyboard_caps, name="DesktopMCP Virtual Keyboard", version=1)

    def _attach_devices(self):
        mouse_id = self._wait_slave("DesktopMCP Virtual Mouse")
        keyboard_id = self._wait_slave("DesktopMCP Virtual Keyboard")
        self._run(["xinput", "reattach", str(mouse_id), str(self.master_pointer)])
        self._run(["xinput", "reattach", str(keyboard_id), str(self.master_keyboard)])

    def _emit(self, device, event_type, code, value):
        device.write(event_type, code, value)
        device.syn()

    def move(self, dx, dy):
        if not self.mouse:
            raise DesktopError("Virtual mouse is not initialised.")
        self.mouse.write(e.EV_REL, e.REL_X, int(dx))
        self.mouse.write(e.EV_REL, e.REL_Y, int(dy))
        self.mouse.syn()

    def click(self, button="left", double=False):
        if not self.mouse:
            raise DesktopError("Virtual mouse is not initialised.")
        codes = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
        if button not in codes:
            raise DesktopError("Button must be left, right or middle.")
        code = codes[button]
        for _ in range(2 if double else 1):
            self._emit(self.mouse, e.EV_KEY, code, 1)
            self._emit(self.mouse, e.EV_KEY, code, 0)
            if double:
                time.sleep(0.06)

    def button(self, button, down):
        if not self.mouse:
            raise DesktopError("Virtual mouse is not initialised.")
        codes = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
        if button not in codes:
            raise DesktopError("Button must be left, right or middle.")
        self._emit(self.mouse, e.EV_KEY, codes[button], 1 if down else 0)

    def scroll(self, vertical=0, horizontal=0):
        if not self.mouse:
            raise DesktopError("Virtual mouse is not initialised.")
        if vertical:
            self.mouse.write(e.EV_REL, e.REL_WHEEL, int(vertical))
        if horizontal:
            self.mouse.write(e.EV_REL, e.REL_HWHEEL, int(horizontal))
        self.mouse.syn()

    def key(self, key_name, down):
        if not self.keyboard:
            raise DesktopError("Virtual keyboard is not initialised.")
        name = key_name.upper()
        aliases = {"ENTER":"KEY_ENTER", "RETURN":"KEY_ENTER", "ESC":"KEY_ESC",
                   "ESCAPE":"KEY_ESC", "SPACE":"KEY_SPACE", "TAB":"KEY_TAB",
                   "BACKSPACE":"KEY_BACKSPACE", "DELETE":"KEY_DELETE",
                   "LEFT":"KEY_LEFT", "RIGHT":"KEY_RIGHT", "UP":"KEY_UP",
                   "DOWN":"KEY_DOWN", "CTRL":"KEY_LEFTCTRL", "CONTROL":"KEY_LEFTCTRL",
                   "SHIFT":"KEY_LEFTSHIFT", "ALT":"KEY_LEFTALT", "SUPER":"KEY_LEFTMETA"}
        code_name = aliases.get(name, name if name.startswith("KEY_") else "KEY_" + name)
        code = getattr(e, code_name, None)
        if code is None:
            raise DesktopError("Unsupported key: " + key_name)
        self._emit(self.keyboard, e.EV_KEY, code, 1 if down else 0)

    def type_text(self, text):
        if not self.keyboard:
            raise DesktopError("Virtual keyboard is not initialised.")
        mapping = {}
        for ch, code in zip("abcdefghijklmnopqrstuvwxyz", range(e.KEY_A, e.KEY_Z + 1)):
            mapping[ch], mapping[ch.upper()] = (code, False), (code, True)
        digit_codes = [e.KEY_1,e.KEY_2,e.KEY_3,e.KEY_4,e.KEY_5,e.KEY_6,e.KEY_7,e.KEY_8,e.KEY_9,e.KEY_0]
        for ch, code in zip("1234567890", digit_codes):
            mapping[ch] = (code, False)
        for ch, code in zip("!@#$%^&*()", digit_codes):
            mapping[ch] = (code, True)
        mapping.update({
            " ":(e.KEY_SPACE,False), "\n":(e.KEY_ENTER,False), "\t":(e.KEY_TAB,False),
            "-":(e.KEY_MINUS,False), "_":(e.KEY_MINUS,True), "=":(e.KEY_EQUAL,False),
            "+":(e.KEY_EQUAL,True), "[":(e.KEY_LEFTBRACE,False), "{":(e.KEY_LEFTBRACE,True),
            "]":(e.KEY_RIGHTBRACE,False), "}":(e.KEY_RIGHTBRACE,True),
            ";":(e.KEY_SEMICOLON,False), ":":(e.KEY_SEMICOLON,True),
            "'":(e.KEY_APOSTROPHE,False), '"':(e.KEY_APOSTROPHE,True),
            "~":(e.KEY_GRAVE,True), "\\":(e.KEY_BACKSLASH,False),
            "|":(e.KEY_BACKSLASH,True), ",":(e.KEY_COMMA,False),
            "<":(e.KEY_COMMA,True), ".":(e.KEY_DOT,False), ">":(e.KEY_DOT,True),
            "/":(e.KEY_SLASH,False), "?":(e.KEY_SLASH,True),
        })
        for ch in text:
            item = mapping.get(ch)
            if item is None:
                continue
            code, use_shift = item
            if use_shift:
                self._emit(self.keyboard, e.EV_KEY, e.KEY_LEFTSHIFT, 1)
            self._emit(self.keyboard, e.EV_KEY, code, 1)
            self._emit(self.keyboard, e.EV_KEY, code, 0)
            if use_shift:
                self._emit(self.keyboard, e.EV_KEY, e.KEY_LEFTSHIFT, 0)

    def close(self):
        if self._closed:
            return
        self._closed = True
        for dev in (self.mouse, self.keyboard):
            try:
                if dev:
                    dev.close()
            except Exception:
                pass
        self.mouse = self.keyboard = None
        if self.master_pointer is not None:
            try:
                self._run(["xinput", "remove-master", str(self.master_pointer),
                           "AttachToMaster", "2", "3"], check=False)
            except Exception:
                pass

    def __del__(self):
        self.close()
