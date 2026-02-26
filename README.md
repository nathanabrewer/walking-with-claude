# Walking with Claude

Claude controls your walking pad. When Claude works, you walk.

## Install

```bash
pip install git+https://github.com/nathanabrewer/walking-with-claude.git
claude mcp add walking-pad -- python -m walking_with_claude
```

## Compatible device

[<img src="https://sperax.com/cdn/shop/files/P1_1.jpg?v=1767170824&width=2880" width="400" alt="Sperax Walking Vibration Pad">](https://sperax.com/products/p1-walking-vibration-pad?variant=51576446091548)

| | |
|---|---|
| **Product** | [Sperax Walking Vibration Pad (4-in-1)](https://sperax.com/products/p1-walking-vibration-pad?variant=51576446091548) |
| **Model** | WLT6200 (RM-01) |
| **BLE name** | `SPERAX_RM01` |
| **Manufacturer** | wi-linktech (Quanzhou WenTeLai) |
| **Connection** | Bluetooth Low Energy (FFF0 service) |

> Other Sperax models using the same BLE protocol may also work. The BLE device name must be `SPERAX_RM01`.
>
> Verify your pad works with the [Web Bluetooth test page](https://nathanabrewer.github.io/sperax-rm01/) (Chrome required).

## What happens

1. You ask Claude to do something
2. Claude starts the walking pad — you walk
3. Claude works on your task while you walk
4. Claude finishes, stops the pad
5. You stop walking and review the work

Claude picks the speed based on task complexity. Quick fix? Easy stroll at 2 km/h. Major refactor? You're running at 5.

## Requirements

- macOS or Linux
- Python 3.10+
- [Claude Code](https://claude.ai/claude-code)
- A compatible walking pad, powered on and nearby

## How it works

This is an [MCP](https://modelcontextprotocol.io/) server that gives Claude four tools:

| Tool | What it does |
|------|-------------|
| `start_walking(speed)` | Start the belt (0.5-6.0 km/h) |
| `stop_walking()` | Stop the belt |
| `set_pace(speed)` | Change speed mid-task |
| `walking_status()` | Check connection and speed |

Under the hood it uses the [sperax-rm01](https://github.com/nathanabrewer/sperax-rm01) BLE library. First tool call triggers Bluetooth scan and connection (a few seconds). After that, commands are instant.

## The story

Started by reverse engineering a walking pad's Bluetooth protocol — decompiling its Flutter app, cracking a CRC-16 algorithm, and testing commands on live hardware. Then we thought: what if Claude controlled the pad? When Claude works on your code, you walk. When Claude stops, you stop. Claude drives.

Built by Nathan and Claude, so Nathan can try to keep up.

## Vibes

[![](https://img.youtube.com/vi/D8upY-3l0hA/0.jpg)](https://www.youtube.com/watch?v=D8upY-3l0hA)
[![](https://img.youtube.com/vi/qEU_nlLxYXA/0.jpg)](https://www.youtube.com/watch?v=qEU_nlLxYXA)
[![](https://img.youtube.com/vi/aSERfEISn_o/0.jpg)](https://www.youtube.com/watch?v=aSERfEISn_o)
