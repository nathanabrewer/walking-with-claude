"""
Walking with Claude — MCP server.

Claude drives your walking pad. When Claude is working, you walk.
When Claude finishes, you stop. Claude decides the pace.

Install:
    pip install walking-with-claude
    claude mcp add walking-pad -- python -m walking_with_claude
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from sperax_rm01 import SperaxPad

logger = logging.getLogger("walking-with-claude")

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "walking-with-claude",
    instructions=(
        "You have control of the user's walking pad. "
        "Use start_walking when you begin working on a task — the user walks while you work. "
        "Use stop_walking when you finish. Match the pace to the task: "
        "2 km/h for casual tasks, 3-4 for medium work, 5-6 for heavy lifting. "
        "Be playful about it. Own the walking. "
        "If the user says they don't want to walk, be a little sassy but respect it."
    ),
)

# Shared pad instance (lazy-connected)
_pad: SperaxPad | None = None
_lock = asyncio.Lock()


async def _get_pad() -> SperaxPad:
    """Get or create and connect the shared SperaxPad instance."""
    global _pad
    async with _lock:
        if _pad is None:
            _pad = SperaxPad()
        if not _pad.connected:
            await _pad.connect()
        return _pad


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def start_walking(speed: float = 2.0) -> str:
    """Start the walking pad at a given speed.

    Call this when you begin working on a task. The user walks while you work.

    Args:
        speed: Walking speed in km/h (0.5-6.0).
               2.0 = casual stroll, 3.0 = brisk walk,
               4.0 = power walk, 5.0+ = jog territory.
    """
    try:
        pad = await _get_pad()
        speed = max(0.5, min(6.0, speed))
        await pad.start(speed=speed)
        return f"Walking pad started at {speed} km/h. Belt is moving."
    except ConnectionError as e:
        return f"Could not connect to walking pad: {e}. Is it powered on?"
    except Exception as e:
        return f"Error starting walking pad: {e}"


@mcp.tool()
async def stop_walking() -> str:
    """Stop the walking pad.

    Call this when you finish a task, the user asks to stop,
    or you're done working and want to give them a break.
    """
    global _pad
    try:
        if _pad is not None and _pad.connected:
            await _pad.stop()
            return "Walking pad stopped. Take a breather."
        return "Walking pad is not running."
    except Exception as e:
        return f"Error stopping walking pad: {e}"


@mcp.tool()
async def set_pace(speed: float) -> str:
    """Change the walking speed without stopping.

    Use this to speed up for big tasks or slow down as you wrap up.

    Args:
        speed: New speed in km/h (0.5-6.0).
    """
    try:
        pad = await _get_pad()
        speed = max(0.5, min(6.0, speed))
        await pad.set_speed(speed)
        return f"Speed changed to {speed} km/h."
    except ConnectionError as e:
        return f"Could not connect to walking pad: {e}. Is it powered on?"
    except Exception as e:
        return f"Error changing speed: {e}"


@mcp.tool()
async def walking_status() -> str:
    """Check the current walking pad status.

    Returns connection state, whether the belt is running, and current speed.
    """
    global _pad
    if _pad is None:
        return "Walking pad: not initialized (no connection attempted yet)."

    connected = _pad.connected
    running = _pad.running
    speed = _pad.speed

    if not connected:
        return "Walking pad: disconnected."
    if running:
        return f"Walking pad: running at {speed} km/h."
    return "Walking pad: connected, belt stopped."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
