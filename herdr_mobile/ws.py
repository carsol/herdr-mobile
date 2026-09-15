"""RFC 6455 WebSocket bridge to `herdr terminal attach` on a fresh PTY.

Server -> client: BINARY frames of raw PTY bytes.
Client -> server: BINARY frames are keystrokes; TEXT frames are JSON control
messages, currently only {"type":"resize","cols":N,"rows":M}.
"""

import base64
import fcntl
import hashlib
import json
import os
import pty
import select
import signal
import struct
import termios
import threading

HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")
TAKEOVER = os.environ.get("HERDR_MOBILE_TAKEOVER", "1") != "0"
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(client_key: str) -> str:
    return base64.b64encode(hashlib.sha1((client_key + _GUID).encode()).digest()).decode()


def _frame(opcode: int, payload: bytes) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def _read_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def _read_frame(sock) -> tuple[int, bytes]:
    b1, b2 = _read_exact(sock, 2)
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", _read_exact(sock, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", _read_exact(sock, 8))[0]
    mask = _read_exact(sock, 4) if masked else None
    data = _read_exact(sock, n)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def bridge(sock, terminal_id: str) -> None:
    """Run until the client hangs up. Closing only detaches; the pane lives on."""
    pid, fd = pty.fork()
    if pid == 0:
        env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
        argv = [HERDR_BIN, "terminal", "attach", terminal_id]
        if TAKEOVER:
            argv.append("--takeover")
        try:
            os.execvpe(argv[0], argv, env)
        finally:
            os._exit(127)

    _set_winsize(fd, 40, 100)
    lock = threading.Lock()
    alive = True

    def send(opcode: int, payload: bytes) -> None:
        with lock:
            sock.sendall(_frame(opcode, payload))

    def pump_pty() -> None:
        nonlocal alive
        try:
            while alive:
                r, _, _ = select.select([fd], [], [], 1.0)
                if not r:
                    continue
                data = os.read(fd, 65536)
                if not data:
                    break
                send(0x2, data)
        except OSError:
            pass
        finally:
            alive = False
            try:
                send(0x8, b"")
            except OSError:
                pass

    t = threading.Thread(target=pump_pty, daemon=True)
    t.start()
    try:
        while alive:
            opcode, data = _read_frame(sock)
            if opcode == 0x8:
                break
            if opcode == 0x9:
                send(0xA, data)
            elif opcode == 0x2:
                os.write(fd, data)
            elif opcode == 0x1:
                try:
                    msg = json.loads(data)
                except ValueError:
                    continue
                if msg.get("type") == "resize":
                    _set_winsize(fd, int(msg.get("rows", 24)), int(msg.get("cols", 80)))
                    os.kill(pid, signal.SIGWINCH)
    except (ConnectionError, OSError):
        pass
    finally:
        alive = False
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
