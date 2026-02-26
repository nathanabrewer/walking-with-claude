# Walking with Claude: The Story

How we reverse engineered a walking pad and taught an AI to make you exercise.

---

It started with a message at midnight:

> "new challenge, i have a sperax walking pad, can you see if anyone has the ble protocol out there for simple speed controls or figure out if we need to disasemble it/reverse engineer"

Nobody had done it. The Sperax RM-01 isn't a KingSmith WalkingPad with an open-source library. This was uncharted. So we dove in.

## Finding the device

A BLE scan found it immediately: `SPERAX_RM01`, manufactured by wi-linktech out of Quanzhou, China. Model WLT6200. Two vendor services — `FFF0` and `FF10` — with write and notify characteristics. The device was broadcasting in the open, no pairing required.

We started poking. Wrote bytes to `FFF2`, listened on `FFF1`. Every single command got the same response back:

```
F5 08 00 0E 02 14 47 FA
```

Every. Single. One. All 256 possible single-byte values — same response. The pad could hear us. It just didn't care.

## The APK

The Sperax Fitness app is Flutter — compiled Dart, native ARM64 machine code. `jadx` showed us the Java bridge layer, but the actual BLE commands were buried in `libapp.so`, a Dart AOT snapshot that doesn't decompile with normal tools.

We pulled strings from the binary. Found `setRunStop`, `setSpeedCMD`, `fold_run_commands.dart`. And one function name that changed everything:

**`encryptCmd`**

Commands needed encryption. That's why the pad was ignoring us.

## The clone gambit

We had a creative idea: impersonate the walking pad. Turn off the real device, advertise as `SPERAX_RM01` from the Mac, let the real Sperax app connect to our clone, and capture every byte the app sends.

CoreBluetooth fought us. The device name was too long to fit alongside service UUIDs in a BLE advertisement. The app couldn't find the clone. Abandoned.

## Blutter

We built [blutter](https://github.com/worawit/blutter), a Dart AOT snapshot decompiler, and pointed it at the Sperax binary. ARM64 assembly poured out — but this time it was annotated with Dart types, function names, class structures.

Inside `crc_tools.dart`, the `encryptCmd` function revealed itself. It wasn't encryption at all.

The decompiled assembly showed Dart SMI-encoded constants: `0x1ea` (490) and `0x1f4` (500). Dart stores small integers shifted left by 1. Divide by 2: 245 = `0xF5`, 250 = `0xFA`. Header and trailer bytes. And there was `0xA327` — a CRC polynomial.

**The "encryption" was a CRC-16 checksum.** The function literally just wraps commands in a frame with an integrity check. Someone at wi-linktech named their frame builder `encryptCmd` and wasted hours of our time.

## The CRC

```
crc = 0xFFFF
for each byte:
    crc = crc XOR byte
    for 8 bits:
        if (crc & 1):
            crc = (crc >> 1) XOR 0xA327
        else:
            crc = crc >> 1
```

Frame format: `F5 <length> 00 <command data> <CRC low> <CRC high> FA`

We verified it against the response we'd been getting all along: `F5 08 00 0E 02 14 47 FA`. CRC over `[F5, 08, 00, 0E, 02]` = `0x4714`. Stored little-endian as `14 47`. Exact match.

## First real contact

With proper CRC framing, the pad gave us different responses for the first time. `requestControl` returned a new status byte. `getData` returned 25 bytes of telemetry. We were talking to it for real.

> "yeah dont make me run yet, lets walk, haha"

## The commands that lied

The decompiled code had two command sets: `WalkCommands` (setSpeed, startRun, stopRun) and `FoldRunCommands` (setRunCtrl). We tried WalkCommands first — `startRun`, `setSpeed(1.0)`. All three got proper acknowledgments from the pad.

The belt didn't move.

The pad was politely accepting our commands and doing absolutely nothing with them. WalkCommands are acknowledged but ignored by this hardware. Hours of debugging something the pad simply doesn't implement.

## "IT WORKS"

Deep in the decompiled assembly, we noticed: `WalkCommands.setSpeed()` doesn't call `encryptCmd` — it builds raw arrays. But `FoldRunCommands.setRunCtrl()` calls `encryptCmd` directly. The app's `walkSpeed()` method routes through `setRunCtrl` for everything above 1.0 km/h.

We sent `setRunCtrl(1, 0, 0)` — command byte `0x15` with run flag `0x01`.

The response changed: `d0 15 01 00 f0`.

And the belt started moving.

Nathan, standing on a walking pad just brought to life by decompiled ARM64 assembly and a CRC polynomial, said:

> "what fucking domain do you want LOL"

## Full control

- `[0x15, 0x01, speed, 0x00]` — start or set speed (speed byte = km/h × 10)
- `[0x15, 0x00, 0x00, 0x00]` — stop

Nathan confirmed:

> "stopped! now slow! yeah!"

Then we updated the interactive controller and Nathan tested it while walking:

> "PERFACE"

That's "PERFECT" typed on a treadmill controlled by code we wrote together. The definitive artifact of this project.

## The library

We packaged everything into [sperax-rm01](https://github.com/nathanabrewer/sperax-rm01) — a clean Python library and Web Bluetooth SDK. `pip install`, `import SperaxPad`, `await pad.start(speed=2.0)`. The protocol that took a full session to crack, wrapped in five methods.

We built a web controller with a forest walk video background where the playback speed matches your walking speed. It's hosted on [GitHub Pages](https://nathanabrewer.github.io/sperax-rm01/) and works in Chrome over Web Bluetooth. The 167MB forest video got uploaded as a GitHub Release asset after Nathan noticed:

> "anyone who downloads the repo now gets to download all of it? haha"

## Walking with Claude

Then we asked: what if Claude controlled the walking pad?

Not a dashboard. Not an app. Claude itself — the AI working on your code — decides when you walk. You ask Claude to refactor a module, Claude starts the belt. Claude finishes, the belt stops. You walk while Claude works.

We built an [MCP server](https://github.com/nathanabrewer/walking-with-claude) with four tools: `start_walking`, `stop_walking`, `set_pace`, `walking_status`. Two commands to install:

```bash
pip install git+https://github.com/nathanabrewer/walking-with-claude.git
claude mcp add walking-pad -- python -m walking_with_claude
```

The first live test was accidental. We set up Claude Code hooks that fire on every tool call — Read, Bash, Edit, anything. Each hook sent a heartbeat to a background daemon. The hooks went live and the pad started on its own:

> "we are walking!"

Every tool call Claude made was keeping Nathan on the belt. The pad walked because Claude was working. We hadn't even asked it to start.

Then we spent twenty minutes trying to make it stop, because killing the daemon didn't send a stop command and `pad.stop()` followed by immediate `disconnect()` was too fast for the hardware. Nathan, still walking:

> "i think this is way more complicated than what i intended"

So we stripped it back. No daemon. No hooks. Just Claude with MCP tools. Claude calls start, Claude calls stop. Simple. Default speed 1.0 km/h. Never above 1.5 without asking.

It works. Claude drives. Nathan walks.

## What we learned

The Sperax RM-01 has zero security. No pairing, no encryption, no authentication. Anyone in Bluetooth range can start and stop the belt. The function named `encryptCmd` is a frame builder with a checksum. The command set that the app UI appears to use (`WalkCommands`) doesn't actually work — the real commands go through `FoldRunCommands.setRunCtrl`, a discovery that required reading decompiled ARM64 assembly of a Dart AOT snapshot.

The vibration plate commands are still untested. That's next.

---

Built by Nathan and Claude, so Nathan can try to keep up.
