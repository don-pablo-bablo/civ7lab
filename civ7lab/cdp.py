"""A Chrome DevTools Protocol client, standard library only.

The game's UI runs on Coherent cohtml, which embeds Chrome's inspector
protocol. The `UIDebugger` switch in AppOptions.txt starts the server. With it
on, the game runs JavaScript sent to it and returns the result as JSON.

Only a small part of the protocol is needed: a WebSocket handshake, masked
text frames, and requests matched to replies by id.

    from civ7lab import cdp
    with cdp.connect() as session:
        print(session.evaluate("GameContext.localPlayerID"))
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import socket
import struct
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# The game uses 9444: UI.log reads "Inspector initialized. Remote debugging
# available on port: 9444" (build 25245002, 21 Sep 2026). If a patch moves it,
# set CIV7_CDP_PORT.
DEFAULT_PORTS = (9444,)

ENV_PORT = "CIV7_CDP_PORT"
ENV_HOST = "CIV7_CDP_HOST"


class CDPError(RuntimeError):
    """Anything that went wrong talking to the game."""


class JSException(CDPError):
    """The JavaScript threw. The message is the game's own, such as
    'X is not defined'."""


@dataclass(frozen=True)
class Target:
    """One inspectable UI context. A script exists only in the context that
    loaded it; the gameplay APIs are in fs://game/root-game.html."""

    id: str
    title: str
    url: str
    ws_url: str

    def __str__(self) -> str:
        return f"{self.title or '(untitled)'}  [{self.id}]  {self.url}"


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


