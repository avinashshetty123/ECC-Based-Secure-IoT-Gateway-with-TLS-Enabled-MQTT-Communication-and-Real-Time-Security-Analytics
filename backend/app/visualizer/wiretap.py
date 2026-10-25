"""A local TCP relay that shows what a network eavesdropper would see.

Device --> [WireTap :tap_port] --> Mosquitto :broker_port

Every byte is forwarded unchanged (the tap cannot decrypt or modify TLS, so
certificate and hostname verification still happen end-to-end between the
device and the broker). While relaying, it parses the byte stream into:
  * TLS records  (TLS modes)  - only the plaintext parts of the handshake
                               (ClientHello / ServerHello) can be decoded;
                               everything after is ciphertext.
  * MQTT packets (plain mode) - fully readable, including passwords.

Passwords captured in plain mode are MASKED before they leave this module;
the UI only states that they were readable on the wire.
"""
from __future__ import annotations

import itertools
import socket
import threading

from app.visualizer.events import EventBus

TLS_CONTENT = {20: "ChangeCipherSpec", 21: "Alert", 22: "Handshake", 23: "ApplicationData"}
TLS_HANDSHAKE = {
    1: "ClientHello", 2: "ServerHello", 4: "NewSessionTicket", 8: "EncryptedExtensions", 11: "Certificate",
    12: "ServerKeyExchange", 13: "CertificateRequest", 14: "ServerHelloDone", 15: "CertificateVerify",
    16: "ClientKeyExchange", 20: "Finished",
}
TLS_VERSIONS = {0x0301: "TLS 1.0", 0x0302: "TLS 1.1", 0x0303: "TLS 1.2", 0x0304: "TLS 1.3"}
CIPHERS = {
    0x1301: "TLS_AES_128_GCM_SHA256", 0x1302: "TLS_AES_256_GCM_SHA384", 0x1303: "TLS_CHACHA20_POLY1305_SHA256",
    0xC02B: "ECDHE-ECDSA-AES128-GCM-SHA256", 0xC02C: "ECDHE-ECDSA-AES256-GCM-SHA384",
    0xCCA9: "ECDHE-ECDSA-CHACHA20-POLY1305",
}
GROUPS = {
    0x0017: "secp256r1 (P-256)", 0x0018: "secp384r1 (P-384)", 0x0019: "secp521r1 (P-521)",
    0x001D: "X25519", 0x001E: "X448", 0x0100: "ffdhe2048", 0x11EC: "X25519MLKEM768",
}
MQTT_TYPES = {
    1: "CONNECT", 2: "CONNACK", 3: "PUBLISH", 4: "PUBACK", 5: "PUBREC", 6: "PUBREL", 7: "PUBCOMP",
    8: "SUBSCRIBE", 9: "SUBACK", 10: "UNSUBSCRIBE", 11: "UNSUBACK", 12: "PINGREQ", 13: "PINGRESP",
    14: "DISCONNECT",
}
CONNACK_RC = {0: "Accepted", 1: "Bad protocol", 2: "Client ID rejected", 3: "Server unavailable",
              4: "Bad username or password", 5: "Not authorized"}


def _hex(b: bytes, n: int = 40) -> str:
    s = b[:n].hex(" ")
    return s + (" …" if len(b) > n else "")


def _u16(b: bytes, i: int) -> int:
    return int.from_bytes(b[i:i + 2], "big")


# --------------------------------------------------------------------------- TLS parsing

def _parse_extensions(data: bytes) -> dict[int, bytes]:
    exts, i = {}, 0
    while i + 4 <= len(data):
        etype, elen = _u16(data, i), _u16(data, i + 2)
        exts[etype] = data[i + 4:i + 4 + elen]
        i += 4 + elen
    return exts


def parse_client_hello(body: bytes) -> dict:
    info: dict = {}
    i = 2 + 32
    i += 1 + body[i]                      # session id
    cs_len = _u16(body, i)
    info["cipher_suites_offered"] = [CIPHERS.get(_u16(body, i + 2 + k), f"0x{_u16(body, i + 2 + k):04x}")
                                     for k in range(0, cs_len, 2)][:8]
    i += 2 + cs_len
    i += 1 + body[i]                      # compression methods
    exts = _parse_extensions(body[i + 2:i + 2 + _u16(body, i)])
    if 0 in exts and len(exts[0]) > 5:    # server_name (SNI) - visible to any eavesdropper!
        info["sni"] = exts[0][5:5 + _u16(exts[0], 3)].decode(errors="replace")
    if 10 in exts:
        g = exts[10]
        info["groups_offered"] = [GROUPS.get(_u16(g, 2 + k), f"0x{_u16(g, 2 + k):04x}") for k in range(0, _u16(g, 0), 2)]
    if 43 in exts:
        v = exts[43]
        info["versions_offered"] = [TLS_VERSIONS.get(_u16(v, 1 + k), hex(_u16(v, 1 + k))) for k in range(0, v[0], 2)]
    if 51 in exts:                        # key_share: client's EPHEMERAL public key(s)
        ks, j, shares = exts[51], 2, []
        while j + 4 <= len(ks):
            grp, klen = _u16(ks, j), _u16(ks, j + 2)
            shares.append({"group": GROUPS.get(grp, hex(grp)), "public_key": _hex(ks[j + 4:j + 4 + klen], 16),
                           "key_bytes": klen})
            j += 4 + klen
        info["key_shares"] = shares
    return info


