#!/usr/bin/env python3
"""
pad.py -- non-interactive one-shot controller for the Sperax RM-01 walking pad.

Each invocation does exactly one thing and exits, so it is safe to call from a
Claude Code skill (no REPL, no long-lived process, no session reset):

    python pad.py start [speed]   # start belt (default 1.0 km/h, range 0.5-6.0)
    python pad.py pace <speed>    # change speed while walking
    python pad.py stop            # stop the belt
    python pad.py status          # report connection + running state

It discovers the pad over BLE by name ("SPERAX_RM01") -- no pairing or MAC.

Why one-shot works: the pad keeps the belt running after the BLE connection
drops (see sperax-rm01 PROTOCOL.md). So `start` connects, sends the command,
disconnects, and the belt keeps going. `stop` / `pace` / `status` reconnect,
do their one thing, and disconnect again.

Wraps the reverse-engineered `sperax_rm01` library (same API the
walking-with-claude MCP server drives). Install it once with:

    pip install git+https://github.com/nathanabrewer/sperax-rm01.git
"""

from __future__ import annotations

import asyncio
import sys

# --- Hard dependency: the BLE driver. Fail loudly with the exact fix. --------
try:
    from sperax_rm01 import SperaxPad
except ImportError:
    sys.stderr.write(
        "ERROR: the 'sperax_rm01' BLE library is not installed.\n"
        "Install it once with:\n\n"
        "    pip install git+https://github.com/nathanabrewer/sperax-rm01.git\n\n"
    )
    sys.exit(2)

DEVICE_NAME = "SPERAX_RM01"
SPEED_MIN = 0.5
SPEED_MAX = 6.0
DEFAULT_SPEED = 1.0  # safe, easy pace (matches the MCP server default)
STOP_MAX_ATTEMPTS = 3  # confirm-and-retry the stop this many times before warning

# Status states the pad reports in a 0x0E frame (see PROTOCOL.md).
_STATUS_NAMES = {0x00: "ready", 0x01: "running", 0x02: "idle", 0x03: "paused"}


def _clamp(speed: float) -> float:
    return max(SPEED_MIN, min(SPEED_MAX, speed))


async def _teardown_keep_running(pad: SperaxPad) -> None:
    """Disconnect WITHOUT stopping the belt.

    `pad.disconnect()` sends a STOP if it thinks the belt is running, which we
    do NOT want after a `start`/`pace`. Clearing the running flag first makes
    disconnect tear down the keepalive task and BLE link cleanly while leaving
    the belt moving.
    """
    pad._running = False
    await pad.disconnect()


async def cmd_start(speed: float) -> int:
    speed = _clamp(speed)
    pad = SperaxPad()
    await pad.connect()  # raises ConnectionError if the pad is not found
    try:
        await pad.start(speed=speed)  # request-control + set speed
        await asyncio.sleep(0.5)      # let the command land + get acked
        print(f"Walking pad started at {speed} km/h. Belt is moving.")
    finally:
        await _teardown_keep_running(pad)
    return 0


async def cmd_pace(speed: float) -> int:
    speed = _clamp(speed)
    pad = SperaxPad()
    await pad.connect()
    try:
        # Fresh connection: must request control before setRunCtrl takes effect.
        await pad.request_control()
        await asyncio.sleep(0.3)
        await pad.set_speed(speed)
        await asyncio.sleep(0.5)
        print(f"Speed changed to {speed} km/h.")
    finally:
        await _teardown_keep_running(pad)
    return 0


