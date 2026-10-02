"""Prove the WebSocket and CDP client against a fake inspector.

The real inspector only exists while the game is running, and the first time
anyone uses this client will be the moment a measurement is wanted. So the
framing, the handshake, the request/response matching and the event queue are
tested here against a server written for the purpose. Otherwise a few hundred
lines of protocol would be debugged in the worst possible place.
"""

import base64
import hashlib
import json
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from civ7lab import cdp, live

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakeInspector(threading.Thread):
    """Serves /json/list over HTTP and a WebSocket that answers Runtime.evaluate."""

    def __init__(self):
        super().__init__(daemon=True)
        self.http = HTTPServer(("127.0.0.1", 0), self._handler())
        self.http_port = self.http.server_port
        self.ws_socket = socket.socket()
        self.ws_socket.bind(("127.0.0.1", 0))
        self.ws_socket.listen(1)
        self.ws_port = self.ws_socket.getsockname()[1]
        self.last_expression = None

    def _handler(self):
        inspector = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                # The shape cohtml serves: the title is the discovery address,
                # and webSocketDebuggerUrl echoes the request path, so only
                # devtoolsFrontendUrl's ws= parameter points at the socket.
                port = inspector.ws_port
                body = json.dumps(
                    [
                        {
                            "id": "0",
                            "title": f"127.0.0.1:{inspector.http_port}",
                            "url": "fs://game/root-game.html",
                            "devtoolsFrontendUrl": "/devtools/inspector.html"
                            f"?ws=127.0.0.1:{port}/devtools/page/0",
                            "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}{self.path}"
                            "/devtools/page/0",
                        }
                    ]
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        return Handler

    def run(self):
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        connection, _ = self.ws_socket.accept()
        self._handshake(connection)
        self._serve(connection)

    def _handshake(self, connection):
        request = b""
        while b"\r\n\r\n" not in request:
            request += connection.recv(4096)
        key = [
            line.split(b": ", 1)[1]
            for line in request.split(b"\r\n")
            if line.lower().startswith(b"sec-websocket-key")
        ][0].decode()
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        connection.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            ).encode()
        )

    def _recv(self, connection):
        header = connection.recv(2)
        if len(header) < 2:
            return None
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", connection.recv(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", connection.recv(8))[0]
        opcode = header[0] & 0x0F
        mask = connection.recv(4) if header[1] & 0x80 else None
        payload = b""
        while len(payload) < length:
            chunk = connection.recv(length - len(payload))
            if not chunk:
                return None
            payload += chunk
        if mask:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        if opcode == 0x8:  # the client said goodbye
            return None
        return payload.decode()

    def _send(self, connection, text, fragment=False):
        payload = text.encode()
        if not fragment:
            header = bytearray([0x81])
            if len(payload) < 126:
                header.append(len(payload))
            else:
                header.append(126)
                header += struct.pack(">H", len(payload))
            connection.sendall(bytes(header) + payload)
            return
        # Deliberately split across two frames, because the real server does
        # for anything large and a client that assumes one frame per message
        # works until the first big snapshot.
        half = len(payload) // 2
        for opcode, part in ((0x01, payload[:half]), (0x80, payload[half:])):
            header = bytearray([opcode])
            if len(part) < 126:
                header.append(len(part))
            else:
                header.append(126)
                header += struct.pack(">H", len(part))
            connection.sendall(bytes(header) + part)

    def _serve(self, connection):
        while True:
            text = self._recv(connection)
            if text is None:
                return
            if not text.strip():
                return
            message = json.loads(text)
            method, params = message.get("method"), message.get("params", {})
            if method == "Runtime.evaluate":
                expression = params.get("expression", "")
                self.last_expression = expression
                if "boom" in expression:
                    result = {
                        "result": {"type": "undefined"},
                        "exceptionDetails": {
                            "exception": {"description": "ReferenceError: boom is not defined"}
                        },
                    }
                elif "big" in expression:
                    result = {
                        "result": {
                            "type": "object",
                            "value": {"tiles": [{"x": i} for i in range(50)]},
                        }
                    }
                else:
                    # Echo an evaluated arithmetic expression, or the raw text.
                    try:
                        value = eval(expression, {"__builtins__": {}}, {})
                    except Exception:
                        value = expression
                    result = {"result": {"type": "object", "value": value}}
                # An unsolicited event first, to prove it does not confuse the
                # reply matching.
                self._send(
                    connection,
                    json.dumps(
                        {
                            "method": "Runtime.consoleAPICalled",
                            "params": {"type": "error", "args": [{"value": "[C7LAB] hello"}]},
                        }
                    ),
                )
                self._send(
                    connection,
                    json.dumps(
                        {
                            "method": "Runtime.consoleAPICalled",
                            "params": {"type": "log", "args": [{"value": "a mod's own line"}]},
                        }
                    ),
                )
                self._send(
                    connection,
                    json.dumps({"id": message["id"], "result": result}),
                    fragment="big" in expression,
                )
            else:
                self._send(connection, json.dumps({"id": message["id"], "result": {}}))


