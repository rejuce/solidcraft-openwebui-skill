# SolidCraft MCP Skill — OpenWebUI Skill

A Python skill package that drives **SolidCraft** (a CAD/CAM desktop app)
headlessly via its **MCP stdio server** using standard JSON-RPC 2.0. It lets an
LLM / OpenWebUI build 3D floor-plan models and render them to PNG — no GUI
interaction required.

This skill does **not** start the SolidCraft app. The app must already be
running with the renderer set to `cpu`. The bundled driver auto-discovers the
app's port and token from the control files, so no port needs to be hard-coded
(currently `127.0.0.1:27878`; a prior install used `7878`).

## Why a skill, not a tool

The friction in driving SolidCraft is **protocol knowledge** — knowing which
commands go through `m.run()` vs `m.tool()`, that `screenshot` ignores `view`
when connected, and that `new_design` restarts the app — not a missing atomic
capability. A skill packages this decision-based knowledge plus tested driver
files, so it adapts to any floor plan or any set of views without re-baking.

## Files

```
solidcraft-openwebui-skill/
├── SKILL.md              ← OpenWebUI / agent skill instructions
├── README.md             ← this file
├── requirements.txt      ← (none — standard library only)
├── .gitignore
├── LICENSE
├── git-push              ← deploy-key push helper
├── tools/
│   ├── mcp_driver.py     ← JSON-RPC driver: spawn, MCP class, run/tool/batch
│   └── render_views.py   ← template: render iso/top/fit with distinct cameras
└── agent/
    ├── architecture.md   ← architecture overview
    └── progress.md       ← living log of steps taken
```

## The two execution paths

SolidCraft's MCP exposes two kinds of commands that **must not be confused**:

1. **MCP tools** — `inspect_design`, `screenshot`, `new_design`, `save`,
   `list_tools`, `list_commands`, `describe_command` → call via `m.tool()`.
2. **Engine commands** — `sketch.*`, `solid.*` → run via `m.run()` / `m.batch()`
   (wrapped as `{"command":"execute","params":{"command":<cid>,"params":{...}}}`).

## Command schemas (verified)

| Command | Path | Key params |
|---------|------|------------|
| `solid.box` | `m.run()` | `length/width/height` (mm), `center:[x,y,z]`, `operation:"join"|"cut"` |
| `sketch.create` | `m.run()` | plane needs **both** `x_dir` **and** `y_dir` + `origin` |
| `sketch.text` | `m.run()` | `text` (`\n` breaks lines), `at:[x,y]`, `height` (capital height mm), `align:left\|center\|right` |
| `screenshot` | `m.tool()` | `camera:{target,yaw,pitch,distance,fov}`, `source:"model"|"window"`, `grid`, `axes`, `width`, `height` |

## Rendering gotcha

When connected to the running app, `screenshot` **ignores `view`** and captures
the window by default — so `view:"top"` and `view:"iso"` come out byte-identical.
**Fix:** pass an explicit `camera` with distinct yaw/pitch/distance/fov per view,
plus `source:"model"` and `grid:true`.

## Pitfalls

- **Never execute from or edit the development repo.** Read packaged files via
  `read_skill_file`, write to a temp dir, execute from there, clean up.
- **`m.run()` vs `m.tool()`:** `sketch.*`/`solid.*` → `m.run()`; everything else
  → `m.tool()`.
- **`screenshot` ignores `view`** when connected — use explicit `camera`.
- **`new_design` restarts the app** — start a fresh MCP session afterwards.

## Usage

```python
import sys
sys.path.insert(0, "/workspace/repos/solidcraft-openwebui-skill/tools")
import mcp_driver as d

proc = d.spawn()
m = d.MCP(proc)
m.run("solid.box", {"length": 9500, "width": 34000, "height": 300,
                    "center": [4750, 17000, 150], "operation": "join"})
print(m.tool("inspect_design", {}))
m.close()
```

Or render distinct views:

```bash
cd /tmp/work && python3 render_views.py /workspace
md5sum /workspace/floorplan_*.png   # three distinct hashes
```

## Verification

```bash
cd /tmp/work
python3 -c "import sys; sys.path.insert(0, '.'); import mcp_driver as d; p=d.spawn(); m=d.MCP(p); print(m.tool('inspect_design', {})); m.close()"
md5sum /workspace/floorplan_iso.png /workspace/floorplan_top.png /workspace/floorplan_fit.png
```

## License

See [LICENSE](LICENSE).
