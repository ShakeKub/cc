"""SSL/TLS certificate inspector — expiry, chain, ciphers, protocol support."""

import datetime
import socket
import ssl
from typing import Any


_WEAK_PROTOCOLS = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.1"}
_EXPIRY_WARN_DAYS = 30


def _connect_ssl(host: str, port: int, ctx: ssl.SSLContext, timeout: float = 5.0):
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            return ssock.getpeercert(), ssock.cipher(), ssock.version()


def check(host: str, port: int = 443, timeout: float = 5.0) -> dict:
    """Full TLS inspection of *host:port*. Returns a detail dict."""
    result: dict[str, Any] = {
        "host": host, "port": port,
        "ok": False, "error": None,
        "cert": {}, "chain": [],
        "cipher": None, "protocol": None,
        "weak_protocols": [],
        "expiry_days": None, "expired": False, "expiry_warn": False,
    }

    # ── Main connection ───────────────────────────────────────
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode    = ssl.CERT_REQUIRED

    try:
        cert, cipher, version = _connect_ssl(host, port, ctx, timeout)
    except ssl.CertificateError as exc:
        result["error"] = f"Certificate error: {exc}"
        return result
    except ssl.SSLError as exc:
        result["error"] = f"SSL error: {exc}"
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result

    result["ok"]       = True
    result["cipher"]   = {"name": cipher[0], "protocol": cipher[1], "bits": cipher[2]}
    result["protocol"] = version

    # ── Parse certificate ─────────────────────────────────────
    subject = dict(x[0] for x in cert.get("subject", []))
    issuer  = dict(x[0] for x in cert.get("issuer",  []))
    sans    = [v for t, v in cert.get("subjectAltName", []) if t == "DNS"]

    not_after_str  = cert.get("notAfter",  "")
    not_before_str = cert.get("notBefore", "")

    expiry_days = None
    expired     = False
    if not_after_str:
        try:
            not_after = datetime.datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
            not_after = not_after.replace(tzinfo=datetime.timezone.utc)
            now       = datetime.datetime.now(datetime.timezone.utc)
            delta     = not_after - now
            expiry_days = delta.days
            expired     = delta.total_seconds() < 0
        except Exception:
            pass

    result["cert"] = {
        "subject":    subject,
        "issuer":     issuer,
        "sans":       sans,
        "not_before": not_before_str,
        "not_after":  not_after_str,
        "serial":     cert.get("serialNumber", ""),
    }
    result["expiry_days"] = expiry_days
    result["expired"]     = expired
    result["expiry_warn"] = (expiry_days is not None
                             and 0 <= expiry_days <= _EXPIRY_WARN_DAYS)

    # ── Probe weak protocols ───────────────────────────────────
    weak_found = []
    for proto_name, ssl_const in [
        ("TLSv1",   ssl.TLSVersion.TLSv1   if hasattr(ssl, "TLSVersion") else None),
        ("TLSv1.1", ssl.TLSVersion.TLSv1_1 if hasattr(ssl, "TLSVersion") else None),
    ]:
        if ssl_const is None:
            continue
        try:
            wctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            wctx.check_hostname = False
            wctx.verify_mode    = ssl.CERT_NONE
            wctx.minimum_version = ssl_const
            wctx.maximum_version = ssl_const
            _connect_ssl(host, port, wctx, timeout=2.0)
            weak_found.append(proto_name)
        except Exception:
            pass

    result["weak_protocols"] = weak_found
    return result


def format_report(r: dict) -> list[str]:
    """Return a human-readable list of lines for a check() result."""
    lines = []
    if not r["ok"]:
        lines.append(f"ERROR: {r['error']}")
        return lines

    c = r["cert"]
    lines += [
        f"Host       : {r['host']}:{r['port']}",
        f"Protocol   : {r['protocol']}",
        f"Cipher     : {r['cipher']['name']}  ({r['cipher']['bits']} bits)",
        f"Subject    : {c['subject'].get('commonName', '?')}",
        f"Issuer     : {c['issuer'].get('organizationName', '?')}",
        f"SANs       : {', '.join(c['sans'][:6]) or '—'}",
        f"Valid from : {c['not_before']}",
        f"Valid until: {c['not_after']}",
    ]
    if r["expired"]:
        lines.append("⚠ CERTIFICATE EXPIRED!")
    elif r["expiry_warn"]:
        lines.append(f"⚠ Expires in {r['expiry_days']} days — renew soon!")
    else:
        lines.append(f"  Expires in : {r['expiry_days']} days")

    if r["weak_protocols"]:
        lines.append(f"⚠ Weak protocols supported: {', '.join(r['weak_protocols'])}")
    else:
        lines.append("  No weak TLS protocols detected.")

    return lines
