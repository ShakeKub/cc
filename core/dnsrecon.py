"""DNS reconnaissance — record lookup, zone transfer attempt, subdomain bruteforce."""
import concurrent.futures, socket, subprocess
from pathlib import Path

RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME", "PTR", "SRV", "CAA"]

def lookup(domain: str, rtype: str = "A") -> list[str]:
    """Query a DNS record type via dig/nslookup."""
    try:
        r = subprocess.run(["dig", "+short", rtype, domain],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except FileNotFoundError:
        pass
    # Fallback: nslookup
    try:
        r = subprocess.run(["nslookup", f"-type={rtype}", domain],
                           capture_output=True, text=True, timeout=8)
        results = []
        for line in r.stdout.splitlines():
            for kw in ("Address:", "mail exchanger", "nameserver", "text ="):
                if kw in line:
                    results.append(line.split("=", 1)[-1].split(":", 1)[-1].strip())
        if results:
            return results
    except Exception:
        pass
    # socket fallback for A
    if rtype == "A":
        try:
            return [socket.gethostbyname(domain)]
        except Exception:
            pass
    return []

def all_records(domain: str) -> dict[str, list[str]]:
    return {rt: lookup(domain, rt) for rt in RECORD_TYPES}

def zone_transfer(domain: str) -> list[str]:
    """Attempt AXFR zone transfer against each NS."""
    results = []
    ns_list = lookup(domain, "NS")
    for ns in ns_list:
        ns = ns.rstrip(".")
        try:
            r = subprocess.run(["dig", f"@{ns}", domain, "AXFR"],
                               capture_output=True, text=True, timeout=10)
            if "XFR size" in r.stdout or (r.returncode == 0 and len(r.stdout) > 200):
                results.append(f"NS {ns}: TRANSFER POSSIBLE\n{r.stdout[:2000]}")
            else:
                results.append(f"NS {ns}: transfer refused")
        except Exception as e:
            results.append(f"NS {ns}: {e}")
    return results or ["No NS records found"]

def bruteforce_subdomains(domain: str, wordlist: list[str] | None = None,
                           max_workers: int = 50,
                           progress_cb=None) -> list[dict]:
    if wordlist is None:
        wordlist = _default_wordlist()
    found = []
    done = [0]
    def _check(sub):
        done[0] += 1
        if progress_cb: progress_cb(done[0], len(wordlist), sub)
        fqdn = f"{sub}.{domain}"
        try:
            ip = socket.gethostbyname(fqdn)
            return {"subdomain": fqdn, "ip": ip}
        except socket.gaierror:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r in ex.map(_check, wordlist):
            if r: found.append(r)
    return sorted(found, key=lambda x: x["subdomain"])

def _default_wordlist() -> list[str]:
    wl = Path(__file__).parent / "wordlist.txt"
    common = ["www","mail","ftp","smtp","pop","imap","webmail","remote","vpn",
              "api","dev","staging","test","beta","admin","portal","shop","blog",
              "forum","wiki","docs","cdn","static","assets","m","mobile","app",
              "ns1","ns2","mx","mx1","mx2","autodiscover","autoconfig","cpanel",
              "webdisk","whm","ftp2","sftp","ssh","git","svn","jira","confluence",
              "jenkins","gitlab","grafana","kibana","elasticsearch","redis","db","sql",
              "mysql","postgres","mongo","backup","vpn2","remote2","intranet","internal"]
    if wl.is_file():
        extra = [l.strip() for l in wl.read_text(errors="replace").splitlines()
                 if l.strip() and not l.startswith("#")]
        common = list(dict.fromkeys(common + extra[:500]))
    return common