def _http_get(url: str, timeout: float = 1.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.URLError, OSError, ValueError:
        return None


def port_is_open(host: str, port: int, timeout: float = 0.2) -> bool:
    with contextlib.closing(socket.socket()) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def find_port(host: str | None = None, ports=None, timeout: float = 0.2) -> int | None:
    """The first port that answers and looks like an inspector."""
    host = host or os.environ.get(ENV_HOST, "127.0.0.1")
    env_port = os.environ.get(ENV_PORT)
    candidates = [int(env_port)] if env_port else list(ports or DEFAULT_PORTS)
    for port in candidates:
        if not port_is_open(host, port, timeout):
            continue
        if targets(host, port, quiet=True):
            return port
    return None


def targets(host: str = "127.0.0.1", port: int = 9444, quiet: bool = False) -> list[Target]:
    """Every inspectable context the server lists at /json/list."""
    base = f"http://{host}:{port}"
    found: list[Target] = []
    body = _http_get(f"{base}/json/list")
    try:
        entries = json.loads(body) if body else []
    except json.JSONDecodeError:
        entries = []
    for entry in entries if isinstance(entries, list) else []:
        # On build 25245002 webSocketDebuggerUrl echoes the request path,
        # giving ws://host:port/json/list/devtools/page/0, which is not an
        # endpoint. The ws= parameter of devtoolsFrontendUrl is right.
        match = re.search(r"ws=([^&\s]+)", entry.get("devtoolsFrontendUrl") or "")
        if not match:
            continue
        # cohtml sets the title to the discovery URL; the page url is the
        # useful name.
        title = str(entry.get("title", ""))
        if title.startswith(f"{host}:{port}"):
            title = ""
        found.append(
            Target(
                id=str(entry.get("id", "")),
                title=title,
                url=str(entry.get("url", "")),
                ws_url="ws://" + match.group(1),
            )
        )
    if not found and not quiet:
        raise CDPError(
            f"{base} answered, but served no inspectable targets.\n"
            "If the game is running, UIDebugger may be off: `civ7lab options --live`\n"
            "sets it, and the option is read at launch, so the game must be restarted."
        )
    return found

    index = _http_get(f"{base}/")
    if index:
        for match in re.finditer(r"ws=([^\"'&<>\s]+)", index):
            ws_url = "ws://" + match.group(1)
            found.append(Target(id=ws_url.rsplit("/", 1)[-1], title="", url="", ws_url=ws_url))
    if not found and not quiet:
        raise CDPError(
            f"{base} answered, but served no inspectable targets.\n"
            "If the game is running, UIDebugger may be off: `civ7lab options --live`\n"
            "sets it, and the option is read at launch, so the game must be restarted."
        )
    return found


# --------------------------------------------------------------------------
# The WebSocket half
# --------------------------------------------------------------------------

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_OP_CONT, _OP_TEXT, _OP_BIN, _OP_CLOSE, _OP_PING, _OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class _WebSocket:
    """Only as much of RFC 6455 as a local inspector needs: a client handshake,
    masked text frames out, fragmentation and control frames in."""

    def __init__(self, url: str, timeout: float = 30.0):
        match = re.match(r"ws://([^:/]+)(?::(\d+))?(/.*)?$", url)
        if not match:
            raise CDPError(f"not a ws:// url: {url}")
        host, port, path = match.group(1), int(match.group(2) or 80), match.group(3) or "/"
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buffer = b""

        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())

        header = self._read_until(b"\r\n\r\n")
        if b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise CDPError(f"inspector refused the upgrade: {header.splitlines()[:1]}")
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        accept = re.search(rb"Sec-WebSocket-Accept:\s*(\S+)", header, re.I)
        if accept and accept.group(1).decode() != expected:
            raise CDPError("inspector handshake did not match the key we sent")

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("inspector closed the connection during the handshake")
            self._buffer += chunk
        head, self._buffer = self._buffer.split(marker, 1)
        return head + marker

    def _read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self.sock.recv(max(4096, count - len(self._buffer)))
            if not chunk:
                raise CDPError("inspector closed the connection")
            self._buffer += chunk
        out, self._buffer = self._buffer[:count], self._buffer[count:]
        return out

    def send_text(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x80 | _OP_TEXT])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self):
        first, second = self._read_exactly(2)
        fin, opcode = bool(first & 0x80), first & 0x0F
        masked, length = bool(second & 0x80), second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exactly(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exactly(8))[0]
        mask = self._read_exactly(4) if masked else None
        payload = self._read_exactly(length)
        if mask:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return fin, opcode, payload

    def recv_text(self) -> str:
        """The next complete text message, control frames handled in passing."""
        chunks: list[bytes] = []
        while True:
            fin, opcode, payload = self._recv_frame()
            if opcode == _OP_CLOSE:
                raise CDPError("inspector closed the connection")
            if opcode == _OP_PING:
                self._send_control(_OP_PONG, payload)
                continue
            if opcode == _OP_PONG:
                continue
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8", "replace")

    def _send_control(self, opcode: int, payload: bytes = b"") -> None:
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked)

    def close(self) -> None:
        with contextlib.suppress(OSError, CDPError):
            self._send_control(_OP_CLOSE)
        with contextlib.suppress(OSError):
            self.sock.close()

    def settimeout(self, timeout: float | None) -> None:
        self.sock.settimeout(timeout)


# --------------------------------------------------------------------------
# The protocol half
# --------------------------------------------------------------------------