def with_server(body):
    server = FakeInspector()
    server.start()
    try:
        return body(server)
    finally:
        server.http.shutdown()


def test_discovery_finds_the_target():
    def body(server):
        found = cdp.targets("127.0.0.1", server.http_port)
        assert len(found) == 1
        assert found[0].title == "" and found[0].url == "fs://game/root-game.html"
        assert found[0].ws_url == f"ws://127.0.0.1:{server.ws_port}/devtools/page/0"
        assert cdp.pick_target(found).ws_url.startswith("ws://")

    with_server(body)


def test_evaluate_returns_a_value():
    def body(server):
        session = cdp.connect(port=server.http_port)
        assert session.evaluate("1 + 1") == 2
        session.close()

    with_server(body)


def test_exception_is_raised_with_the_game_side_text():
    def body(server):
        session = cdp.connect(port=server.http_port)
        try:
            session.evaluate("boom()")
            raise AssertionError("should have raised")
        except cdp.JSException as error:
            assert "not defined" in str(error)
        session.close()

    with_server(body)


def test_fragmented_reply_reassembles():
    def body(server):
        session = cdp.connect(port=server.http_port)
        value = session.evaluate("big")
        assert len(value["tiles"]) == 50
        session.close()

    with_server(body)


def test_events_are_kept_not_dropped():
    def body(server):
        session = cdp.connect(port=server.http_port)
        session.evaluate("1 + 1")
        lines = session.drain_console()
        assert any("[C7LAB] hello" in line["text"] for line in lines), lines
        session.close()

    with_server(body)


def test_call_packs_json_arguments():
    def body(server):
        session = cdp.connect(port=server.http_port)
        session.call("(n, a) => C7Lab.collect(n, a)", "tile", {"x": 20, "y": 7})
        assert '"tile"' in server.last_expression
        assert '{"x": 20, "y": 7}' in server.last_expression
        session.close()

    with_server(body)


def test_the_gameplay_context_is_picked_over_others():
    found = [
        cdp.Target("1", "", "fs://game/shell.html", "ws://a"),
        cdp.Target("0", "", "fs://game/root-game.html", "ws://b"),
    ]
    assert cdp.pick_target(found).ws_url == "ws://b"
    assert cdp.pick_target(found, match="shell").ws_url == "ws://a"


def test_watch_shows_the_probes_records_or_every_line():
    def body(server):
        session = cdp.connect(port=server.http_port)
        probe = live.Probe(session)
        session.evaluate("1 + 1")
        assert [line["text"] for line in probe.watch(seconds=0.2)] == ["[C7LAB] hello"]
        session.evaluate("1 + 1")
        lines = [(line["level"], line["text"]) for line in probe.watch(seconds=0.2, marker="")]
        assert lines == [("error", "[C7LAB] hello"), ("log", "a mod's own line")], lines
        session.close()

    with_server(body)
