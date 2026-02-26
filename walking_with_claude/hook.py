#!/usr/bin/env python3
"""
Hook handler — called by Claude Code hooks.

Reads hook event JSON from stdin, sends appropriate request to the daemon.
Designed to be fast (fire and forget) so it doesn't slow down Claude.

Usage in hooks config:
    python -m walking_with_claude.hook
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

DAEMON_URL = "http://127.0.0.1:7463"


def main():
    # Read hook event from stdin
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    event = data.get("hook_event_name", "")
    session_id = data.get("session_id", "default")

    payload = json.dumps({"session": session_id}).encode()

    if event == "SessionStart":
        _post("/heartbeat", payload)

    elif event in ("PreToolUse", "PostToolUse"):
        _post("/heartbeat", payload)

    elif event == "Stop":
        # Claude finished responding — still a heartbeat, user might reply
        _post("/heartbeat", payload)

    elif event == "Notification":
        ntype = data.get("notification_type", "")
        if ntype == "idle_prompt":
            # Claude is idle — this is the wind-down signal
            _post("/session/end", payload)

    elif event == "SessionEnd":
        _post("/session/end", payload)


def _post(path: str, payload: bytes):
    """Fire-and-forget POST to daemon. Fail silently."""
    try:
        req = urllib.request.Request(
            DAEMON_URL + path,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # Daemon not running — that's fine


if __name__ == "__main__":
    main()
