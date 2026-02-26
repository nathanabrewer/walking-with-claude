"""
Walking daemon — background process that holds the BLE connection
and responds to heartbeats from Claude Code hooks.

Heartbeat model:
  - Hooks fire curl requests on PreToolUse, SessionStart, etc.
  - Each request resets a timer.
  - No heartbeat for SLOW_AFTER seconds → slow to minimum speed.
  - No heartbeat for STOP_AFTER seconds → stop the belt.

Run:
    python -m walking_with_claude.daemon
    # or
    walking-daemon
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from sperax_rm01 import SperaxPad

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("walking-daemon")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PORT = 7463            # WALK-ish on a phone keypad
SLOW_AFTER = 30.0      # seconds without heartbeat → slow down
STOP_AFTER = 60.0      # seconds without heartbeat → stop
MIN_SPEED = 1.0        # km/h when slowing down
DEFAULT_SPEED = 2.0    # km/h on start

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
pad = SperaxPad()
last_heartbeat: float = 0.0
target_speed: float = DEFAULT_SPEED
sessions: set[str] = set()        # track active session IDs
_watchdog_task: asyncio.Task | None = None


def _state() -> dict[str, Any]:
    return {
        "connected": pad.connected,
        "running": pad.running,
        "speed": pad.speed,
        "target_speed": target_speed,
        "sessions": len(sessions),
        "last_heartbeat_ago": round(time.time() - last_heartbeat, 1) if last_heartbeat else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

async def handle_heartbeat(request: Request) -> JSONResponse:
    """Heartbeat from a Claude Code hook. Keeps the pad running."""
    global last_heartbeat, target_speed

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    session_id = body.get("session", "default")
    speed = body.get("speed", None)

    last_heartbeat = time.time()
    sessions.add(session_id)

    if speed is not None:
        target_speed = max(0.5, min(6.0, float(speed)))

    # Auto-connect and start if not running
    if not pad.connected:
        try:
            await pad.connect()
            log.info("BLE connected")
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=503)

    if not pad.running:
        await pad.start(speed=target_speed)
        log.info(f"Started at {target_speed} km/h")
    elif speed is not None:
        await pad.set_speed(target_speed)

    return JSONResponse({"ok": True, **_state()})


async def handle_start(request: Request) -> JSONResponse:
    """Explicitly start the pad."""
    global last_heartbeat, target_speed

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    speed = body.get("speed", DEFAULT_SPEED)
    target_speed = max(0.5, min(6.0, float(speed)))
    last_heartbeat = time.time()

    if not pad.connected:
        try:
            await pad.connect()
            log.info("BLE connected")
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=503)

    await pad.start(speed=target_speed)
    log.info(f"Started at {target_speed} km/h")
    return JSONResponse({"ok": True, **_state()})


async def handle_stop(request: Request) -> JSONResponse:
    """Stop the pad."""
    global last_heartbeat

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    session_id = body.get("session", None)
    if session_id and session_id in sessions:
        sessions.discard(session_id)

    # Only stop if no active sessions left, or explicit stop
    if session_id is None or len(sessions) == 0:
        if pad.connected and pad.running:
            await pad.stop()
            log.info("Stopped")
        last_heartbeat = 0.0
        sessions.clear()

    return JSONResponse({"ok": True, **_state()})


async def handle_speed(request: Request) -> JSONResponse:
    """Change speed."""
    global target_speed, last_heartbeat

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    speed = body.get("speed", DEFAULT_SPEED)
    target_speed = max(0.5, min(6.0, float(speed)))
    last_heartbeat = time.time()

    if pad.connected and pad.running:
        await pad.set_speed(target_speed)
        log.info(f"Speed → {target_speed} km/h")

    return JSONResponse({"ok": True, **_state()})


async def handle_status(request: Request) -> JSONResponse:
    """Return current state."""
    return JSONResponse(_state())


async def handle_session_end(request: Request) -> JSONResponse:
    """A Claude session ended. Remove it and maybe stop."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    session_id = body.get("session", "default")
    sessions.discard(session_id)
    log.info(f"Session ended: {session_id} ({len(sessions)} remaining)")

    if len(sessions) == 0 and pad.connected and pad.running:
        await pad.stop()
        log.info("All sessions ended — stopped")

    return JSONResponse({"ok": True, **_state()})


# ---------------------------------------------------------------------------
# Watchdog — auto slow/stop on heartbeat timeout
# ---------------------------------------------------------------------------

async def watchdog():
    """Background task: slow down and stop if heartbeats stop coming."""
    global last_heartbeat
    slowed = False

    while True:
        await asyncio.sleep(5)

        if last_heartbeat == 0.0 or not pad.running:
            slowed = False
            continue

        elapsed = time.time() - last_heartbeat

        if elapsed > STOP_AFTER:
            if pad.connected and pad.running:
                await pad.stop()
                log.info(f"No heartbeat for {STOP_AFTER}s — stopped")
                sessions.clear()
            slowed = False

        elif elapsed > SLOW_AFTER and not slowed:
            if pad.connected and pad.running:
                await pad.set_speed(MIN_SPEED)
                log.info(f"No heartbeat for {SLOW_AFTER}s — slowed to {MIN_SPEED} km/h")
            slowed = True


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def _shutdown():
    """Stop the pad and disconnect on server shutdown."""
    log.info("Shutting down — stopping walking pad...")
    if pad.connected and pad.running:
        try:
            await pad.stop()
            log.info("Pad stopped")
        except Exception as e:
            log.warning(f"Error stopping pad: {e}")
    if pad.connected:
        try:
            await pad.disconnect()
            log.info("BLE disconnected")
        except Exception:
            pass


app = Starlette(
    routes=[
        Route("/heartbeat", handle_heartbeat, methods=["POST", "GET"]),
        Route("/start", handle_start, methods=["POST"]),
        Route("/stop", handle_stop, methods=["POST"]),
        Route("/speed", handle_speed, methods=["POST"]),
        Route("/status", handle_status, methods=["GET"]),
        Route("/session/end", handle_session_end, methods=["POST"]),
    ],
    on_startup=[lambda: asyncio.create_task(watchdog())],
    on_shutdown=[_shutdown],
)


def main():
    """Run the walking daemon."""
    import signal

    print(f"""
    ╔══════════════════════════════════════╗
    ║     Walking with Claude — Daemon     ║
    ║                                      ║
    ║  http://localhost:{PORT}              ║
    ║                                      ║
    ║  Waiting for heartbeats...           ║
    ║  Slow after {SLOW_AFTER}s, stop after {STOP_AFTER}s    ║
    ║  Ctrl-C to stop (pad stops too)      ║
    ╚══════════════════════════════════════╝
    """)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
