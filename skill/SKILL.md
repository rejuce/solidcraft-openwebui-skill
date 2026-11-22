---
name: SolidCraft MCP Skill
description: Build and render 3D floor-plan models in SolidCraft by driving its MCP stdio server over JSON-RPC. Use when asked to create, modify, or render a SolidCraft design — e.g. a building floor plan with rooms, walls, openings, labels, or multi-angle PNG renders (iso/top/fit).
---

# SolidCraft MCP Skill

Drive **SolidCraft** (a CAD/CAM desktop app) headlessly via its **MCP stdio
server** using standard JSON-RPC 2.0. This lets you build 3D models and
render them to PNG from the command line — no GUI interaction required.

The MCP server is a stdio process launched by `solidcraft-cli` that bridges to
the running SolidCraft app. This skill does **not** start the SolidCraft app
itself — the app must already be running. It currently listens on
`127.0.0.1:27878` (a previous run used `7878`; the port can change between
installs). **Do not hard-code a port** — the bundled driver auto-discovers it
(see below).

## Prerequisites

- SolidCraft app running with renderer set to `cpu` (headless server).
- `solidcraft-cli` at
  `/home/user/solidcraft-work/solidcraft-0.22.0-linux-x86_64/bin/solidcraft-cli`.
- Control files in `~/.local/share/solidcraft/control/` (`current.port`,
  `<port>.token`). The driver reads these automatically.
- Python 3 (standard library only — no external dependencies).

## The two execution paths (CRITICAL)

SolidCraft's MCP exposes two kinds of commands. **They must not be confused:**

1. **MCP tools** — called directly via `m.tool(name, arguments)`:
   `inspect_design`, `screenshot`, `new_design`, `save`, `list_tools`,
   `list_commands`, `describe_command`, **`batch`**, **`execute`**.
2. **Engine commands** — `sketch.*` and `solid.*` — which are NOT in the tool
   list (they are *schemas* from `list_commands()`). They are run by wrapping
   them as `{"command":"execute","params":{"command":<cid>,"params":{...}}}` and
   sending the **live `batch` MCP tool** via `m.run()` / `m.batch()`.

Rule of thumb: if the command starts with `sketch.` or `solid.`, use
`m.run()` / `m.batch()`. Otherwise use `m.tool()`.

> ⚠️ **Verify tools against the LIVE app, not the schema dump.**
> `list_commands()` returns engine-command *schemas* (a 245 KB list of
> `sketch.*`/`solid.*` definitions). That is **not** the list of live MCP
> tools. To check whether a tool like `batch` or `screenshot` actually exists,
> call `m.list_tools()` — that returns the authoritative live tool list.
>
> > ⚠️ **Do NOT reinvent the driver.** The bundled `mcp_driver.py`
> > auto-discovers the port and token from the control files, so it works
> > regardless of whether the app is on 7878 or 27878. If something fails,
> > **fix the bundled driver** (copy it to your temp dir and patch the one
> > broken line) — do **not** write your own inline JSON-RPC bridge. Writing a
> > custom bridge is the #1 cause of failure here.

## How to run

> ⚠️ **Never read, edit, or execute from the development repository.** The
> `tools/` folder in the development repo is this skill's **source**, not what
> you run. The files you run are the **packaged** skill served to you by
> `read_skill_file`; they are **not** directly readable by `run_command`, and
> you are always the relay between them. To execute them safely:

1. **Read** the tool files via `read_skill_file` (or `view_skill`):
   `tools/mcp_driver.py` and `tools/render_views.py`.
2. **Write** them to a **temporary** working directory — never into the
   development repo. Create it fresh each run:
   ```bash
   WORKDIR="$(mktemp -d)"
   ```
3. **Execute** from that temporary directory:
   ```bash
   cd "$WORKDIR"
   python3 -c "import sys; sys.path.insert(0, '.'); import mcp_driver as d; ..."
   ```
4. **Clean up** afterwards:
   ```bash
   rm -rf "$WORKDIR"
   ```

Because `render_views.py` imports `mcp_driver` at the top, both files must be
present in the temp directory together before executing — hence the
write-then-run workflow.

## Command schemas (verified)

### `solid.box` (engine command → `m.run()` / `m.batch()`)
- Units are **millimetres**.
- `length`, `width`, `height` — box dimensions.
- `center: [x, y, z]` — centre point in mm.
- `operation`: `"join"` (default) or `"cut"`. Joins merge into a single body.

### `sketch.create` (engine command → `m.run()`)
- Plane needs **both** `x_dir` and `y_dir` **and** `origin`.

