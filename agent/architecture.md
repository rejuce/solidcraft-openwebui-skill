# Architecture — SolidCraft MCP Skill

## Overview

The skill drives SolidCraft (a CAD/CAM desktop app) headlessly by talking to
its **MCP stdio server** over JSON-RPC 2.0. A thin Python driver (`tools/
mcp_driver.py`) launches the stdio bridge via `solidcraft-cli mcp` and speaks
JSON-RPC. A higher-level template (`tools/render_views.py`) shows how to
assemble engine commands and render distinct views.

## Component diagram

```
LLM / OpenWebUI agent
        │  read_skill_file (packaged SKILL.md + tools/)
        ▼
SKILL.md  (instructions, gotchas, schemas)
        │  write packaged files to a temp dir, then exec
        ▼
render_views.py  (orchestration / template)
        │  import
        ▼
mcp_driver.py  (JSON-RPC driver)
        │  subprocess.Popen
        ▼
solidcraft-cli mcp --connect 127.0.0.1:<PORT> --token <token>   (stdio bridge)
        │  bridges to the running SolidCraft app (port auto-discovered)
        ▼
SolidCraft app  (renderer=cpu)
```

## The two execution paths

SolidCraft's MCP server exposes two kinds of commands that the driver treats
differently:

1. **MCP tools** (`inspect_design`, `screenshot`, `new_design`, `save`,
   `list_tools`, `list_commands`, `describe_command`) — sent as a direct
   `tools/call` request via `m.tool(name, arguments)`.

2. **Engine commands** (`sketch.*`, `solid.*`) — these are MCP tools that must
   be **wrapped** and sent through the `batch`/`execute` tool:
   `{"command":"execute","params":{"command":<cid>,"params":{...}}}`. The
   driver exposes this as `m.run(cid, params)` / `m.batch(cmds)`.

Confusing the two is the most common failure. Rule of thumb: anything starting
with `sketch.` or `solid.` → `m.run()`; everything else → `m.tool()`.

## The MCP driver (`mcp_driver.py`)

- `spawn()` — launches `solidcraft-cli mcp` as a Popen stdio process.
- `MCP(proc)` — wraps the process; starts a reader thread that lines-buffered
  parses the JSON-RPC stream and dispatches responses to `_responses`.
- `initialize()` — sends the MCP `initialize` handshake (no `notifications/
  initialized` needed).
- `_send()` — JSON-RPC request with a 60s timeout (1200 × 50ms polls).
- `tool()` — generic `tools/call`.
- `tool_result()` — extracts `result.content[0].text`.
- `list_tools()` — returns the `tools` array.
- `list_commands()` / `describe_command()` — introspect engine commands.
- `batch()` / `ec()` / `run()` — engine-command wrappers.
- `close()` — terminates the bridge.

## Rendering (`render_views.py`)

The `screenshot` tool **ignores `view`** when connected to the running app, so
distinct views require an explicit `camera` object (yaw/pitch/distance/fov) plus
`source:"model"` and `grid:true`. `render_views.py` defines a list of view
dicts and renders each, writing one PNG per view.

## Failure modes (baked into the skill)

- `new_design` restarts the app and drops the MCP connection → start a fresh
  `MCP(proc)` afterwards.
- `screenshot` ignores `view` when connected → explicit `camera` needed.
- Renderer must be `cpu` for the stdio bridge to render correctly.