def parse_server_hello(body: bytes) -> dict:
    info: dict = {"legacy_version": TLS_VERSIONS.get(_u16(body, 0), "?")}
    i = 2 + 32
    i += 1 + body[i]
    info["cipher"] = CIPHERS.get(_u16(body, i), f"0x{_u16(body, i):04x}")
    i += 3
    if i + 2 <= len(body):
        exts = _parse_extensions(body[i + 2:i + 2 + _u16(body, i)])
        if 43 in exts:
            info["version"] = TLS_VERSIONS.get(_u16(exts[43], 0), "?")
        if 51 in exts and len(exts[51]) >= 4:
            ks = exts[51]
            info["key_exchange"] = GROUPS.get(_u16(ks, 0), hex(_u16(ks, 0)))
            info["server_public_key"] = _hex(ks[4:4 + _u16(ks, 2)], 16)
            info["key_bytes"] = _u16(ks, 2)
    info.setdefault("version", info["legacy_version"])
    return info


def parse_server_key_exchange(body: bytes) -> dict:  # TLS 1.2 only (plaintext there)
    if body and body[0] == 3:
        return {"key_exchange": GROUPS.get(_u16(body, 1), hex(_u16(body, 1))),
                "server_public_key": _hex(body[4:4 + body[3]], 16)}
    return {}


class TlsStream:
    """Re-frames a TCP byte stream into TLS records."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes) -> list[dict]:
        self.buf += data
        out = []
        while len(self.buf) >= 5:
            ctype, version, length = self.buf[0], _u16(self.buf, 1), _u16(self.buf, 3)
            if ctype not in TLS_CONTENT:      # not TLS at all (e.g. plaintext client on a TLS port)
                out.append({"layer": "raw", "rtype": "Non-TLS bytes", "length": len(self.buf), "hex": _hex(self.buf)})
                self.buf = b""
                break
            if len(self.buf) < 5 + length:
                break
            payload, self.buf = self.buf[5:5 + length], self.buf[5 + length:]
            rec = {"layer": "tls", "rtype": TLS_CONTENT[ctype], "record_version": TLS_VERSIONS.get(version, hex(version)),
                   "length": 5 + length, "header_hex": _hex(bytes([ctype]) + version.to_bytes(2, "big") + length.to_bytes(2, "big")),
                   "hex": _hex(payload), "encrypted": ctype == 23}
            if ctype == 22:
                msgs, j = [], 0
                while j + 4 <= len(payload):
                    htype, hlen = payload[j], int.from_bytes(payload[j + 1:j + 4], "big")
                    body = payload[j + 4:j + 4 + hlen]
                    entry = {"type": TLS_HANDSHAKE.get(htype, f"type {htype}")}
                    try:
                        if htype == 1:
                            entry.update(parse_client_hello(body))
                        elif htype == 2:
                            entry.update(parse_server_hello(body))
                        elif htype == 12:
                            entry.update(parse_server_key_exchange(body))
                    except (IndexError, ValueError):
                        entry["parse_error"] = True
                    msgs.append(entry)
                    j += 4 + hlen
                rec["handshake"] = msgs
            elif ctype == 21 and len(payload) == 2:
                rec["alert"] = {"level": payload[0], "description": payload[1]}
            out.append(rec)
        return out


# --------------------------------------------------------------------------- MQTT parsing

def _mask(secret: str) -> str:
    return (secret[:2] + "•" * max(len(secret) - 2, 0))[:14] + f"  ({len(secret)} chars)"


class MqttStream:
    """Re-frames a plaintext TCP byte stream into MQTT 3.1.1 packets."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes) -> list[dict]:
        self.buf += data
        out = []
        while len(self.buf) >= 2:
            mult, rem, i = 1, 0, 1
            while True:
                if i >= len(self.buf):
                    return out
                b = self.buf[i]
                rem += (b & 0x7F) * mult
                mult *= 128
                i += 1
                if not b & 0x80:
                    break
            if len(self.buf) < i + rem:
                return out
            pkt, self.buf = self.buf[:i + rem], self.buf[i + rem:]
            out.append(self._describe(pkt, pkt[i:]))
        return out

    @staticmethod
    def _describe(pkt: bytes, body: bytes) -> dict:
        ptype = pkt[0] >> 4
        d = {"layer": "mqtt", "rtype": MQTT_TYPES.get(ptype, f"type {ptype}"), "length": len(pkt), "hex": _hex(pkt),
             "encrypted": False}
        try:
            if ptype == 1:  # CONNECT
                j = 2 + _u16(body, 0)
                flags = body[j + 1]
                j += 4
                fields = {}
                cid_len = _u16(body, j)
                fields["client_id"] = body[j + 2:j + 2 + cid_len].decode(errors="replace")
                j += 2 + cid_len
                if flags & 0x04:  # will topic + message
                    j += 2 + _u16(body, j)
                    j += 2 + _u16(body, j)
                if flags & 0x80:
                    ulen = _u16(body, j)
                    fields["username"] = body[j + 2:j + 2 + ulen].decode(errors="replace")
                    j += 2 + ulen
                if flags & 0x40:
                    plen = _u16(body, j)
                    fields["password_masked"] = _mask(body[j + 2:j + 2 + plen].decode(errors="replace"))
                    fields["password_exposed"] = True
                d["fields"] = fields
                d["readable"] = (f"CONNECT client_id={fields['client_id']} username={fields.get('username', '-')} "
                                 f"password={'READABLE ON THE WIRE (masked here)' if flags & 0x40 else '-'}")
            elif ptype == 2:  # CONNACK
                rc = body[1]
                d["fields"] = {"return_code": CONNACK_RC.get(rc, rc)}
                d["readable"] = f"CONNACK {CONNACK_RC.get(rc, rc)}"
            elif ptype == 3:  # PUBLISH
                qos = (pkt[0] >> 1) & 3
                tlen = _u16(body, 0)
                topic = body[2:2 + tlen].decode(errors="replace")
                payload = body[2 + tlen + (2 if qos else 0):]
                d["fields"] = {"topic": topic, "qos": qos}
                d["readable"] = f"PUBLISH {topic}  {payload[:400].decode(errors='replace')}"
            elif ptype == 8:  # SUBSCRIBE
                tlen = _u16(body, 2)
                d["readable"] = f"SUBSCRIBE {body[4:4 + tlen].decode(errors='replace')}"
            else:
                d["readable"] = d["rtype"]
        except (IndexError, ValueError):
            d["readable"] = d["rtype"]
        return d


