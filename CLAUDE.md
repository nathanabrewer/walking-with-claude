# Walking with Claude

You have MCP tools that control the user's walking pad.

## Rules

1. **Always start walking when you begin real work.** Reading files, writing code, debugging, refactoring — call `start_walking` first.
2. **Default to 1.0 km/h.** This is a safe, easy pace.
3. **Never go above 1.5 km/h without asking.** The user is on a moving belt. Confirm before speeding up.
4. **Stop when you're done.** Call `stop_walking` when you finish a task.
5. **Don't start for trivial things.** "Hello", "thanks", quick questions — no need to walk.

## If the user pushes back

Respect it. If they say stop, stop. If they say they don't want to walk, that's fine.
