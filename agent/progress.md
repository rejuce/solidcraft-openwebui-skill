# Progress — SolidCraft MCP Skill

Living log of steps taken. Keep this current as the skill evolves.

## 2026-11-22 — Initial skill creation

- Built the skill in `/workspace/repos/solidcraft-openwebui-skill/`.
- Generated a fresh ed25519 deploy key at
  `repos/keys/solidcraft-openwebui-skill/solidcraft-openwebui-skill`
  (private 600, `.pub` 644).
- Authored `SKILL.md` following OpenWebUI skill conventions (frontmatter
  `name`/`description` with "Use when…" triggers).
- Packaged two tool files in `tools/`:
  - `mcp_driver.py` — JSON-RPC driver (spawn, MCP class, run/tool/batch).
  - `render_views.py` — template that renders iso/top/fit with distinct cameras.
- Wrote `README.md`, `requirements.txt` (stdlib-only, runtime deps documented),
  `.gitignore`, `LICENSE` (MIT), `git-push` (deploy-key push helper),
  `agent/architecture.md`, `agent/progress.md`.
- Documented the three protocol gotchas that caused iteration friction:
  1. `m.run()` vs `m.tool()` for engine vs MCP commands.
  2. `screenshot` ignores `view` when connected → explicit `camera` needed.
  3. `new_design` restarts the app → fresh MCP session required.

## Validation status

- Both Python files parse cleanly (`ast.parse` OK).
- SKILL.md/README schemas verified against the actual MCP command output.
- Not yet: live end-to-end run against the running app (requires the app on
  :7878 with renderer=cpu).

## Next steps

- Register the public key on the GitHub repo as a Write-Enabled deploy key,
  then push via `./git-push master`.
- Run `render_views.py` end-to-end against a live design and confirm three
  distinct `md5sum` hashes.
