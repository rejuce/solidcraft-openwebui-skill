#!/usr/bin/env python3
"""SolidCraft MCP JSON-RPC driver (stdio bridge to the running app).

Protocol: standard MCP over stdio.
- Call `initialize` first (no notifications/initialized needed).
- Invoke tools via `tools/call` with {"name":..., "arguments":...}.
- Response text is at r["result"]["content"][0]["text"].
- Engine commands (sketch.*, solid.*) are MCP tools that must be run through
  `run()` / `batch()` — they are wrapped as {"command":"execute",...}.
- Special tools (new_design, save, screenshot, inspect_design, list_tools,
  list_commands, describe_command, batch, execute) are called directly via
  `tool()` / `m.tool()`.

BOOTSTRAP (IMPORTANT): spawn() auto-discovers the app port and token from the
control directory (see discover_port / discover_token_path below). It reads
`current.port` and then `<port>.token`. This means the driver works whether the
app is on 7878, 27878, or any other port — do NOT hard-code a port in your own
scripts, and do NOT rewrite the driver. If you must adapt (e.g. a non-standard
install), copy the driver into your temp dir and patch only what is broken.
"""
import json
import os
import subprocess
import sys
import threading
import time

CONTROL_DIR = os.path.expanduser("~/.local/share/solidcraft/control")
DEFAULT_CLI = "/home/user/solidcraft-work/solidcraft-0.22.0-linux-x86_64/bin/solidcraft-cli"
DEFAULT_PORT = 7878


def discover_port(default=DEFAULT_PORT):
    """Return the port the app is actually listening on.

    Reads `current.port` from the control dir. Falls back to `default`
    (7878) if the file is missing or unreadable.
    """
    try:
        with open(os.path.join(CONTROL_DIR, "current.port")) as f:
            return int(f.read().strip().split()[0])
    except Exception:
        return default


def discover_token_path(port):
    """Path to the token file for a given port: control/<port>.token."""
    return os.path.join(CONTROL_DIR, f"{port}.token")


def discover_cli():
    """Locate the solidcraft-cli binary.

    Prefers the known install path, then falls back to a PATH search.
    """
    if os.path.exists(DEFAULT_CLI):
        return DEFAULT_CLI
    for cand in ("solidcraft-cli",):
        for base in (
            "/home/user/solidcraft-work",
            "/home/user/solidcraft-work/solidcraft-0.22.0-linux-x86_64/bin",
        ):
            p = os.path.join(base, cand)
            if os.path.exists(p):
                return p
    return DEFAULT_CLI


def spawn(token_path=None, host="127.0.0.1", port=None, cli=None):
    """Launch `solidcraft-cli mcp` as a Popen stdio process.

    Port and token are auto-discovered unless explicitly overridden.
    """
    if port is None:
        port = discover_port()
    if token_path is None:
        token_path = discover_token_path(port)
    token = open(token_path).read().strip()
    cli = cli or discover_cli()
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
        """Call an MCP tool by name (inspect_design, screenshot, batch, ...)."""
        r = self.call("tools/call", {"name": name, "arguments": arguments or {}})
        return self.tool_result(r)

    def list_tools(self):
        """Return the LIVE list of MCP tools exposed by the running app.

        This is authoritative for which tools exist (batch, execute,
        screenshot, inspect_design, ...). Use this to verify a tool exists
        before calling it — do NOT rely on the engine-command schema dump.
        """
        r = self.call("tools/list", {})
        return json.loads(self.tool_result(r))["tools"]

    def list_commands(self, filter=None):
        """Return engine-command schemas (sketch.*, solid.*). NOT live tools."""
        params = {}
        if filter:
            params["filter"] = filter
        r = self.tool("list_commands", params)
        return json.loads(r)

    def describe_command(self, cid):
        r = self.tool("describe_command", {"id": cid})
        return json.loads(r)

    def batch(self, cmds):
        """Run a batch of engine steps. cmds = list of {command, params} wrappers.

        Sends the live `batch` MCP tool with {"commands": cmds}.
        """
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