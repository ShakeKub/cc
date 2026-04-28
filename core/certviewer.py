"""SSL/TLS certificate viewer — installed certs + remote host certs."""
import os, platform, re, socket, ssl, subprocess
from datetime import datetime, timezone

def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def _days_until(dt: datetime) -> int:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - now).days

def check_host(host: str, port: int = 443, timeout: int = 8) -> dict:
    """Fetch and analyze the TLS certificate of a remote host."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                proto  = ssock.version()
        not_after  = ssl.cert_time_to_seconds(cert["notAfter"])
        not_before = ssl.cert_time_to_seconds(cert["notBefore"])
        exp_dt  = datetime.fromtimestamp(not_after,  tz=timezone.utc)
        st_dt   = datetime.fromtimestamp(not_before, tz=timezone.utc)
        days_left = _days_until(exp_dt)
        subject = dict(x[0] for x in cert.get("subject", []))
        issuer  = dict(x[0] for x in cert.get("issuer",  []))
        sans    = [v for t, v in cert.get("subjectAltName", []) if t == "DNS"]
        return {
            "host": host, "port": port,
            "subject_cn": subject.get("commonName", ""),
            "issuer_cn":  issuer.get("commonName", ""),
            "issuer_org": issuer.get("organizationName", ""),
            "not_before": st_dt.strftime("%Y-%m-%d"),
            "not_after":  exp_dt.strftime("%Y-%m-%d"),
            "days_left":  days_left,
            "expired":    days_left < 0,
            "expiry_warn": 0 <= days_left <= 30,
            "sans":       sans[:10],
            "cipher":     cipher[0] if cipher else "",
            "protocol":   proto or "",
            "valid":      True,
        }
    except ssl.SSLCertVerificationError as e:
        return {"host": host, "port": port, "valid": False, "error": f"Cert invalid: {e}"}
    except Exception as e:
        return {"host": host, "port": port, "valid": False, "error": str(e)}

def list_system_certs() -> list[dict]:
    """List certificates from the system store."""
    sys = platform.system()
    if sys == "Windows":   return _win_certs()
    if sys == "Darwin":    return _mac_certs()
    return _linux_certs()

def _win_certs() -> list[dict]:
    certs = []
    for store in ("My", "Root", "CA"):
        rc, out, _ = _run(["certutil", "-store", store])
        current: dict = {"store": store}
        for line in out.splitlines():
            line = line.strip()
            if "Subject:" in line:
                current["subject"] = line.split("Subject:",1)[1].strip()
            elif "NotAfter:" in line or "Platnost do:" in line:
                raw = line.split(":",1)[1].strip()
                current["not_after"] = raw
                try:
                    dt = datetime.strptime(raw[:19], "%m/%d/%Y %H:%M %p") if "/" in raw \
                         else datetime.strptime(raw[:10], "%Y-%m-%d")
                    current["days_left"] = _days_until(dt.replace(tzinfo=timezone.utc))
                except Exception:
                    current["days_left"] = None
            elif "Issuer:" in line:
                current["issuer"] = line.split("Issuer:",1)[1].strip()
            elif line == "":
                if current.get("subject"):
                    current["expired"] = (current.get("days_left") or 1) < 0
                    certs.append(dict(current))
                    current = {"store": store}
    return certs

def _mac_certs() -> list[dict]:
    rc, out, _ = _run(["security", "find-certificate", "-a", "-p",
                        "/Library/Keychains/System.keychain"])
    certs, pem = [], []
    for line in out.splitlines():
        pem.append(line)
        if line == "-----END CERTIFICATE-----":
            ctx = ssl.create_default_context(cadata="\n".join(pem))
            pem = []
    # Fallback: just count
    rc2, out2, _ = _run(["security", "dump-keychain", "-r"])
    return [{"subject": l.strip(), "store": "System"} for l in out2.splitlines()
            if '"labl"' in l][:50]

def _linux_certs() -> list[dict]:
    certs = []
    cert_dirs = ["/etc/ssl/certs", "/usr/share/ca-certificates"]
    for d in cert_dirs:
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d))[:100]:
                if fn.endswith((".pem", ".crt")):
                    certs.append({"subject": fn.replace(".pem","").replace(".crt",""),
                                  "store": d, "days_left": None})
    return certs