# --------------------------------------------------------------------------- relay

class WireTap:
    def __init__(self, bus: EventBus, listen_port: int, target_port: int, tls: bool):
        self.bus, self.listen_port, self.target_port, self.tls = bus, listen_port, target_port, tls
        self._servers: list[socket.socket] = []
        self._conns: set[socket.socket] = set()
        self._ids = itertools.count(1)
        self._next_label = "client"
        self._lock = threading.Lock()
        self._running = False

    def label_next(self, label: str) -> None:
        """Name the next accepted connection (scenarios run one at a time)."""
        with self._lock:
            self._next_label = label

    def start(self) -> None:
        self._running = True
        for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            try:
                s = socket.socket(family, socket.SOCK_STREAM)
                s.bind((host, self.listen_port))
                s.listen(16)
            except OSError:
                continue  # e.g. IPv6 disabled
            self._servers.append(s)
            threading.Thread(target=self._accept_loop, args=(s,), daemon=True).start()
        if not self._servers:
            raise OSError(f"wire tap could not listen on port {self.listen_port}")

    def stop(self) -> None:
        self._running = False
        for s in self._servers + list(self._conns):
            try:
                s.close()
            except OSError:
                pass
        self._servers.clear()
        self._conns.clear()

    def _accept_loop(self, server: socket.socket) -> None:
        while self._running:
            try:
                client, addr = server.accept()
            except OSError:
                return
            with self._lock:
                label, self._next_label = self._next_label, "client"
            conn_id = next(self._ids)
            try:
                upstream = socket.create_connection(("127.0.0.1", self.target_port), timeout=5)
                upstream.settimeout(None)
            except OSError as exc:
                self.bus.publish("error", message=f"wire tap could not reach broker: {exc}")
                client.close()
                continue
            for s in (client, upstream):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._conns.update((client, upstream))
            self.bus.publish("wire_conn", conn=conn_id, label=label, event="open", peer=f"{addr[0]}:{addr[1]}")
            stream_cls = TlsStream if self.tls else MqttStream
            threading.Thread(target=self._pump, args=(client, upstream, conn_id, label, "c2s", stream_cls()), daemon=True).start()
            threading.Thread(target=self._pump, args=(upstream, client, conn_id, label, "s2c", stream_cls()), daemon=True).start()

    def _pump(self, src, dst, conn_id, label, direction, stream) -> None:
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)  # forward FIRST: inspection never delays or alters traffic
                try:
                    for item in stream.feed(data):
                        self.bus.publish("wire", conn=conn_id, label=label, dir=direction, **item)
                except Exception as exc:  # noqa: BLE001 - a parser bug must never break the relay
                    self.bus.publish("error", message=f"wire parser: {exc}")
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                s.close()
                self._conns.discard(s)
            if direction == "c2s":
                self.bus.publish("wire_conn", conn=conn_id, label=label, event="close")
