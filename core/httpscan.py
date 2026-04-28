"""HTTP security headers scanner."""
import http.client, socket, ssl, urllib.parse

SECURITY_HEADERS = {
    "strict-transport-security":  ("HSTS",            "high"),
    "content-security-policy":    ("CSP",             "high"),
    "x-frame-options":            ("X-Frame-Options", "medium"),
    "x-content-type-options":     ("X-Content-Type",  "medium"),
    "referrer-policy":            ("Referrer-Policy", "low"),
    "permissions-policy":         ("Permissions-Policy","low"),
    "x-xss-protection":           ("X-XSS-Protection","low"),
    "cross-origin-opener-policy": ("COOP",            "low"),
    "cross-origin-resource-policy":("CORP",           "low"),
}

INFO_HEADERS = ["server", "x-powered-by", "x-aspnet-version", "x-aspnetmvc-version",
                "x-generator", "x-drupal-cache", "x-wordpress-cache"]

def scan(url: str, timeout: int = 10) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    host   = parsed.hostname or ""
    port   = parsed.port
    path   = parsed.path or "/"
    https  = parsed.scheme == "https"

    result = {
        "url": url, "host": host, "https": https,
        "status": None, "final_url": url,
        "redirect_to_https": False,
        "headers_present": {}, "headers_missing": [],
        "info_leaks": {}, "cookies": [],
        "grade": "?", "issues": [],
    }

    # Try HTTPS first, fall back to HTTP
    raw_headers: dict[str, str] = {}
    try:
        if https:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, port or 443, timeout=timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port or 80, timeout=timeout)
        conn.request("HEAD", path, headers={"User-Agent": "Mozilla/5.0 (security-scanner/1.0)"})
        resp = conn.getresponse()
        result["status"] = resp.status
        raw_headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()

        # Check redirect HTTP→HTTPS
        if not https and resp.status in (301, 302, 307, 308):
            loc = raw_headers.get("location", "")
            if loc.startswith("https://"):
                result["redirect_to_https"] = True
    except ssl.SSLError as e:
        result["issues"].append(f"SSL error: {e}")
    except Exception as e:
        result["issues"].append(f"Connection failed: {e}")
        return result

    # Security headers
    for hdr, (label, severity) in SECURITY_HEADERS.items():
        if hdr in raw_headers:
            result["headers_present"][label] = raw_headers[hdr]
        else:
            result["headers_missing"].append({"header": label, "severity": severity})

    # Info leaks
    for hdr in INFO_HEADERS:
        if hdr in raw_headers:
            result["info_leaks"][hdr] = raw_headers[hdr]

    # Cookies
    for hdr_val in [v for k, v in raw_headers.items() if k == "set-cookie"]:
        flags = {
            "secure":   "secure" in hdr_val.lower(),
            "httponly": "httponly" in hdr_val.lower(),
            "samesite": "samesite" in hdr_val.lower(),
        }
        result["cookies"].append({"raw": hdr_val[:120], **flags})

    # Grade
    missing_high = sum(1 for m in result["headers_missing"] if m["severity"] == "high")
    missing_med  = sum(1 for m in result["headers_missing"] if m["severity"] == "medium")
    if not https:
        result["grade"] = "F"
    elif missing_high >= 2:
        result["grade"] = "D"
    elif missing_high == 1:
        result["grade"] = "C"
    elif missing_med >= 2:
        result["grade"] = "B"
    elif missing_med == 1:
        result["grade"] = "B+"
    else:
        result["grade"] = "A"

    if result["info_leaks"]:
        result["issues"].append("Server tech info exposed via headers")
    for ck in result["cookies"]:
        if not ck["secure"]:   result["issues"].append(f"Cookie missing Secure flag")
        if not ck["httponly"]: result["issues"].append(f"Cookie missing HttpOnly flag")

    return result
