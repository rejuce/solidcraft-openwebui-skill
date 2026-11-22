#!/usr/bin/env python3
"""Render multiple distinct views of a SolidCraft design to PNG files.

Usage:
    python3 render_views.py <output_dir>

Reads the driver from the same directory (mcp_driver.py), connects to the
running SolidCraft app on :7878, and writes one PNG per view.

The KEY gotcha this script exists to fix: when connected to the running app,
the `screenshot` tool IGNORES the `view` parameter and captures the window.
To get genuinely distinct views we pass an explicit `camera` object with a
different yaw/pitch/distance/fov per view, plus `source:"model"` and
`grid:true`.

Each view dict:
    {
        "filename": "floorplan_iso.png",
        "camera": {"target": [x, y, z], "yaw": ..., "pitch": ...,
                   "distance": ..., "fov": ...},
        "source": "model", "grid": True,
        "width": 1600, "height": 1000,
    }

Adjust the camera targets/angles to taste. The target is usually the room
centre, e.g. [4750, 17000, 1000] for the hall.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mcp_driver  # noqa: E402


def render(m, view, out_dir):
    """Render one view dict to a PNG. Returns the file path."""
    params = {
        "camera": view["camera"],
        "source": view.get("source", "model"),
        "grid": view.get("grid", True),
        "width": view.get("width", 1600),
        "height": view.get("height", 1000),
    }
    # screenshot is an MCP tool -> call via m.tool() directly.
    m.tool("screenshot", params)
    # Give the renderer a moment to flush the file.
    time.sleep(2)
    path = os.path.join(out_dir, view["filename"])
    if os.path.exists(path):
        return path
    raise RuntimeError(f"expected output not found: {path}")


def main():
    if len(sys.argv) < 2:
        print("usage: render_views.py <output_dir>")
        sys.exit(2)
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)

    # Build a fresh session after new_design. If you haven't built anything yet,
    # call m.tool("new_design", {}) first, wait for the app to restart, then
    # create a NEW MCP(proc) instance and reconnect.
    proc = mcp_driver.spawn()
    m = mcp_driver.MCP(proc)

    views = [
        {
            "filename": "floorplan_iso.png",
            "camera": {"target": [4750, 17000, 1000],
                       "yaw": 0.7, "pitch": 0.6,
                       "distance": 45000, "fov": 0.6},
        },
        {
            "filename": "floorplan_top.png",
            "camera": {"target": [4750, 17000, 1000],
                       "yaw": 0.0, "pitch": 1.45,
                       "distance": 45000, "fov": 0.6},
        },
        {
            "filename": "floorplan_fit.png",
            "camera": {"target": [4750, 17000, 1000],
                       "yaw": -0.9, "pitch": 0.55,
                       "distance": 49500, "fov": 0.6},
        },
    ]

    for v in views:
        path = render(m, v, out_dir)
        print(f"rendered {path}")

    m.close()


if __name__ == "__main__":
    main()