class Session:
    """One attached inspector session. Events that arrive while waiting for
    a reply, such as console output, are kept in `events`."""

    def __init__(self, ws_url: str, timeout: float = 30.0):
        self.ws = _WebSocket(ws_url, timeout=timeout)
        self.ws_url = ws_url
        self.timeout = timeout
        self._next_id = 0
        self.events: list[dict] = []
        self._console_enabled = False

    # -- plumbing ---------------------------------------------------------
    def send(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        message_id = self._next_id
        self.ws.send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CDPError(f"{method} did not answer within {self.timeout}s")
            self.ws.settimeout(remaining)
            message = json.loads(self.ws.recv_text())
            if message.get("id") == message_id:
                if "error" in message:
                    raise CDPError(f"{method}: {message['error'].get('message', message['error'])}")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)

    # -- running code -----------------------------------------------------
    def evaluate(self, expression: str, await_promise: bool = True, raw: bool = False):
        """Run JavaScript in the game and return the value.

        The game serialises the result to JSON. Anything that does not
        serialise, such as a DOM node or an object with cycles, comes back as
        an empty object, so collectors return plain data.
        """
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "allowUnsafeEvalBlockedByCSP": True,
                "userGesture": True,
            },
        )
        if raw:
            return result
        details = result.get("exceptionDetails")
        if details:
            thrown = details.get("exception", {})
            text = thrown.get("description") or thrown.get("value") or details.get("text")
            raise JSException(str(text))
        return result.get("result", {}).get("value")

    def call(self, function: str, *args):
        """Call a function in the game with JSON arguments. Built as an
        expression, so no remote object id is needed."""
        packed = ", ".join(json.dumps(argument) for argument in args)
        return self.evaluate(f"({function})({packed})")

    def enable_console(self) -> None:
        """Start collecting the game's console output as events."""
        if self._console_enabled:
            return
        self.send("Runtime.enable")
        with contextlib.suppress(CDPError):
            self.send("Log.enable")
        self._console_enabled = True

    def drain_console(self) -> list[dict]:
        """Console lines seen since the last drain, oldest first, as dicts of
        {level, text, ts}. Unlike UI.log, this includes console.log."""
        lines = []
        remaining = []
        for event in self.events:
            method = event.get("method")
            params = event.get("params", {})
            if method == "Runtime.consoleAPICalled":
                text = " ".join(_render_remote(arg) for arg in params.get("args", []))
                lines.append(
                    {
                        "level": params.get("type", "log"),
                        "text": text,
                        "ts": params.get("timestamp"),
                    }
                )
            elif method == "Log.entryAdded":
                entry = params.get("entry", {})
                lines.append(
                    {
                        "level": entry.get("level", "log"),
                        "text": entry.get("text", ""),
                        "ts": entry.get("timestamp"),
                    }
                )
            elif method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails", {})
                lines.append(
                    {
                        "level": "exception",
                        "text": str(
                            details.get("exception", {}).get("description")
                            or details.get("text", "")
                        ),
                        "ts": params.get("timestamp"),
                    }
                )
            else:
                remaining.append(event)
        self.events = remaining
        return lines

    def pump(self, seconds: float) -> None:
        """Read events for a while without sending anything."""
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.ws.settimeout(remaining)
            try:
                message = json.loads(self.ws.recv_text())
            except TimeoutError:
                return
            if "method" in message:
                self.events.append(message)

    def close(self) -> None:
        self.ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()


def _render_remote(argument: dict) -> str:
    if "value" in argument:
        value = argument["value"]
        return value if isinstance(value, str) else json.dumps(value)
    if "description" in argument:
        return str(argument["description"])
    if "unserializableValue" in argument:
        return str(argument["unserializableValue"])
    return json.dumps(argument.get("preview", argument))


def connect(
    host: str | None = None,
    port: int | None = None,
    match: str | None = None,
    timeout: float = 30.0,
) -> Session:
    """Attach to a running game.

    `match` picks a target by substring of its title or url. Without it,
    fs://game/root-game.html is chosen, since the gameplay APIs are there.
    """
    host = host or os.environ.get(ENV_HOST, "127.0.0.1")
    if port is None:
        port = find_port(host)
        if port is None:
            raise CDPError(
                "No inspector found. In order: is the game running; is UIDebugger on\n"
                "(`civ7lab options --live`, then restart the game); is it on an unusual\n"
                f"port (set {ENV_PORT}). Tried {', '.join(map(str, DEFAULT_PORTS))}."
            )
    found = targets(host, port)
    if not found:
        raise CDPError(f"inspector on {host}:{port} has no targets")
    chosen = pick_target(found, match)
    return Session(chosen.ws_url, timeout=timeout)


def pick_target(found: list[Target], match: str | None = None) -> Target:
    if match:
        for target in found:
            if match.lower() in (target.title + " " + target.url + " " + target.id).lower():
                return target
        raise CDPError(
            f"no target matching {match!r}; saw: " + ", ".join(t.title or t.url for t in found)
        )
    # The gameplay APIs live in fs://game/root-game.html.
    for target in found:
        if target.url.endswith("root-game.html"):
            return target
    return found[0]