### `sketch.text` (engine command → `m.run()`)
- `text` — the label text; `
` breaks lines.
- `at: [x, y]` — baseline start position.
- `height` — capital height in mm.
- `align`: `left` | `center` | `right`.

### `screenshot` (MCP tool → `m.tool()`)
- `view`: iso / home / front / back / top / bottom / left / right / fit
  (**see the rendering gotcha below — `view` is ignored when connected**).
- `camera`: `{target:[x,y,z], yaw, pitch, distance, fov}` — explicit camera.
- `source`: `"window"` (default, ignores `view`) vs `"model"`.
- `grid`, `axes`, `width`, `height` — rendering options.

## Rendering gotcha (the most common failure)

When connected to the running app, the `screenshot` tool **ignores the `view`
parameter** and captures the window by default — so a `view:"top"` and a
`view:"iso"` render come out **byte-identical**.

**Fix:** pass an explicit `camera` object with a *different* yaw/pitch/
distance/fov per view, plus `source:"model"` and `grid:true`. Example:

```python
m.tool("screenshot", {
    "camera": {"target": [4750, 17000, 1000], "yaw": 0.7, "pitch": 0.6,
               "distance": 45000, "fov": 0.6},
    "source": "model", "grid": True, "width": 1600, "height": 1000,
})
```

## `new_design` gotcha

`new_design` **restarts the app**, which drops the MCP connection mid-script.
Do **not** call it in the middle of a build script. Instead:
1. Call `m.tool("new_design", {})`.
2. Wait for the app to restart and the MCP connection to drop.
3. Create a **fresh** `mcp_driver.MCP(proc)` instance and reconnect.

## Example: build a floor plan

```python
import sys
sys.path.insert(0, ".")
import mcp_driver as d

proc = d.spawn()
m = d.MCP(proc)

# Floor slab (mm). Joins merge into ONE body.
m.run("solid.box", {"length": 9500, "width": 34000, "height": 300,
                     "center": [4750, 17000, 150], "operation": "join"})

# Perimeter walls (250 thick, 5000 tall, centred at z=2800).
m.run("solid.box", {"length": 9500, "width": 250, "height": 5000,
                     "center": [4750, 125, 2800], "operation": "join"})   # South
m.run("solid.box", {"length": 9500, "width": 250, "height": 5000,
                     "center": [4750, 33875, 2800], "operation": "join"}) # North
m.run("solid.box", {"length": 250, "width": 34000, "height": 5000,
                     "center": [125, 17000, 2800], "operation": "join"})   # West
m.run("solid.box", {"length": 250, "width": 34000, "height": 5000,
                     "center": [9375, 17000, 2800], "operation": "join"})  # East

# Verify the build:
print(m.tool("inspect_design", {}))

# Labels — single sketch with multiple `align:center` text labels.
m.run("sketch.text", {"text": "Landwirtsch. Gerätehalle",
                      "at": [4750, 17000], "height": 800, "align": "center"})

m.close()
```

## Example: render distinct views

```bash
cd "$WORKDIR"
python3 render_views.py /workspace
```

This writes `floorplan_iso.png`, `floorplan_top.png`, and `floorplan_fit.png`
with genuinely distinct cameras. Verify distinctness with `md5sum`.

## Pitfalls

- **Never execute from or edit the development repo:** the repo's `tools/`
  folder is this skill's source. Read the packaged files via `read_skill_file`,
  write them to a temp directory, execute from there, and clean up.
- **`m.run()` vs `m.tool()`:** `sketch.*` and `solid.*` are engine commands →
  `m.run()` / `m.batch()`. Everything else (`screenshot`, `inspect_design`,
  `new_design`, `save`) → `m.tool()`.
- **`screenshot` ignores `view` when connected:** always pass an explicit
  `camera` + `source:"model"` + `grid:true` for distinct views.
- **`new_design` restarts the app:** start a fresh MCP session afterwards.
- **Renderer must be `cpu`:** the app is driven headless; a GPU renderer will
  not render correctly over the stdio bridge.
- **Verify, don't assume:** check `inspect_design` (body count, volume, bbox)
  and `md5sum` the renders to confirm they are distinct and non-empty.

## Verification

After building, confirm the model is a single body with the expected geometry:

```bash
cd "$WORKDIR"
python3 -c "import sys; sys.path.insert(0, '.'); import mcp_driver as d; p=d.spawn(); m=d.MCP(p); print(m.tool('inspect_design', {})); m.close()"
```

After rendering, confirm distinctness:

```bash
md5sum /workspace/floorplan_iso.png /workspace/floorplan_top.png /workspace/floorplan_fit.png
```

Three different hashes + non-zero file sizes prove the skill and its bundled
tool files are correctly installed and functional.
