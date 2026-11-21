"""Tiny local SOCKS5 relay.

Chrome (and Playwright's proxy option) cannot do SOCKS5 username/password
authentication, while the egress pool requires it. This relay listens without
authentication on 127.0.0.1 and re-authenticates against the upstream proxy.

Usage:
    python -m opengame_protocol.socks_bridge --listen 127.0.0.1:10808 \
        --upstream 74.81.81.81:10000 --user <session>__crus --password <pw>
"""

from __future__ import annotations

import argparse
import socket
import struct
import threading


def _recv_exactly(sock, count):
    buf = b""
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf += chunk
    return buf


def _parse_address(sock, atyp):
    if atyp == 0x01:
        raw = _recv_exactly(sock, 4)
        host = socket.inet_ntoa(raw)
    elif atyp == 0x03:
        length = _recv_exactly(sock, 1)[0]
        raw = _recv_exactly(sock, length)
        host = raw.decode("utf-8", "replace")
    elif atyp == 0x04:
        raw = _recv_exactly(sock, 16)
        host = socket.inet_ntop(socket.AF_INET6, raw)
    else:
        raise ConnectionError("bad address type %s" % atyp)
    port = struct.unpack("!H", _recv_exactly(sock, 2))[0]
    return raw, host, port


def _upstream_connect(upstream, user, password):
    sock = socket.create_connection(upstream, timeout=30)
    if user:
        sock.sendall(b"\x05\x02\x00\x02")
    else:
        sock.sendall(b"\x05\x01\x00")
    reply = _recv_exactly(sock, 2)
    if reply[0] != 0x05:
        raise ConnectionError("bad upstream greeting")
    if reply[1] == 0x02:
        if not user:
            raise ConnectionError("upstream wants auth")
        sock.sendall(
            b"\x01"
            + bytes([len(user)])
            + user.encode()
            + bytes([len(password or "")])
            + (password or "").encode()
        )
        auth = _recv_exactly(sock, 2)
        if auth[1] != 0x00:
            raise ConnectionError("upstream auth rejected")
    elif reply[1] != 0x00:
        raise ConnectionError("upstream auth method refused")
    return sock


def _pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass


def handle_client(client, upstream, user, password):
    remote = None
    try:
        version = _recv_exactly(client, 1)[0]
        if version != 0x05:
            return
        n_methods = _recv_exactly(client, 1)[0]
        _recv_exactly(client, n_methods)
        client.sendall(b"\x05\x00")

        header = _recv_exactly(client, 4)
        if header[1] != 0x01:
            client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            return
        atyp = header[3]
        raw, host, port = _parse_address(client, atyp)

        try:
            remote = _upstream_connect(upstream, user, password)
        except Exception:
            client.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            return

        if atyp == 0x01:
            req = b"\x05\x01\x00\x01" + raw + struct.pack("!H", port)
        elif atyp == 0x04:
            req = b"\x05\x01\x00\x04" + raw + struct.pack("!H", port)
        else:
            req = (
                b"\x05\x01\x00\x03"
                + bytes([len(host)])
                + host.encode()
                + struct.pack("!H", port)
            )
        remote.sendall(req)
        resp = _recv_exactly(remote, 4)
        if resp[1] != 0x00:
            client.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            remote.close()
            return
        atyp = resp[3]
        if atyp == 0x01:
            _recv_exactly(remote, 4)
        elif atyp == 0x03:
            _recv_exactly(remote, _recv_exactly(remote, 1)[0])
        elif atyp == 0x04:
            _recv_exactly(remote, 16)
        _recv_exactly(remote, 2)

        client.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
        t1 = threading.Thread(target=_pump, args=(client, remote), daemon=True)
        t2 = threading.Thread(target=_pump, args=(remote, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        for sock in (client, remote):
            try:
                if sock:
                    sock.close()
            except OSError:
                pass


def serve(listen, upstream, user, password):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(listen)
    server.listen(64)
    print(
        "socks bridge %s:%d -> %s:%d" % (listen[0], listen[1], upstream[0], upstream[1]),
        flush=True,
    )
    while True:
        client, _ = server.accept()
        threading.Thread(
            target=handle_client, args=(client, upstream, user, password), daemon=True
        ).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="127.0.0.1:10808")
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--user")
    ap.add_argument("--password")
    args = ap.parse_args()
    lhost, lport = args.listen.split(":")
    uhost, uport = args.upstream.split(":")
    serve((lhost, int(lport)), (uhost, int(uport)), args.user, args.password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