async def cmd_stop() -> int:
    """Stop the belt and CONFIRM it actually stopped before reporting success.

    A pad that prints "stopped" while the belt keeps moving is a safety bug, so
    we never trust the stop command blindly:

      1. On a fresh connection the pad IGNORES run-control commands until it has
         GRANTED control, so each attempt requests control first (this is why
         the old blind single `stop()` could no-op on a moving belt yet still
         print success).
      2. After commanding stop we let the belt decelerate, then prompt a fresh
         0x0E run-state frame and read it back. The library's stop() optimisti-
         cally sets running=False, so we rely on the pad's OWN status frame --
         a real "running" frame re-sets pad.running -- not on that flag alone.
      3. If still running (or no state frame arrives) we retry. Only a confirmed
         idle/paused/ready state prints success; otherwise we warn the user to
         step off / use the physical button and exit non-zero.
    """
    state = {"last": None}

    def on_notify(data: bytes) -> None:
        if len(data) >= 5 and data[0] == 0xF5 and data[-1] == 0xFA and data[3] == 0x0E:
            state["last"] = _STATUS_NAMES.get(data[4], f"0x{data[4]:02x}")

    pad = SperaxPad()
    pad.on_notification = on_notify
    await pad.connect()
    confirmed = False
    try:
        for _ in range(STOP_MAX_ATTEMPTS):
            # Grant control first so the run-control STOP is actually honored
            # (a fresh connection has NOT granted control yet), then stop.
            await pad.request_control()
            await asyncio.sleep(0.3)
            await pad.stop()              # sends the stop command twice
            # Let the belt decelerate, then read back a FRESH run-state frame.
            await asyncio.sleep(1.0)
            state["last"] = None
            await pad.request_control()   # prompts a 0x0E status frame
            await asyncio.sleep(1.0)
            # Confirmed only if the pad reports a stopped state AND its own
            # running flag (re-set True by any "running" frame) is clear.
            if state["last"] in ("idle", "paused", "ready") and not pad.running:
                confirmed = True
                break

        if confirmed:
            print("Walking pad stopped. Belt is idle.")
            return 0

        sys.stderr.write(
            "WARNING: could not confirm the walking pad stopped.\n"
            "  The belt may STILL BE MOVING -- step off now and press the\n"
            "  physical STOP button on the pad.\n"
        )
        return 1
    finally:
        # Force one more STOP via disconnect() as a last-ditch safety net:
        # the library only stops on disconnect when it thinks it is running, so
        # set the flag to guarantee that final command fires (harmless if the
        # belt is already idle).
        pad._running = True
        await pad.disconnect()


async def cmd_status() -> int:
    last = {"state": None}

    def on_notify(data: bytes) -> None:
        if len(data) >= 5 and data[0] == 0xF5 and data[-1] == 0xFA and data[3] == 0x0E:
            last["state"] = _STATUS_NAMES.get(data[4], f"0x{data[4]:02x}")

    pad = SperaxPad()
    pad.on_notification = on_notify
    await pad.connect()
    try:
        await pad.request_control()  # prompts a 0x0E status frame
        await asyncio.sleep(1.0)      # wait for the notification
        if last["state"] == "running" or pad.running:
            # Note: a fresh connection can't read back the exact speed; the pad
            # only reports running/idle/paused, not the current km/h value.
            print("Walking pad: connected, belt RUNNING.")
        elif last["state"] in (None, "ready", "idle", "paused"):
            print(
                "Walking pad: connected, belt stopped"
                + (f" ({last['state']})." if last["state"] else ".")
            )
        else:
            print(f"Walking pad: connected, state {last['state']}.")
    finally:
        await _teardown_keep_running(pad)  # don't stop the belt just to check it
    return 0


USAGE = (
    "Usage:\n"
    "  python pad.py start [speed]   start belt (default 1.0 km/h, 0.5-6.0)\n"
    "  python pad.py pace <speed>    change speed while walking\n"
    "  python pad.py stop            stop the belt\n"
    "  python pad.py status          report connection + running state\n"
)


async def _dispatch(argv: list[str]) -> int:
    if not argv:
        sys.stderr.write(USAGE)
        return 1

    cmd = argv[0].lower()

    try:
        if cmd == "start":
            speed = float(argv[1]) if len(argv) > 1 else DEFAULT_SPEED
            return await cmd_start(speed)
        if cmd == "pace":
            if len(argv) < 2:
                sys.stderr.write("ERROR: 'pace' needs a speed, e.g. pace 2.0\n")
                return 1
            return await cmd_pace(float(argv[1]))
        if cmd == "stop":
            return await cmd_stop()
        if cmd == "status":
            return await cmd_status()
        sys.stderr.write(f"ERROR: unknown command '{cmd}'.\n{USAGE}")
        return 1
    except ValueError:
        sys.stderr.write("ERROR: speed must be a number, e.g. 2.0\n")
        return 1
    except ConnectionError as e:
        # Pad not found / not powered on. On macOS this also fires when the
        # terminal lacks Bluetooth permission (first run prompts for it).
        sys.stderr.write(
            f"ERROR: could not reach the walking pad ('{DEVICE_NAME}').\n"
            f"  {e}\n"
            "  - Is the pad powered on and nearby?\n"
            "  - macOS first run: allow Bluetooth for your terminal when prompted\n"
            "    (System Settings > Privacy & Security > Bluetooth).\n"
        )
        return 1
    except Exception as e:  # noqa: BLE001 - surface any BLE error clearly
        sys.stderr.write(f"ERROR: {type(e).__name__}: {e}\n")
        return 1


def main() -> None:
    sys.exit(asyncio.run(_dispatch(sys.argv[1:])))


if __name__ == "__main__":
    main()
