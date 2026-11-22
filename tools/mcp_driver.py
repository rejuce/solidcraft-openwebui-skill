#!/usr/bin/env python3
"""SolidCraft MCP JSON-RPC driver (stdio bridge to the running app on :7878).

Protocol: standard MCP over stdio.
- Call `initialize` first (no notifications/initialized needed).
- Invoke tools via `tools/call` with {"name":..., "arguments":...}.
- Response text is at r["result"]["content"][0]["text"].
- Engine commands (sketch.*, solid.*) are MCP tools that must be run through
  `run()` / `batch()` — they are wrapped as {"command":"execute",...}.
- Special tools (new_design, save, screenshot, inspect_design, list_tools,
  list_commands, describe_command) are called directly via `tool()` / `m.tool()`.

CRITICAL gotcha: `new_design` causes the app to restart, which drops the MCP
connection mid-script. Do NOT call it in the middle of a build script. Start a
fresh MCP session after `new_design` and reconnect.

CRITICAL gotcha: when connected to the running app, the `screenshot` tool
ignores the `view` parameter and captures the window by default. To get
distinct views (top/iso/fit), pass an explicit `camera` object with distinct
yaw/pitch/distance/fov per view, plus `source:"model"` and `grid:true`.
"""
import json
import subprocess
import sys
import threading
import time


def spawn(token_path="/home/user/.local/share/solidcraft/control/7878.token",
          host="127.0.0.1", port=7878, cli=None):
    token = open(token_path).read().strip()
    cli = cli or "/home/user/solidcraft-work/solidcraft-0.22.0-linux-x86_64/bin/solidcraft-cli"
    proc = subprocess.Popen(
        [cli, "mcp", "--connect", f"{host}:{port}", "--token", token],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
    return proc


class MCP:
    def __init__(self, proc):
        self.proc = proc
        self._id = 0
        self._responses = {}
        self._buf = ""
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()
        self.initialize()

    def _reader(self):
        for line in self.proc.stdout:
            self._buf += line
            while "\n" in self._buf:
                msg, self._buf = self._buf.split("\n", 1)
                msg = msg.strip()
                if not msg:
                    continue
                try:
                    obj = json.loads(msg)
                except Exception:
                    continue
                if obj.get("method") == "notifications/message":
                    sys.stderr.write("[mcp] " + str(obj.get("params", {}).get("message", "")) + "\n")
                    continue
                self._responses[obj.get("id")] = obj

    def _next_id(self):
        self._id += 1
        return self._id

    def _send(self, method, params=None):
        rid = self._next_id()
        self._responses[rid] = None
        req = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        for _ in range(1200):
            if self._responses.get(rid) is not None:
                return self._responses.pop(rid)
            time.sleep(0.05)
        raise TimeoutError(f"timeout waiting for response to {method}")

    def initialize(self):
        return self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "driver", "version": "1.0"},
        })

    def call(self, method, params=None):
        r = self._send(method, params)
        if "error" in r and r["error"] is not None:
            raise RuntimeError(f"error calling {method}: {r['error']}")
        return r

    def tool_result(self, r):
        try:
            return r["result"]["content"][0]["text"]
        except Exception:
            return json.dumps(r.get("result"))

    def tool(self, name, arguments=None):
        """Call an MCP tool by name (inspect_design, screenshot, new_design, ...)."""
        r = self.call("tools/call", {"name": name, "arguments": arguments or {}})
        return self.tool_result(r)

    def list_tools(self):
        r = self.call("tools/list", {})
        return json.loads(self.tool_result(r))["tools"]

    def list_commands(self, filter=None):
        params = {}
        if filter:
            params["filter"] = filter
        r = self.tool("list_commands", params)
        return json.loads(r)

    def describe_command(self, cid):
        r = self.tool("describe_command", {"id": cid})
        return json.loads(r)

    def batch(self, cmds):
        """Run a batch of engine steps. cmds = list of {command, params} wrappers."""
        r = self.tool("batch", {"commands": cmds})
        return r

    def ec(self, cid, params=None):
        """Wrap an engine command (sketch.*, solid.*) for a batch."""
        return {"command": "execute", "params": {"command": cid, "params": params or {}}}

    def run(self, cid, params=None):
        """Execute a single engine command (wrapped in a 1-item batch)."""
        return self.batch([self.ec(cid, params)])

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:
            pass
