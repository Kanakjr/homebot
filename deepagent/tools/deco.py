"""TP-Link Deco mesh router tools.

Implements the proprietary Deco RPC protocol (RSA-PKCS1v1.5 + AES-CBC) so the
agent can list connected clients, enumerate mesh nodes, reboot nodes, and
manage DHCP reservations. The crypto/login dance was ported from the
``tplink_deco`` Home Assistant HACS integration (see amosyuen/ha-tplink-deco),
trimmed to standard-lib + ``cryptography`` + ``aiohttp`` so we avoid adding a
new dependency to the deepagent image.

All public entry points are LangChain ``@tool`` functions suitable for the
ReAct agent.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import math
import re
import secrets
import ssl as ssl_module
from typing import Any
from urllib.parse import quote_plus

import aiohttp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from langchain_core.tools import tool

import config

log = logging.getLogger("deepagent.tools.deco")

AES_KEY_BYTES = 16
MIN_AES_KEY = 10 ** (AES_KEY_BYTES - 1)
MAX_AES_KEY = (10**AES_KEY_BYTES) - 1
PKCS1_V15_HEADER_BYTES = 11
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_TIMEOUT_ERROR_RETRIES = 2

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
ALLOWED_SUBNET = ipaddress.ip_network(config.__dict__.get("DECO_ALLOWED_SUBNET", "192.168.0.0/16"))


class DecoError(Exception):
    """Base class for Deco RPC failures."""


class LoginError(DecoError):
    pass


class ApiError(DecoError):
    pass


def _byte_len(n: int) -> int:
    return (int(math.log2(n)) + 8) >> 3


def _decode_name(name: str) -> str:
    try:
        return base64.b64decode(name).decode()
    except Exception:
        return name


def _encode_name(name: str) -> str:
    return base64.b64encode(name.encode()).decode()


def _rsa_encrypt(n: int, e: int, plaintext: bytes) -> str:
    """RSA/PKCS1v1.5 encrypt in fixed-size blocks and hex-concatenate.

    Matches TP-Link's expectation: block size = keysize in bytes, payload
    bytes per block = block_size - 11 (PKCS#1 v1.5 header overhead).
    """
    pub = RSAPublicNumbers(e, n).public_key(default_backend())
    block_size = _byte_len(n)
    bytes_per_block = block_size - PKCS1_V15_HEADER_BYTES

    out = []
    for i in range(0, len(plaintext), bytes_per_block):
        chunk = plaintext[i : i + bytes_per_block]
        out.append(pub.encrypt(chunk, asym_padding.PKCS1v15()).hex())
    return "".join(out)


def _aes_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    padder = sym_padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def _aes_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    return dec.update(ciphertext) + dec.finalize()


def _check_error_code(context: str, data: dict) -> None:
    code = data.get("error_code") or data.get("errorcode")
    if code:
        raise ApiError(f"{context} error_code={code}: {data}")


def _normalize_mac(mac: str) -> str:
    """Return upper-case MAC with colon separators (XX:XX:...)."""
    m = mac.strip().upper().replace("-", ":")
    if not MAC_RE.match(m):
        raise ValueError(f"invalid MAC address: {mac!r}")
    return m


def _mac_for_deco(mac: str) -> str:
    """Deco reservation API expects hyphen-separated uppercase MAC."""
    return _normalize_mac(mac).replace(":", "-")


class DecoClient:
    """Lightweight async client for the TP-Link Deco web admin RPC."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._timeout_seconds = timeout_seconds

        if verify_ssl:
            self._ssl: Any = None
        else:
            self._ssl = ssl_module.create_default_context()
            self._ssl.check_hostname = False
            self._ssl.verify_mode = ssl_module.CERT_NONE

        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

        # Auth/session state
        self._aes_key: int | None = None
        self._aes_iv: int | None = None
        self._aes_key_bytes: bytes | None = None
        self._aes_iv_bytes: bytes | None = None
        self._password_rsa_n: int | None = None
        self._password_rsa_e: int | None = None
        self._sign_rsa_n: int | None = None
        self._sign_rsa_e: int | None = None
        self._seq: int | None = None
        self._stok: str | None = None
        self._cookie: str | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def _clear_auth(self) -> None:
        self._seq = None
        self._stok = None
        self._cookie = None

    def _generate_aes(self) -> None:
        self._aes_key = secrets.randbelow(MAX_AES_KEY - MIN_AES_KEY) + MIN_AES_KEY
        self._aes_iv = secrets.randbelow(MAX_AES_KEY - MIN_AES_KEY) + MIN_AES_KEY
        self._aes_key_bytes = str(self._aes_key).encode("utf-8")
        self._aes_iv_bytes = str(self._aes_iv).encode("utf-8")

    async def _fetch_keys(self) -> None:
        resp = await self._raw_post(
            "fetch_keys",
            f"{self._host}/cgi-bin/luci/;stok=/login",
            params={"form": "keys"},
            data=json.dumps({"operation": "read"}),
        )
        try:
            keys = resp["result"]["password"]
            self._password_rsa_n = int(keys[0], 16)
            self._password_rsa_e = int(keys[1], 16)
        except Exception as err:
            raise LoginError(f"parse keys failed: {err}, resp={resp}") from err

    async def _fetch_auth(self) -> None:
        resp = await self._raw_post(
            "fetch_auth",
            f"{self._host}/cgi-bin/luci/;stok=/login",
            params={"form": "auth"},
            data=json.dumps({"operation": "read"}),
        )
        try:
            auth_result = resp["result"]
            auth_key = auth_result["key"]
            self._sign_rsa_n = int(auth_key[0], 16)
            self._sign_rsa_e = int(auth_key[1], 16)
            self._seq = auth_result["seq"]
        except Exception as err:
            raise LoginError(f"parse auth failed: {err}, resp={resp}") from err

    async def login(self) -> None:
        async with self._lock:
            if self._stok and self._cookie:
                return
            if self._aes_key is None:
                self._generate_aes()
            if self._password_rsa_n is None:
                await self._fetch_keys()
            await self._fetch_auth()

            password_encrypted = _rsa_encrypt(
                self._password_rsa_n,  # type: ignore[arg-type]
                self._password_rsa_e,  # type: ignore[arg-type]
                self._password.encode(),
            )
            payload = {
                "params": {"password": password_encrypted},
                "operation": "login",
            }
            resp = await self._raw_post(
                "login",
                f"{self._host}/cgi-bin/luci/;stok=/login",
                params={"form": "login"},
                data=self._encode_payload(payload),
            )
            data = self._decrypt_data("login", resp["data"])
            if data.get("error_code") != 0:
                self._clear_auth()
                raise LoginError(f"login rejected: {data}")
            self._stok = data["result"]["stok"]
            if self._cookie is None:
                raise LoginError("login did not return Set-Cookie sysauth header")

    async def _login_if_needed(self) -> None:
        if self._stok is None or self._cookie is None:
            await self.login()

    def _encode_sign(self, data_len: int) -> str:
        if self._seq is None:
            raise LoginError("_seq is None; must login first")
        seq_plus = self._seq + data_len
        auth_hash = hashlib.md5(f"{self._username}{self._password}".encode()).digest().hex()
        sign_text = f"k={self._aes_key}&i={self._aes_iv}&h={auth_hash}&s={seq_plus}"
        return _rsa_encrypt(
            self._sign_rsa_n,  # type: ignore[arg-type]
            self._sign_rsa_e,  # type: ignore[arg-type]
            sign_text.encode(),
        )

    def _encode_data(self, payload: Any) -> str:
        body = json.dumps(payload, separators=(",", ":"))
        enc = _aes_encrypt(self._aes_key_bytes, self._aes_iv_bytes, body.encode())
        return base64.b64encode(enc).decode()

    def _encode_payload(self, payload: Any) -> str:
        data = self._encode_data(payload)
        sign = self._encode_sign(len(data))
        return f"sign={sign}&data={quote_plus(data)}"

    def _decrypt_data(self, context: str, data: str) -> dict:
        if not data:
            self._clear_auth()
            raise ApiError(f"{context}: empty data from router")
        try:
            raw = base64.b64decode(data)
            dec = _aes_decrypt(self._aes_key_bytes, self._aes_iv_bytes, raw)
            pad = int(dec[-1])
            return json.loads(dec[:-pad].decode())
        except ApiError:
            raise
        except Exception as err:
            raise ApiError(f"{context}: decrypt failed: {err}") from err

    async def _raw_post(
        self,
        context: str,
        url: str,
        params: dict,
        data: Any,
    ) -> dict:
        session = await self._ensure_session()
        headers = {"Content-Type": "application/json"}
        if self._cookie:
            headers["Cookie"] = self._cookie
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with session.post(
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    ssl=self._ssl,
                ) as resp:
                    resp.raise_for_status()
                    set_cookie = resp.headers.get("Set-Cookie")
                    if set_cookie:
                        m = re.search(r"(sysauth=[a-f0-9]+)", set_cookie)
                        if m:
                            self._cookie = m.group(1)
                    body = await resp.json(content_type=None)
                    if "error_code" in body and body["error_code"] not in (0, ""):
                        # surface non-zero envelope error to caller
                        raise ApiError(f"{context} envelope error: {body}")
                    return body
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                self._clear_auth()
            raise DecoError(f"{context} http {err.status}: {err.message}") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._clear_auth()
            raise DecoError(f"{context} transport: {err}") from err

    async def _call(self, context: str, path: str, params: dict, payload: dict) -> dict:
        await self._login_if_needed()
        url = f"{self._host}/cgi-bin/luci/;stok={self._stok}{path}"
        resp = await self._raw_post(context, url, params=params, data=self._encode_payload(payload))
        return self._decrypt_data(context, resp["data"])

    # --- Public API ---

    async def list_clients(self, deco_mac: str = "default") -> list[dict]:
        payload = {"operation": "read", "params": {"device_mac": deco_mac}}
        data = await self._call(
            "list_clients", "/admin/client", {"form": "client_list"}, payload
        )
        _check_error_code("list_clients", data)
        clients = data["result"]["client_list"]
        for c in clients:
            if "name" in c:
                c["name"] = _decode_name(c["name"])
        return clients

    async def list_devices(self) -> list[dict]:
        """List Deco mesh nodes."""
        payload = {"operation": "read"}
        data = await self._call(
            "list_devices", "/admin/device", {"form": "device_list"}, payload
        )
        _check_error_code("list_devices", data)
        devs = data["result"]["device_list"]
        for d in devs:
            nick = d.get("custom_nickname")
            if nick:
                d["custom_nickname"] = _decode_name(nick)
        return devs

    async def reboot_decos(self, macs: list[str]) -> dict:
        payload = {
            "operation": "reboot",
            "params": {"mac_list": [{"mac": m} for m in macs]},
        }
        data = await self._call(
            "reboot_decos", "/admin/device", {"form": "system"}, payload
        )
        _check_error_code("reboot_decos", data)
        return data.get("result", {})

    async def list_reservations(self) -> list[dict]:
        """Return DHCP reservation entries configured on the router."""
        payload = {"operation": "read"}
        # The web UI uses /admin/dhcps?form=reservation
        data = await self._call(
            "list_reservations", "/admin/dhcps", {"form": "reservation"}, payload
        )
        _check_error_code("list_reservations", data)
        result = data.get("result") or {}
        entries = (
            result.get("reservation_list")
            or result.get("list")
            or result.get("reservations")
            or []
        )
        for entry in entries:
            nm = entry.get("name")
            if nm:
                entry["name"] = _decode_name(nm)
        return entries

    async def add_reservation(self, ip: str, mac: str, name: str, enable: bool = True) -> dict:
        # Safety: IP must live in an RFC1918 subnet
        addr = ipaddress.ip_address(ip)
        if not addr.is_private:
            raise ValueError(f"refusing to reserve non-private IP {ip}")
        dmac = _mac_for_deco(mac)
        payload = {
            "operation": "add",
            "params": {
                "enable": enable,
                "ip": ip,
                "mac": dmac,
                "name": _encode_name(name),
            },
        }
        data = await self._call(
            "add_reservation", "/admin/dhcps", {"form": "reservation"}, payload
        )
        _check_error_code("add_reservation", data)
        return data.get("result") or {"status": "ok"}

    async def remove_reservation(self, mac: str) -> dict:
        dmac = _mac_for_deco(mac)
        payload = {"operation": "remove", "params": {"key": dmac}}
        data = await self._call(
            "remove_reservation", "/admin/dhcps", {"form": "reservation"}, payload
        )
        _check_error_code("remove_reservation", data)
        return data.get("result") or {"status": "ok"}


# Module-level singleton so repeated tool calls reuse the Deco session.
_CLIENT_SINGLETON: DecoClient | None = None
_CLIENT_LOCK = asyncio.Lock()


async def _get_client() -> DecoClient:
    global _CLIENT_SINGLETON
    async with _CLIENT_LOCK:
        if _CLIENT_SINGLETON is None:
            if not config.DECO_URL or not config.DECO_PASSWORD:
                raise RuntimeError(
                    "Deco not configured. Set DECO_URL, DECO_USERNAME, DECO_PASSWORD."
                )
            _CLIENT_SINGLETON = DecoClient(
                host=config.DECO_URL,
                username=config.DECO_USERNAME,
                password=config.DECO_PASSWORD,
                verify_ssl=config.DECO_VERIFY_SSL,
            )
        return _CLIENT_SINGLETON


def _err(context: str, err: Exception) -> str:
    log.warning("deco %s failed: %s: %s", context, type(err).__name__, err)
    return json.dumps({"status": "error", "context": context, "detail": str(err)[:400]})


def _project_client(c: dict) -> dict:
    """Return a trimmed client record with the fields the agent needs."""
    return {
        "name": c.get("name") or c.get("client_mesh_name") or "",
        "mac": c.get("mac", ""),
        "ip": c.get("ip", ""),
        "online": bool(c.get("online", True)),
        "wire_type": c.get("wire_type") or c.get("wireless_connection") or "",
        "interface": c.get("interface") or c.get("connection_type") or "",
        "owner_id": c.get("owner_id"),
        "device_type": c.get("client_type") or c.get("device_type") or "",
    }


def _project_node(d: dict) -> dict:
    return {
        "nickname": d.get("custom_nickname") or d.get("device_model") or "",
        "device_model": d.get("device_model") or d.get("hardware_ver") or "",
        "mac": d.get("mac") or d.get("device_mac") or "",
        "ip": d.get("device_ip") or d.get("ip") or "",
        "role": d.get("role", ""),
        "inet_status": d.get("inet_status", ""),
        "signal_level": d.get("signal_level"),
        "connection_type": d.get("connection_type", ""),
    }


@tool
async def deco_list_clients(deco_mac: str = "default") -> str:
    """List all devices connected to the Deco mesh.

    Returns wireless/wired clients with name, MAC, IP, online state and the
    mesh node they're attached to. Use this to find a device by name/vendor
    before reserving an IP, or to confirm a new device joined the network.

    Args:
        deco_mac: Mesh node MAC to filter to (default "default" returns all
            clients across the mesh).
    """
    try:
        client = await _get_client()
        raw = await client.list_clients(deco_mac=deco_mac)
        projected = [_project_client(c) for c in raw]
        return json.dumps(
            {"status": "ok", "count": len(projected), "clients": projected}, default=str
        )
    except Exception as err:
        return _err("list_clients", err)


@tool
async def deco_list_mesh_nodes() -> str:
    """List the Deco mesh nodes (routers/satellites) with status and uplink info.

    Use when the user asks "which decos are online", "is the bedroom deco
    working", "reboot the mesh", or wants mesh topology. Each node exposes
    its MAC, nickname, role (master/slave), and uplink signal.
    """
    try:
        client = await _get_client()
        raw = await client.list_devices()
        projected = [_project_node(d) for d in raw]
        return json.dumps(
            {"status": "ok", "count": len(projected), "nodes": projected}, default=str
        )
    except Exception as err:
        return _err("list_mesh_nodes", err)


@tool
async def deco_reboot_nodes(macs: list[str]) -> str:
    """Reboot one or more Deco mesh nodes by MAC address.

    Destructive: expect ~60 seconds downtime for rebooted nodes. Always
    confirm with the user (via offer_choices) before calling. Pass the MAC
    list returned by ``deco_list_mesh_nodes``.
    """
    try:
        if not macs:
            return json.dumps({"status": "error", "detail": "no MACs provided"})
        client = await _get_client()
        result = await client.reboot_decos([_normalize_mac(m) for m in macs])
        return json.dumps({"status": "ok", "rebooted": macs, "result": result})
    except Exception as err:
        return _err("reboot_nodes", err)


@tool
async def deco_reservation_help(requested_ip: str = "", mac: str = "", name: str = "") -> str:
    """Explain how to pin a device to a fixed LAN IP on this Deco mesh.

    Deco firmwares (including the M4R deployed here) deliberately hide DHCP
    address reservations from the local web admin -- the feature is only
    available in the Deco mobile app (More > Advanced > Address Reservation).
    The agent cannot set it directly, but this tool returns the step-by-step
    guidance so the bot can surface it cleanly. Call it whenever the user asks
    to "pin", "reserve", "fix", or "lock" an IP.

    Args:
        requested_ip: Optional target IP to pass through for the message.
        mac: Optional MAC address to pass through.
        name: Optional human label for the device.
    """
    msg_lines = [
        "Deco DHCP reservations are mobile-app-only on this firmware.",
        "Open the Deco app -> More -> Advanced -> Address Reservation -> (+).",
    ]
    if requested_ip or mac or name:
        detail = []
        if name:
            detail.append(f"name: {name}")
        if mac:
            try:
                detail.append(f"MAC: {_normalize_mac(mac)}")
            except Exception:
                detail.append(f"MAC: {mac}")
        if requested_ip:
            detail.append(f"IP: {requested_ip}")
        if detail:
            msg_lines.append("Use: " + ", ".join(detail) + ".")
    msg_lines.append(
        "Alternative: set a static IP inside the device's own app "
        "(WiZ, Smart Life/Tuya, etc.)."
    )
    return json.dumps(
        {
            "status": "manual_action_required",
            "reason": "deco_firmware_no_local_reservation_api",
            "instructions": msg_lines,
            "requested": {"ip": requested_ip, "mac": mac, "name": name},
        }
    )


def get_deco_tools() -> list:
    """Return Deco tools, or [] if creds aren't configured (so the agent
    still boots in dev environments without a router).

    Note: DHCP reservation add/remove is intentionally omitted because the
    Deco local admin API does not expose it (feature is mobile-app-only).
    ``deco_reservation_help`` is exposed instead so the agent can give the
    user accurate instructions.
    """
    if not config.DECO_URL or not config.DECO_PASSWORD:
        log.info("deco tools disabled: DECO_URL or DECO_PASSWORD unset")
        return []
    return [
        deco_list_clients,
        deco_list_mesh_nodes,
        deco_reboot_nodes,
        deco_reservation_help,
    ]
