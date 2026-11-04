# DesktopMCP

An MCP server that lets a connected AI inspect your Linux desktop and control a separate virtual X11 pointer and keyboard. Your physical mouse remains independent.

## Tools

- screen_info: primary monitor dimensions and session details.
- see_screen: screenshot of the primary monitor.
- move_cursor: relative movement of the independent pointer.
- click: left, right or middle click.
- mouse_button: press/release for dragging.
- scroll: vertical and horizontal scrolling.
- type_text: ordinary text on a US keyboard layout.
- key_press: tap a named key.
- release_inputs: release held mouse buttons and modifiers.

## Requirements

- Linux with an active Xorg/X11 desktop session.
- Python 3.10 or newer.
- xinput, /dev/uinput, and permission to access /dev/uinput.
- Start from the logged-in desktop session. Do not run the server with sudo.

Wayland is not supported by this first backend. It needs a separate portal/compositor implementation.

## Install on Linux Mint

    sudo apt update
    sudo apt install -y python3-venv python3-pip xinput
    sudo modprobe uinput
    sudo usermod -aG input "$USER"

Log out and back in once after adding your account to the input group. Then:

    git clone https://github.com/elithenpc/DesktopMCP.git
    cd DesktopMCP
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python server.py

The MCP endpoint is http://127.0.0.1:8766/mcp.

If /dev/uinput is still inaccessible, check:

    ls -l /dev/uinput
    groups

Do not run the server as root. The server creates a paired XInput master and virtual mouse/keyboard, attaches the virtual devices to that master, and removes the master on shutdown.

## Connecting from ChatGPT

A remote ChatGPT MCP connection needs a URL reachable by ChatGPT over HTTPS. 127.0.0.1 is only reachable from your laptop, and a private Tailscale IP is not normally reachable from OpenAI servers.

For a temporary public HTTPS endpoint, use a secure tunnel such as Tailscale Funnel or Cloudflare Tunnel. If exposing the server beyond localhost, set a long random bearer token and bind only as needed:

    export DESKTOPMCP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    export DESKTOPMCP_HOST=0.0.0.0
    export DESKTOPMCP_PORT=8766
    python server.py

The HTTP MCP endpoint then requires Authorization: Bearer followed by the token. Keep the token private. Do not expose an unauthenticated desktop-control server to the internet. Confirm that your ChatGPT MCP connection method supports bearer-token authentication before exposing it.

## Safety

This server can control the active desktop. Only connect it to an MCP client you trust. Keep it bound to loopback unless you have configured a secure tunnel and authentication. Ask before consequential actions such as sending messages, submitting forms, deleting files or making purchases.

## Current limitations

- X11 only; Wayland needs a separate backend.
- Pointer movement is relative, keeping the physical mouse independent.
- Text entry supports common printable characters on a US keyboard layout.
- Screen capture returns the primary monitor.
- This is an early implementation. Test pointer and keyboard behaviour before relying on it for important work.
