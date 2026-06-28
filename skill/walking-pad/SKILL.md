---
name: walking-pad
description: Start, stop, change the pace of, or check the user's Sperax RM-01 walking pad over Bluetooth. Use whenever the user wants to start/stop walking, speed up or slow down the belt, "walk while Claude works", or check the walking pad status. Drives the pad directly with a bundled script - no MCP server and no session restart required.
---

# Walking Pad

Control the user's Sperax RM-01 walking pad (BLE name `SPERAX_RM01`) by running
the bundled `pad.py` script. Each call does one thing and exits. The belt keeps
running after the command exits, so a single `start` is enough - you do not need
to hold a connection.

## Commands

Run these from this skill's directory (the folder containing this file and
`pad.py`):

| Goal | Command |
|------|---------|
| Start walking | `python pad.py start` (default 1.0 km/h) |
| Start at a speed | `python pad.py start 2.0` |
| Change pace while walking | `python pad.py pace 2.5` |
| Stop walking | `python pad.py stop` |
| Check status | `python pad.py status` |

Speed range is `0.5`-`6.0` km/h (values are clamped).

## How to drive it

- When the user asks you to begin real work and walk along, run
  `python pad.py start 1.0`. Then do their task.
- Default to a safe, easy pace: **1.0 km/h**. Do not go above **1.5 km/h**
  without asking the user first.
- Use `pace` to speed up for big tasks or slow down as you wrap up.
- Run `python pad.py stop` when the task is done or the user asks to stop.
- If the user says they do not want to walk, respect it - do not start.

The script prints a clear one-line result and exits non-zero on failure.

## One-time setup

The script wraps the reverse-engineered `sperax_rm01` BLE driver. Install it
once (the script prints this exact line if the import is missing):

```bash
pip install git+https://github.com/nathanabrewer/sperax-rm01.git
```

## macOS Bluetooth gotcha

On macOS, the first BLE use prompts for Bluetooth permission **for the terminal
app** (CoreBluetooth). If that prompt is dismissed or denied, scanning finds
nothing and the script reports "could not reach the walking pad". Fix: allow the
terminal under System Settings > Privacy & Security > Bluetooth, then retry.
Also make sure the pad is powered on and nearby (no pairing or MAC needed).

## Notes

- `start` and `pace` leave the belt running after the script exits (the pad
  holds its speed without an active connection).
- `status` reports `running` vs `stopped`; on a fresh connection the pad only
  reports its run state, not the exact km/h, so the precise speed is shown only
  for a speed you set this session.
