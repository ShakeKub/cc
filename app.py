"""System Cleaner - pure terminal interface."""

import json
import os
import queue as _queue
import sys
import threading
from pathlib import Path

from core.logger import CleanerLogger
from core.i18n import t, set_language, get_language, available_languages

# ── Load language from config ────────────────────────────────
def _load_language_from_config():
    cfg_path = Path(__file__).parent / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        lang = cfg.get("language", "en")
        set_language(lang)
    except Exception:
        set_language("en")

# ── ANSI colours ────────────────────────────────────────────
R  = "\033[31m"   # red
G  = "\033[32m"   # green
Y  = "\033[33m"   # yellow
C  = "\033[36m"   # cyan
W  = "\033[37m"   # white
DIM = "\033[2m"
B  = "\033[1m"    # bold
RST = "\033[0m"   # reset


def clr():
    os.system("cls" if os.name == "nt" else "clear")


def sep(char="─", n=60):
    print(DIM + char * n + RST)


def header(title=""):
    clr()
    print(f"{G}{B}")
    print("  ███████╗██╗   ██╗███████╗     ██████╗██╗     ███████╗ █████╗ ███╗   ██╗")
    print("  ██╔════╝╚██╗ ██╔╝██╔════╝    ██╔════╝██║     ██╔════╝██╔══██╗████╗  ██║")
    print("  ███████╗ ╚████╔╝ ███████╗    ██║     ██║     █████╗  ███████║██╔██╗ ██║")
    print("  ╚════██║  ╚██╔╝  ╚════██║    ██║     ██║     ██╔══╝  ██╔══██║██║╚██╗██║")
    print("  ███████║   ██║   ███████║    ╚██████╗███████╗███████╗██║  ██║██║ ╚████║")
    print("  ╚══════╝   ╚═╝   ╚══════╝     ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝")
    print(f"{RST}")
    sep()
    if title:
        print(f"  {C}{B}{title}{RST}")
        sep()


def prompt(text=""):
    try:
        return input(f"{Y}>{RST} {text}").strip()
    except (KeyboardInterrupt, EOFError):
        return "q"


def nav_prompt() -> str:
    """
    Prompt that also detects left/right/up/down arrow keys on Windows.
    Returns '__next__' or '__prev__' for arrow keys, otherwise the typed string.
    Falls back to regular prompt() on non-Windows.
    """
    if os.name == "nt":
        try:
            import msvcrt
            print(f"  {Y}>{RST} ", end="", flush=True)
            chars: list[str] = []
            while True:
                ch = msvcrt.getch()
                if ch in (b"\xe0", b"\x00"):        # extended key prefix
                    ch2 = msvcrt.getch()
                    if ch2 in (b"M", b"P"):          # right / down → next page
                        print()
                        return "__next__"
                    if ch2 in (b"K", b"H"):          # left / up → prev page
                        print()
                        return "__prev__"
                    continue
                if ch == b"\r":                      # Enter
                    print()
                    return "".join(chars).strip()
                if ch == b"\x08":                    # Backspace
                    if chars:
                        chars.pop()
                        print("\b \b", end="", flush=True)
                    continue
                if ch == b"\x03":                    # Ctrl-C
                    raise KeyboardInterrupt
                decoded = ch.decode("utf-8", errors="replace")
                print(decoded, end="", flush=True)
                chars.append(decoded)
        except KeyboardInterrupt:
            return "q"
        except Exception:
            pass
    return prompt()


def ok(msg):
    print(f"  {G}[+]{RST} {msg}")


def err(msg):
    print(f"  {R}[!]{RST} {msg}")


def info(msg):
    print(f"  {C}[*]{RST} {msg}")


def warn(msg):
    print(f"  {Y}[~]{RST} {msg}")


def pause():
    try:
        input(f"\n  {DIM}{t('prompt.press_enter')}{RST}")
    except (KeyboardInterrupt, EOFError):
        pass


def _parse_nums(s: str, upper: int) -> list[int]:
    """
    Parse comma- or space-separated 1-based numbers into valid 0-based indices.
    Accepts '1,3,5', '1 3 5', or '1, 3, 5'. Silently drops out-of-range values.
    """
    indices = []
    for tok in s.replace(",", " ").split():
        try:
            n = int(tok) - 1
            if 0 <= n < upper:
                indices.append(n)
        except ValueError:
            pass
    return indices


def fmt_bytes(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ── MAIN MENU ───────────────────────────────────────────────

def _menu_categories():
    """Return categorised menu structure. Rebuilt each loop so t() reflects current language."""
    return [
        (t("cat.cleaning"), [
            ("1",  t("menu.system_scan")),
            ("2",  t("menu.quick_clean")),
            ("3",  t("menu.standard_clean")),
            ("4",  t("menu.deep_clean")),
            ("5",  t("menu.team_clean")),
        ]),
        (t("cat.file_tools"), [
            ("6",  t("menu.duplicates")),
            ("7",  t("menu.large_files")),
            ("8",  t("menu.empty_folders")),
            ("9",  t("menu.secure_wipe")),
            ("10", t("menu.recovery")),
        ]),
        (t("cat.tools"), [
            ("11", t("menu.browser_tools")),
            ("12", t("menu.process_mgr")),
            ("13", t("menu.network_tools")),
            ("14", t("menu.startup_mgr")),
            ("15", t("menu.disk_tools")),
            ("16", t("menu.registry")),
            ("17", t("menu.optimizer")),
            ("18", t("menu.privacy")),
            ("19", t("menu.uninstaller")),
            ("20", t("menu.autoruns")),
            ("21", t("menu.context_menu")),
        ]),
        (t("cat.monitoring"), [
            ("22", t("menu.app_tracer")),
            ("23", t("menu.scout_mode")),
            ("24", t("menu.health")),
            ("25", t("menu.crash_logs")),
            ("26", t("menu.disk_health")),
        ]),
        (t("cat.system"), [
            ("27", t("menu.history_mgr")),
            ("28", t("menu.restore_points")),
            ("29", t("menu.scheduler")),
            ("30", t("menu.logs")),
            ("31", t("menu.language")),
        ]),
    ]


def _print_menu_categories(categories):
    COL_W = 28  # width of each column entry (number + label)
    for cat_label, items in categories:
        # category header
        label_pad = 54 - len(cat_label)
        print(f"  {DIM}── {cat_label} {'─' * max(label_pad, 2)}{RST}")
        # items in pairs
        for i in range(0, len(items), 2):
            num_l, lbl_l = items[i]
            left  = f"  {C}[{num_l:>2}]{RST} {lbl_l}"
            if i + 1 < len(items):
                num_r, lbl_r = items[i + 1]
                right = f"  {C}[{num_r:>2}]{RST} {lbl_r}"
            else:
                right = ""
            print(f"{left:<{COL_W + 12}}{right}")
        print()


_DISPATCH = {
    "1":  lambda l: menu_scan(l),
    "2":  lambda l: menu_clean(l, "quick"),
    "3":  lambda l: menu_clean(l, "standard"),
    "4":  lambda l: menu_clean(l, "deep"),
    "5":  lambda l: menu_team_clean(l),
    "6":  lambda l: menu_duplicates(l),
    "7":  lambda l: menu_large_files(l),
    "8":  lambda l: menu_empty_folders(l),
    "9":  lambda l: menu_secure_wipe(l),
    "10": lambda l: menu_recovery(l),
    "11": lambda l: menu_browser(l),
    "12": lambda l: menu_process(l),
    "13": lambda l: menu_network(l),
    "14": lambda l: menu_startup(l),
    "15": lambda l: menu_disk(l),
    "16": lambda l: menu_registry(l),
    "17": lambda l: menu_optimizer(l),
    "18": lambda l: menu_privacy(l),
    "19": lambda l: menu_uninstaller(l),
    "20": lambda l: menu_autoruns(l),
    "21": lambda l: menu_context_menu(l),
    "22": lambda l: menu_tracer(l),
    "23": lambda l: menu_scout(l),
    "24": lambda l: menu_health(l),
    "25": lambda l: menu_crash_logs(l),
    "26": lambda l: menu_disk_health(l),
    "27": lambda l: menu_history(l),
    "28": lambda l: menu_restore_points(l),
    "29": lambda l: menu_scheduler(l),
    "30": lambda l: menu_logs(l),
    "31": lambda l: menu_language(l),
}


def main_menu(logger: CleanerLogger):
    import psutil
    _load_language_from_config()
    while True:
        header()

        # status bar
        try:
            cpu  = psutil.cpu_percent(interval=0)
            ram  = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
            print(f"  CPU {cpu:.0f}%  │  RAM {ram.percent:.0f}% ({fmt_bytes(ram.used)}/{fmt_bytes(ram.total)})  │  Disk free {fmt_bytes(disk.free)}")
        except Exception:
            pass

        admin_tag = f"{G}[{t('status.admin')}]{RST}" if is_admin() else f"{Y}[{t('status.no_admin')}]{RST}"
        print(f"  {admin_tag}")
        sep()

        _print_menu_categories(_menu_categories())

        print(f"  {C}[ 0]{RST} {t('menu.exit')}")
        sep()
        choice = prompt()

        if choice in ("0", "q", "exit", "quit"):
            clr()
            print(f"\n  {G}{t('app.bye')}{RST}\n")
            logger.export_json()
            sys.exit(0)

        action = _DISPATCH.get(choice)
        if action:
            action(logger)
        else:
            err(t("app.unknown_option"))
            pause()


# ── 1. SCAN ─────────────────────────────────────────────────

def menu_scan(logger: CleanerLogger):
    header(t("hdr.system_scan"))
    info(t("scan.scanning"))
    try:
        from core.cleaner import scan_all
        results = scan_all(logger)
        sep()
        ok(t("scan.temp_files", count=results.get('temp_files', 0), size=fmt_bytes(results.get('temp_size', 0))))
        for cat, d in results.get("categories", {}).items():
            print(f"    {cat:<30} {d.get('count',0):>5} items   {fmt_bytes(d.get('size',0)):>10}")
        sep()
        ok(t("scan.total", size=fmt_bytes(results.get('temp_size', 0))))
    except Exception as e:
        err(t("scan.failed", err=e))

    info(t("scan.check_procs"))
    try:
        from core.process import list_processes
        procs = list_processes(sort_by="memory", logger=logger)
        suspicious = [p for p in procs if p.get("suspicious")]
        if suspicious:
            sep()
            warn(t("scan.suspicious", count=len(suspicious)))
            for p in suspicious:
                reasons = p["suspicious"].get("reasons", [])
                risk = p["suspicious"].get("risk", "?")
                rc = R if risk == "high" else Y
                print(f"  {rc}[{risk.upper()}]{RST}  {p['name']:<28} PID {p['pid']:>7}  {', '.join(reasons[:2])}")
        else:
            ok(t("scan.no_sus"))
    except Exception as e:
        warn(t("scan.proc_skip", err=e))

    pause()


# ── 2/3/4. CLEAN ────────────────────────────────────────────

_PROFILE_HDR = {"quick": "hdr.quick_clean", "standard": "hdr.standard_clean", "deep": "hdr.deep_clean"}


def menu_clean(logger: CleanerLogger, profile: str):
    header(t(_PROFILE_HDR.get(profile, "hdr.deep_clean")))
    warn(t("clean.warning", profile=profile))
    confirm = prompt(t("prompt.type_yes_confirm"))
    if confirm.upper() not in ("YES", "ANO"):
        info(t("clean.cancelled"))
        pause()
        return
    info(t("clean.cleaning"))
    try:
        import psutil, json
        from core.cleaner import clean_all

        # Snapshot disk usage BEFORE cleaning so we can show real delta
        disk_root = "C:\\" if os.name == "nt" else "/"
        try:
            disk_before = psutil.disk_usage(disk_root).free
        except Exception:
            disk_before = None

        cfg_path = Path(__file__).parent / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        p = cfg.get("cleaning_profiles", {}).get(profile)
        results = clean_all(logger, p)
        freed_reported = results.get("total_freed", 0)

        # Measure real disk delta for honest reporting
        try:
            disk_after = psutil.disk_usage(disk_root).free
            disk_delta = disk_after - disk_before if disk_before is not None else 0
        except Exception:
            disk_delta = 0

        sep()
        ok(t("clean.done", size=fmt_bytes(freed_reported)))
        if disk_delta > 0:
            ok(t("clean.disk_gain", size=fmt_bytes(disk_delta), root=disk_root))
        elif disk_before is not None:
            info(t("clean.unchanged"))
        for name, size in results.get("actions", []):
            display = fmt_bytes(size) if size else "done"
            print(f"    {name:<35} {display}")
    except Exception as e:
        err(t("clean.failed", err=e))
    pause()


# ── 5. BROWSER ──────────────────────────────────────────────

def menu_browser(logger: CleanerLogger):
    while True:
        header(t("hdr.browser"))
        print(f"  {C}[1]{RST} {t('browser.detect')}")
        print(f"  {C}[2]{RST} {t('browser.cache')}")
        print(f"  {C}[3]{RST} {t('browser.cookies')}")
        print(f"  {C}[4]{RST} {t('browser.all')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            try:
                from core.browser import detect_installed_browsers
                browsers = detect_installed_browsers()
                sep()
                if not browsers:
                    warn(t("browser.none"))
                for b in browsers:
                    ok(f"{b['display_name']:<20} profiles: {b['profiles']}  cache: {fmt_bytes(b['cache_size'])}")
            except Exception as e:
                err(str(e))
            pause()
        elif c in ("2", "3", "4"):
            mode = {"2": "cache", "3": "cookies", "4": "all"}[c]
            warn(t("browser.will_clean", mode=mode))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    from core.browser import clean_all_browsers
                    kwargs = {mode: True} if mode != "all" else {"cache": True, "cookies": True, "history": True}
                    results = clean_all_browsers(logger, **kwargs)
                    total = sum(sum(v.values()) for v in results.values())
                    ok(t("browser.freed", size=fmt_bytes(total)))
                except Exception as e:
                    err(str(e))
            else:
                info(t("browser.cancelled"))
            pause()


# ── 6. PROCESS ──────────────────────────────────────────────

def menu_process(logger: CleanerLogger):
    while True:
        header(t("hdr.process"))
        info(t("proc.loading"))
        try:
            from core.process import list_processes
            procs = list_processes(sort_by="memory", logger=logger)
            sep()
            print(f"  {'PID':>7}  {'Name':<28}  {'CPU%':>6}  {'Memory':>10}  {'Status':<10}")
            sep("-")
            for p in procs[:30]:
                flags = ""
                if p.get("is_system"):  flags += " SYS"
                if p.get("suspicious"): flags += f" {R}SUS{RST}"
                if p.get("is_heavy"):   flags += f" {Y}HVY{RST}"
                print(f"  {p['pid']:>7}  {p['name']:<28}  {p['cpu_percent']:>5.1f}%  {fmt_bytes(p['memory_bytes']):>10}  {p['status']:<10}{flags}")
            sep()
            print(f"  {t('proc.total', count=len(procs))}")
        except Exception as e:
            err(str(e))
            pause()
            break

        print(f"\n  {C}[k 1,3]{RST} Kill by #   {C}[f]{RST} {t('proc.filter')}   {C}[r]{RST} {t('proc.refresh')}   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0": break
        elif cmd == "r": continue
        elif cmd == "f":
            name_filter = prompt(t("proc.filter_ask")).strip().lower()
            if name_filter:
                try:
                    from core.process import list_processes
                    all_procs = list_processes(sort_by="memory", logger=logger)
                    filtered = [p for p in all_procs if name_filter in p["name"].lower()]
                    sep()
                    for p in filtered:
                        flags = ""
                        if p.get("suspicious"): flags += f" {R}SUS{RST}"
                        print(f"  {p['pid']:>7}  {p['name']:<28}  {p['cpu_percent']:>5.1f}%  {fmt_bytes(p['memory_bytes']):>10}  {p['status']}{flags}")
                    info(t("proc.filter_res", count=len(filtered), query=name_filter))
                except Exception as e:
                    err(str(e))
            pause()
        else:
            parts = cmd.split(None, 1)
            if parts and parts[0] == "k" and len(parts) > 1:
                idxs = _parse_nums(parts[1], len(procs[:30]))
                targets = [procs[:30][i] for i in idxs]
                if not targets:
                    err(t("proc.bad_pid")); pause(); continue
                warn(f"Kill {len(targets)} process(es): " +
                     ", ".join(f"{p['name']}({p['pid']})" for p in targets))
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    from core.process import kill_process
                    killed = sum(1 for p in targets if kill_process(p["pid"], logger))
                    ok(f"Killed {killed}/{len(targets)} process(es).")
                pause()


# ── 7. NETWORK ──────────────────────────────────────────────

def menu_network(logger: CleanerLogger):
    while True:
        header(t("hdr.network"))
        print(f"  {C}[1]{RST} {t('net.connections')}")
        print(f"  {C}[2]{RST} {t('net.flush')}")
        print(f"  {C}[3]{RST} {t('net.ping')}")
        print(f"  {C}[4]{RST} {t('net.diag')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            try:
                from core.network import get_active_connections, get_ip_info
                info_data = get_ip_info(logger)
                conns = get_active_connections(logger)
                sep()
                print(f"  Hostname : {info_data.get('hostname','N/A')}")
                for iface in info_data.get("interfaces", []):
                    if iface.get("is_up"):
                        for addr in iface.get("addresses", []):
                            if addr.get("type") == "IPv4":
                                print(f"  {iface['name']:<20} {addr['address']}")
                if info_data.get("default_gateway"):
                    print(f"  Gateway  : {info_data['default_gateway']}")
                sep()
                print(f"  {'PID':>7}  {'Process':<20}  {'Local':<22}  {'Remote':<22}  {'Status'}")
                sep("-")
                for conn in conns[:25]:
                    print(f"  {conn['pid']:>7}  {conn['process']:<20}  {conn['local_address']:<22}  {conn['remote_address']:<22}  {conn['status']}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            try:
                from core.network import flush_dns
                success = flush_dns(logger)
                ok(t("net.flushed")) if success else err(t("net.flush_fail"))
            except Exception as e:
                err(str(e))
            pause()
        elif c == "3":
            host = prompt(t("net.ping_ask"))
            if host:
                import subprocess
                result = subprocess.run(["ping", "-n", "4", host], capture_output=True, text=True)
                print(result.stdout or result.stderr)
            pause()
        elif c == "4":
            try:
                from core.network import run_diagnostics
                results = run_diagnostics(logger)
                sep()
                for item in results:
                    sym = f"{G}PASS{RST}" if item["status"] == "pass" else f"{R}FAIL{RST}"
                    print(f"  [{sym}] {item['test']:<30} {item.get('detail','')}")
            except Exception as e:
                err(str(e))
            pause()


# ── 8. STARTUP ──────────────────────────────────────────────

def menu_startup(logger: CleanerLogger):
    while True:
        header(t("hdr.startup"))
        info(t("startup.loading"))
        try:
            from core.startup import get_startup_entries
            entries = get_startup_entries(logger)
        except Exception as e:
            err(str(e))
            pause()
            break
        sep()
        print(f"  {'#':>3}  {'Name':<30}  {'Status':<10}  {'Impact':<8}  {'Type'}")
        sep("-")
        for i, e in enumerate(entries):
            status = f"{G}{t('startup.enabled')}{RST}" if e.get("enabled") else f"{R}{t('startup.disabled')}{RST}"
            impact = e.get("impact", "medium")
            icolor = G if impact == "low" else Y if impact == "medium" else R
            flag = f" {R}[SUS]{RST}" if e.get("suspicious") else ""
            print(f"  {i+1:>3}  {e['name']:<30}  {status:<10}  {icolor}{impact:<8}{RST}  {e.get('type','')}{flag}")
        sep()
        print(f"  {t('startup.total', count=len(entries))}")
        print(f"\n  {C}[e 1,3]{RST} {t('startup.enable')}   {C}[d 1,3]{RST} {t('startup.disable')}   {C}[x 1,3]{RST} {t('startup.remove')}   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0": break
        parts = cmd.split(None, 1)
        if len(parts) == 2 and parts[0] in ("e", "d", "x"):
            idxs = _parse_nums(parts[1], len(entries))
            if not idxs:
                err(t("startup.bad_num")); pause(); continue
            sel = [entries[i] for i in idxs]
            if parts[0] == "e":
                from core.startup import enable_startup_entry
                done = sum(1 for entry in sel if enable_startup_entry(entry, logger))
                ok(f"Enabled {done}/{len(sel)} entry/entries.")
            elif parts[0] == "d":
                from core.startup import disable_startup_entry
                done = sum(1 for entry in sel if disable_startup_entry(entry, logger))
                ok(f"Disabled {done}/{len(sel)} entry/entries.")
            elif parts[0] == "x":
                names = ", ".join(e["name"] for e in sel)
                warn(f"Remove {len(sel)} startup entry/entries: {names[:80]}?")
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    from core.startup import remove_startup_entry
                    done = sum(1 for entry in sel if remove_startup_entry(entry, logger))
                    ok(f"Removed {done}/{len(sel)} entry/entries.")
            pause()


# ── 9. DISK ─────────────────────────────────────────────────

def menu_disk(logger: CleanerLogger):
    while True:
        header(t("hdr.disk"))
        root = "C:\\" if os.name == "nt" else "/"
        try:
            from core.disk import get_disk_usage
            du = get_disk_usage(root, logger)
            if "error" not in du:
                pct = du.get("percent_used", 0)
                bar_len = 40
                filled = int(pct / 100 * bar_len)
                bar = f"{G}{'█'*filled}{'░'*(bar_len-filled)}{RST}"
                print(f"  {root}  [{bar}] {pct:.1f}%")
                print(f"  Total {fmt_bytes(du['total'])}  Used {fmt_bytes(du['used'])}  Free {fmt_bytes(du['free'])}")
        except Exception as e:
            err(str(e))
        sep()
        print(f"  {C}[1]{RST} {t('disk.large')}")
        print(f"  {C}[2]{RST} {t('disk.dupes')}")
        print(f"  {C}[3]{RST} {t('disk.empty')}")
        print(f"  {C}[4]{RST} {t('disk.analyze')}")
        print(f"  {C}[5]{RST} {t('disk.shred')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            info(t("disk.search_lg"))
            try:
                from core.disk import find_large_files
                files = find_large_files(root, min_size_mb=100, logger=logger)
                sep()
                for i, f in enumerate(files[:20]):
                    print(f"  {i+1:>3}. {f['name']:<35} {fmt_bytes(f['size']):>10}  {str(Path(f['path']).parent)[:40]}")
                ok(t("disk.lg_found", count=len(files)))
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            path = prompt(t("disk.dir_ask", root=root)) or root
            info(t("disk.scan_dup"))
            try:
                from core.disk import find_duplicate_files
                dupes = find_duplicate_files(path, logger=logger)
                sep()
                ok(t("disk.dup_found", count=len(dupes)))
                for i, group in enumerate(dupes[:10]):
                    print(f"  Group {i+1}:")
                    for f in group:
                        print(f"    {f}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "3":
            path = prompt(t("disk.path_ask", root=root)) or root
            try:
                from core.disk import find_empty_folders
                empties = find_empty_folders(path, logger)
                sep()
                for f in empties[:20]:
                    print(f"  {f}")
                ok(t("disk.emp_found", count=len(empties)))
            except Exception as e:
                err(str(e))
            pause()
        elif c == "4":
            path = prompt(t("disk.path_ask", root=root)) or root
            info("Analyzing...")
            try:
                from core.disk import analyze_directory
                results = analyze_directory(path, max_depth=2, logger=logger)
                sep()
                for entry in results[:20]:
                    print(f"  {fmt_bytes(entry.get('size',0)):>10}  {entry.get('path','')}")
                ok(t("disk.analyzed", count=len(results)))
            except Exception as e:
                err(str(e))
            pause()
        elif c == "5":
            path = prompt(t("disk.shred_ask"))
            if path:
                warn(t("disk.shred_warn", path=path))
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    try:
                        from core.disk import secure_shred
                        ok(t("disk.shred_ok")) if secure_shred(path, passes=3, logger=logger) else err(t("disk.shred_fail"))
                    except Exception as e:
                        err(str(e))
                else:
                    info(t("clean.cancelled"))
            pause()


# ── 10. REGISTRY ────────────────────────────────────────────

def menu_registry(logger: CleanerLogger):
    while True:
        header(t("hdr.registry"))
        print(f"  {C}[1]{RST} {t('reg.scan')}  +  fix selected  ({C}f 1,3{RST})")
        print(f"  {C}[2]{RST} {t('reg.fix_all')}")
        print(f"  {C}[3]{RST} {t('reg.backup')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            info(t("reg.scanning"))
            try:
                from core.registry import scan_invalid_entries, fix_selected_entries
                entries = scan_invalid_entries(logger)
                sep()
                print(f"  {'#':>3}  {'Category':<20}  {'Entry':<30}  {'Issue':<30}  Risk")
                sep("-")
                for i, e in enumerate(entries[:30]):
                    risk = e.get("risk","low")
                    rc = G if risk=="low" else Y if risk=="medium" else R
                    print(f"  {i+1:>3}  {e.get('category',''):<20}  {e.get('value_name','')[:30]:<30}  {e.get('issue','')[:30]:<30}  {rc}{risk}{RST}")
                ok(t("reg.found", count=len(entries)))
                sep()
                print(f"  {C}[f 1,3,5]{RST} Fix selected   {C}[Enter]{RST} Back")
                sep()
                fix_cmd = prompt()
                fix_parts = fix_cmd.split(None, 1)
                if fix_parts and fix_parts[0] == "f" and len(fix_parts) > 1:
                    idxs = _parse_nums(fix_parts[1], len(entries[:30]))
                    sel = [entries[:30][i] for i in idxs]
                    if sel:
                        warn(f"Fix {len(sel)} registry entry/entries?")
                        if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                            results2 = fix_selected_entries(sel, logger)
                            ok(t("reg.fixed", fixed=results2.get('fixed',0),
                                 failed=results2.get('failed',0),
                                 skipped=results2.get('skipped',0)))
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            warn(t("reg.fix_conf"))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    from core.registry import scan_invalid_entries, fix_all_invalid
                    entries = scan_invalid_entries(logger)
                    results = fix_all_invalid(entries, logger)
                    ok(t("reg.fixed", fixed=results['fixed'], failed=results['failed'], skipped=results['skipped']))
                except Exception as e:
                    err(str(e))
            pause()
        elif c == "3":
            try:
                from core.registry import backup_registry
                path = backup_registry(logger=logger)
                if path:
                    ok(t("reg.bak_ok", path=path))
                else:
                    err(t("reg.bak_fail"))
            except Exception as e:
                err(str(e))
            pause()


# ── 11. OPTIMIZER ───────────────────────────────────────────

def menu_optimizer(logger: CleanerLogger):
    while True:
        header(t("hdr.optimizer"))
        print(f"  {C}[1]{RST} {t('opt.ram')}")
        print(f"  {C}[2]{RST} {t('opt.services')}")
        print(f"  {C}[3]{RST} {t('opt.dis_svc')}")
        print(f"  {C}[4]{RST} {t('opt.en_svc')}")
        print(f"  {C}[5]{RST} {t('opt.plans')}")
        print(f"  {C}[6]{RST} {t('opt.switch_plan')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            info(t("opt.opt_ram"))
            try:
                from core.optimizer import optimize_ram
                result = optimize_ram(logger)
                sep()
                ok(t("opt.ram_freed", size=fmt_bytes(result.get('freed', 0))))
                print(f"  Before : {fmt_bytes(result['before_used'])}  ({result['before_percent']:.0f}%)")
                print(f"  After  : {fmt_bytes(result['after_used'])}  ({result['after_percent']:.0f}%)")
                print(f"  Processes trimmed : {result.get('trimmed_procs', 0)}")
                if result.get('skipped_procs', 0):
                    print(f"  {DIM}Skipped (no access): {result['skipped_procs']}{RST}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            try:
                from core.optimizer import list_optimizable_services
                svcs = list_optimizable_services(logger)
                sep()
                print(f"  {'#':>3}  {'Service':<35}  {'Status':<10}  {'Impact':<8}  Category")
                sep("-")
                for i, s in enumerate(svcs):
                    sc = G if s["status"]=="running" else R
                    ic = G if s["impact"]=="low" else Y if s["impact"]=="medium" else R
                    print(f"  {i+1:>3}  {s['display_name'][:35]:<35}  {sc}{s['status']:<10}{RST}  {ic}{s['impact']:<8}{RST}  {s.get('category','')}")
                ok(t("opt.svc_found", count=len(svcs)))
            except Exception as e:
                err(str(e))
            pause()
        elif c in ("3","4"):
            action = "disable" if c=="3" else "enable"
            name = prompt(t("opt.svc_ask", action=action))
            if name:
                try:
                    from core.optimizer import disable_service, enable_service
                    fn = disable_service if c=="3" else enable_service
                    ok(t("opt.svc_ok", action=action)) if fn(name, logger) else err(t("opt.svc_fail"))
                except Exception as e:
                    err(str(e))
            pause()
        elif c in ("5", "6"):
            try:
                from core.optimizer import get_power_plans, set_power_plan
                plans = get_power_plans(logger)
            except Exception as e:
                err(str(e)); pause(); continue

            sep()
            if not plans:
                warn("No power plans found.")
                pause()
                continue

            for i, p in enumerate(plans):
                active_tag = f"  {G}<-- ACTIVE{RST}" if p.get("active") else ""
                print(f"  {C}[{i+1}]{RST} {p.get('name', 'Unknown')}{active_tag}")

            if c == "5":
                pause()
                continue

            sep()
            choice_p = prompt("Select plan number: ").strip()
            try:
                idx = int(choice_p) - 1
                match = plans[idx]
                ok(t("opt.plan_ok")) if set_power_plan(match["guid"], logger) else err(t("opt.plan_fail"))
            except (ValueError, IndexError):
                err("Invalid number.")
            pause()


# ── 12. PRIVACY ─────────────────────────────────────────────

def menu_privacy(logger: CleanerLogger):
    while True:
        header(t("hdr.privacy"))
        print(f"  {C}[1]{RST} {t('priv.telemetry')}")
        print(f"  {C}[2]{RST} {t('priv.toggle_tel')}")
        print(f"  {C}[3]{RST} {t('priv.scan_track')}")
        print(f"  {C}[4]{RST} {t('priv.clean_track')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            try:
                from core.privacy import get_telemetry_status
                telemetry = get_telemetry_status(logger)
                sep()
                print(f"  {'Setting':<35}  {'Status':<10}  Description")
                sep("-")
                for item in telemetry:
                    s = f"{R}ON{RST}" if item["enabled"] else f"{G}OFF{RST}"
                    print(f"  {item['name']:<35}  {s:<10}  {item['description']}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            warn(t("priv.tog_conf"))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    from core.privacy import disable_all_telemetry
                    results = disable_all_telemetry(logger)
                    success_count = sum(1 for v in results.values() if v)
                    ok(t("priv.dis_count", count=success_count, total=len(results)))
                    for name, success in results.items():
                        sym = f"{G}OK{RST}" if success else f"{R}FAIL{RST}"
                        print(f"    [{sym}] {name}")
                except Exception as e:
                    err(str(e))
            pause()
        elif c == "3":
            try:
                from core.privacy import scan_tracking_files
                tracking = scan_tracking_files(logger)
                sep()
                for item in tracking:
                    print(f"  {item['category']:<25} {item['files']:>5} files  {fmt_bytes(item['size'])}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "4":
            warn(t("priv.clean_conf"))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    from core.privacy import clean_tracking_files
                    freed = clean_tracking_files(logger)
                    ok(t("priv.freed", size=fmt_bytes(freed)))
                except Exception as e:
                    err(str(e))
            pause()


# ── 13. TRACER ──────────────────────────────────────────────

def menu_tracer(logger: CleanerLogger):
    from core.tracer_session import TracerSession
    profile_path = Path(__file__).parent / "profiles"
    profile_path.mkdir(exist_ok=True)
    current_session = None

    while True:
        header(t("hdr.tracer"))
        sessions = TracerSession.load_sessions(str(profile_path))
        if current_session and current_session.is_running:
            print(f"  {G}[LIVE]{RST} Tracing {B}'{current_session.app_name}'{RST}  "
                  f"in  {current_session.watch_path}")
            print(f"  Created:{G}{len(current_session.created_files)}{RST}  "
                  f"Modified:{Y}{len(current_session.modified_files)}{RST}  "
                  f"Deleted:{R}{len(current_session.deleted_files)}{RST}")
        sep()
        print(f"  {C}[1]{RST} {t('tracer.start')}")
        print(f"  {C}[2]{RST} {t('tracer.stop_ses')}")
        print(f"  {C}[3]{RST} {t('tracer.list')}")
        print(f"  {C}[4]{RST} {t('tracer.view')}")
        print(f"  {C}[5]{RST} {t('tracer.clean')}")
        print(f"  {C}[6]{RST} {t('tracer.delete')}")
        print(f"  {C}[7]{RST} {t('tracer.deep')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            if current_session and current_session.is_running:
                current_session.stop()
            break

        elif c == "1":
            if current_session and current_session.is_running:
                warn(t("tracer.active"))
                pause()
                continue

            clr()
            sep()
            print(f"  {C}{B}{t('hdr.tracer_setup')}{RST}")
            sep()

            app_name = prompt(t("tracer.label_ask")).strip()
            if not app_name:
                continue

            default_path = os.path.expanduser("~")
            watch_path = prompt(t("tracer.watch_ask", path=default_path)).strip() or default_path
            if not os.path.isdir(watch_path):
                err(f"Directory not found: {watch_path}")
                pause()
                continue

            target_proc = prompt(t("tracer.target_ask")).strip() or None

            current_session = TracerSession(app_name, str(profile_path), logger)
            current_session.start(watch_path=watch_path, target_process=target_proc)

            clr()
            sep("═")
            print(f"  {G}{B}{t('tracer.live')}{RST}  {B}{app_name}{RST}")
            print(f"  watch : {watch_path}")
            if target_proc:
                print(f"  target: {Y}{target_proc}{RST}  (DLL injection monitoring ON)")
            sep("═")
            print(f"  {DIM}{t('tracer.legend')}{RST}  "
                  f"{G}FILE+{RST}=create  {Y}FILE~{RST}=modify  {R}FILE-{RST}=delete  "
                  f"{C}MOVE {RST}  "
                  f"{G}PROC+{RST}=new proc  {R}PROC-{RST}=killed  "
                  f"{R}{B}DLL  {RST}=injection  "
                  f"{C}NET  {RST}=connection  "
                  f"{Y}TARGET{RST}=target found")
            sep()
            print(f"  {DIM}Enter = stop{RST}\n")

            TYPE_COLOR = {
                "FILE+":  G,
                "FILE~":  Y,
                "FILE-":  R,
                "MOVE ":  C,
                "PROC+":  G,
                "PROC-":  R,
                "DLL  ":  R,
                "NET  ":  C,
                "TARGET": Y,
            }

            stop_flag = threading.Event()

            def _wait_enter():
                try:
                    input()
                except Exception:
                    pass
                stop_flag.set()

            threading.Thread(target=_wait_enter, daemon=True).start()

            while not stop_flag.is_set():
                try:
                    event = current_session.event_queue.get(timeout=0.2)
                    col = TYPE_COLOR.get(event["type"], W)
                    etype = event["type"]
                    if etype == "DLL  ":
                        print(f"  {DIM}{event['time']}{RST}  {R}{B}{etype}{RST}  {R}{event['path']}{RST}")
                    else:
                        print(f"  {DIM}{event['time']}{RST}  {col}{etype}{RST}  {event['path']}")
                except _queue.Empty:
                    pass

            current_session.stop()
            sep("═")
            ok(f"{t('tracer.saved')}  |  "
               f"files: {G}+{len(current_session.created_files)} ~{len(current_session.modified_files)} -{len(current_session.deleted_files)}{RST}  "
               f"procs: {G}+{len(current_session.new_processes)}{RST}  "
               f"DLLs: {R}{len(current_session.injected_dlls)}{RST}  "
               f"net: {C}{len(current_session.new_connections)}{RST}")
            current_session = None
            pause()

        elif c == "2":
            if current_session and current_session.is_running:
                current_session.stop()
                ok(t("tracer.stopped", name=current_session.app_name))
                current_session = None
            else:
                warn(t("tracer.no_active"))
            pause()

        elif c == "3":
            sep()
            if not sessions:
                warn(t("tracer.no_ses"))
            else:
                print(f"  {'Session ID':<20}  {'Label':<18}  {'Target':<15}  F+  F~  F-  Pr  DL  Net")
                sep("-")
                for s in sessions:
                    print(f"  {s.get('session_id',''):<20}  "
                          f"{s.get('app_name',''):<18}  "
                          f"{(s.get('target_process') or '-'):<15}  "
                          f"{len(s.get('created_files',[])):>3}  "
                          f"{len(s.get('modified_files',[])):>3}  "
                          f"{len(s.get('deleted_files',[])):>3}  "
                          f"{len(s.get('new_processes',[])):>3}  "
                          f"{R}{len(s.get('injected_dlls',[])):>3}{RST}  "
                          f"{len(s.get('new_connections',[])):>3}")
            pause()

        elif c == "4":
            sid = prompt(t("tracer.sid_ask"))
            session = next((s for s in sessions if s.get("session_id") == sid), None)
            if session:
                sep()
                # Show DLL injections first — highest severity
                dlls = session.get("injected_dlls", [])
                if dlls:
                    print(f"\n  {R}{B}DLL INJECTION ({len(dlls)}){RST}")
                    for d in dlls:
                        print(f"    {R}{d.get('time','')}  {d.get('dll','')}{RST}")

                net = session.get("new_connections", [])
                if net:
                    print(f"\n  {C}NETWORK ({len(net)}){RST}")
                    for n in net:
                        print(f"    {n.get('time','')}  {n.get('local','')}  →  {n.get('remote','')}  [{n.get('status','')}]")

                procs = session.get("new_processes", [])
                if procs:
                    print(f"\n  {G}NEW PROCESSES ({len(procs)}){RST}")
                    for p in procs:
                        print(f"    {p.get('time','')}  {p.get('name','')} (PID {p.get('pid','')})")

                for label, key, col in [
                    ("FILES CREATED",  "created_files",  G),
                    ("FILES MODIFIED", "modified_files",  Y),
                    ("FILES DELETED",  "deleted_files",   R),
                ]:
                    files = session.get(key, [])
                    if files:
                        print(f"\n  {col}{label} ({len(files)}){RST}")
                        for f in files[:30]:
                            print(f"    {f}")
                        if len(files) > 30:
                            print(f"    {DIM}... and {len(files)-30} more{RST}")
            else:
                err(t("tracer.not_found"))
            pause()

        elif c == "5":
            sid = prompt(t("tracer.sid_ask"))
            session = next((s for s in sessions if s.get("session_id") == sid), None)
            if session:
                files = session.get("created_files", [])
                warn(t("tracer.cln_conf", count=len(files), sid=sid))
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    try:
                        from core.uninstaller import remove_traced_files
                        freed = remove_traced_files(files, logger)
                        ok(f"Freed: {fmt_bytes(freed)}")
                    except Exception as e:
                        err(str(e))
            else:
                err(t("tracer.not_found"))
            pause()

        elif c == "6":
            sid = prompt(t("tracer.sid_ask"))
            f = profile_path / f"trace_{sid}.json"
            if f.exists():
                warn(t("tracer.del_conf", sid=sid))
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    f.unlink()
                    ok(t("tracer.deleted"))
            else:
                err(t("tracer.not_found"))
            pause()

        elif c == "7":
            app_name = prompt(t("tracer.app_ask"))
            if app_name:
                info(t("tracer.analyzing", name=app_name))
                try:
                    from core.tracer import AppTracer
                    tracer = AppTracer(app_name, logger=logger)
                    tracer.scan_all()
                    summary = tracer.get_summary()
                    sep()
                    ok(f"App: {summary.get('app_name')}")
                    print(f"  Total traces : {summary.get('total_traces',0)}")
                    print(f"  Files        : {summary.get('files',0)}")
                    print(f"  Registry     : {summary.get('registry',0)}")
                    print(f"  Services     : {summary.get('services',0)}")
                    print(f"  Total size   : {fmt_bytes(summary.get('total_size',0))}")
                except Exception as e:
                    err(str(e))
            pause()


# ── 14. UNINSTALLER ─────────────────────────────────────────

def menu_uninstaller(logger: CleanerLogger):
    while True:
        header("Uninstaller")
        print(f"  {C}[1]{RST} Installed programs")
        print(f"  {C}[2]{RST} Built-in Windows apps (Teams, Xbox, Cortana…)")
        print(f"  {C}[3]{RST} {R}Remove ALL bloatware{RST}  (Teams, Xbox, Cortana, News, Maps…)")
        print(f"  {C}[4]{RST} Find orphaned registry entries")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0":
            break
        elif c == "1":
            _menu_uninstaller_programs(logger)
        elif c == "2":
            _menu_uninstaller_builtin(logger)
        elif c == "3":
            _menu_remove_all_bloatware(logger)
        elif c == "4":
            try:
                from core.uninstaller import detect_orphaned_entries
                info("Scanning for orphaned registry entries...")
                orphans = detect_orphaned_entries(logger)
                sep()
                if not orphans:
                    ok("No orphaned entries found.")
                else:
                    print(f"  {'#':>4}  {'Name':<40}  Publisher")
                    sep("-")
                    for i, p in enumerate(orphans[:30]):
                        print(f"  {i+1:>4}  {p['name'][:40]:<40}  {p.get('publisher','')[:25]}")
                    ok(f"Found {len(orphans)} orphaned entries")
            except Exception as e:
                err(str(e))
            pause()


def _menu_remove_all_bloatware(logger: CleanerLogger):
    """Bulk-remove all apps in BLOATWARE_IDS."""
    header("Remove All Bloatware")
    print(f"  This will attempt to remove:")
    bloat_names = [
        "Microsoft Teams", "Cortana", "Xbox (all components)", "Mail & Calendar",
        "Maps", "Movies & TV", "Groove Music", "Mixed Reality Portal", "News",
        "Weather", "Solitaire Collection", "OneNote", "Paint 3D", "3D Viewer",
        "Skype", "Tips", "People", "Phone Link", "Get Help", "Feedback Hub",
        "Clipchamp", "Power Automate", "Bing Search", "Quick Assist",
        "MSN Sports/Finance", "Office Hub",
    ]
    for name in bloat_names:
        print(f"    {R}•{RST} {name}")
    sep()
    warn("Microsoft Store and Calculator are NOT included (kept by default).")
    warn("Admin rights required for full removal. Run as administrator for best results.")
    sep()
    scope_raw = prompt("Remove for [1] current user only  [2] ALL users  [0] Cancel: ").strip()
    if scope_raw == "0" or not scope_raw:
        return
    all_users = scope_raw == "2"
    scope_label = "all users" if all_users else "current user"
    warn(f"Remove all bloatware for {scope_label}? This cannot be undone.")
    if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
        info("Cancelled.")
        pause()
        return

    info("Querying installed bloatware — this may take a minute…")
    try:
        from core.uninstaller import remove_all_bloatware
        results = remove_all_bloatware(logger, all_users=all_users)
    except Exception as e:
        err(str(e))
        pause()
        return

    sep()
    removed = [name for name, ok2 in results.items() if ok2]
    failed  = [name for name, ok2 in results.items() if not ok2]
    for name in removed:
        print(f"  {G}[+]{RST} Removed: {name}")
    for name in failed:
        print(f"  {R}[!]{RST} Failed:  {name}")
    sep()
    ok(f"Done — {len(removed)} removed, {len(failed)} failed.")
    if failed:
        warn("Failures may be due to missing packages or insufficient permissions.")
    pause()


def _menu_uninstaller_programs(logger: CleanerLogger):
    """List and uninstall regular programs from registry."""
    info("Loading installed programs...")
    try:
        from core.uninstaller import list_installed_programs
        all_programs = list_installed_programs(logger)
    except Exception as e:
        err(str(e))
        pause()
        return

    filtered = all_programs[:]
    active_filter = ""

    while True:
        header("Uninstaller — Programs")
        display = filtered[:40]
        print(f"  {'#':>4}  {'Name':<35}  {'Version':<15}  {'Publisher'}")
        sep("-")
        for i, p in enumerate(display):
            print(f"  {i+1:>4}  {p['name'][:35]:<35}  {p.get('version','')[:15]:<15}  {p.get('publisher','')[:25]}")
        if len(filtered) > 40:
            print(f"  {DIM}... and {len(filtered)-40} more{RST}")
        if active_filter:
            info(f"Filter active: '{active_filter}'  ({len(filtered)} results)")
        sep()
        print(f"  {C}[u #]{RST} Uninstall #   {C}[s word]{RST} Search   {C}[r]{RST} Reset filter   {C}[0]{RST} Back")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd == "r":
            filtered = all_programs[:]
            active_filter = ""
            continue
        parts = cmd.split(None, 1)
        if not parts:
            continue
        if parts[0] == "s" and len(parts) > 1:
            active_filter = parts[1]
            query = active_filter.lower()
            filtered = [p for p in all_programs if query in p["name"].lower()
                        or query in p.get("publisher", "").lower()]
            info(f"Showing {len(filtered)} matches for '{active_filter}'")
        elif parts[0] == "u" and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                prog = filtered[idx]
                warn(f"Uninstall '{prog['name']}'?")
                if prompt("Type YES: ").upper() == "YES":
                    try:
                        from core.uninstaller import uninstall_program
                        ok("Uninstall started.") if uninstall_program(prog, logger) else err("Failed.")
                    except Exception as e:
                        err(str(e))
            except (ValueError, IndexError):
                err("Invalid number.")
            pause()


def _menu_uninstaller_builtin(logger: CleanerLogger):
    """List and remove Windows built-in (AppX) applications."""
    info("Querying installed built-in apps via PowerShell…")
    try:
        from core.uninstaller import list_builtin_apps, uninstall_builtin_app
        apps = list_builtin_apps(logger)
    except Exception as e:
        err(str(e))
        pause()
        return

    if not apps:
        warn("No removable built-in apps found (or PowerShell unavailable).")
        pause()
        return

    while True:
        header("Uninstaller — Built-in Apps")
        print(f"  {'#':>4}  {'Display Name':<30}  {'Version':<15}  Package Name")
        sep("-")
        for i, a in enumerate(apps):
            print(f"  {i+1:>4}  {a['display_name'][:30]:<30}  {a.get('version','')[:15]:<15}  {a['package_name'][:35]}")
        sep()
        print(f"  {C}[r 1,3]{RST} Remove   {C}[ra 1,3]{RST} Remove for all users   {C}[0]{RST} Back")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        parts = cmd.split(None, 1)
        if not parts or parts[0] not in ("r", "ra") or len(parts) < 2:
            continue
        all_users = parts[0] == "ra"
        idxs = _parse_nums(parts[1], len(apps))
        if not idxs:
            err("Invalid number."); pause(); continue
        sel = [apps[i] for i in sorted(idxs, reverse=True)]  # reverse so pop() indices stay valid
        scope = "for all users" if all_users else "for current user"
        names = ", ".join(a["display_name"] for a in sel)
        warn(f"Remove {len(sel)} app(s) {scope}: {names[:80]}?")
        if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
            removed = 0
            for a in sel:
                orig_idx = apps.index(a)
                if uninstall_builtin_app(a, logger, all_users=all_users):
                    ok(f"Removed '{a['display_name']}'.")
                    apps.pop(orig_idx)
                    removed += 1
                else:
                    err(f"Failed: '{a['display_name']}'.")
            ok(f"Done — {removed}/{len(sel)} removed.")
        pause()


# ── 15. SCHEDULER ───────────────────────────────────────────

def menu_scheduler(logger: CleanerLogger):
    while True:
        header("Scheduler")
        print(f"  {C}[1]{RST} List scheduled tasks")
        print(f"  {C}[2]{RST} Create task")
        print(f"  {C}[3]{RST} Toggle task")
        print(f"  {C}[4]{RST} Delete task")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            try:
                from core.scheduler import list_scheduled_tasks
                tasks = list_scheduled_tasks(logger)
                sep()
                print(f"  {'Name':<20}  {'Schedule':<12}  {'Profile':<12}  Status")
                sep("-")
                for t in tasks:
                    s = f"{G}Active{RST}" if t.get("enabled") else f"{R}Disabled{RST}"
                    print(f"  {t.get('name',''):<20}  {t.get('schedule',''):<12}  {t.get('profile',''):<12}  {s}")
                ok(f"{len(tasks)} tasks")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            name     = prompt("Task name: ")
            schedule = prompt("Schedule (daily/weekly/hourly): ")
            profile  = prompt("Profile (quick/standard/deep): ")
            if name and schedule:
                try:
                    from core.scheduler import create_scheduled_task
                    ok("Task created.") if create_scheduled_task(name, schedule, profile or "standard", logger) else err("Failed to create task.")
                except Exception as e:
                    err(str(e))
            pause()
        elif c in ("3","4"):
            name = prompt("Task name: ")
            if name:
                try:
                    if c == "3":
                        from core.scheduler import list_scheduled_tasks, toggle_scheduled_task
                        tasks = list_scheduled_tasks(logger)
                        task = next((t for t in tasks if t.get("name") == name), None)
                        if task:
                            new_state = not task.get("enabled", True)
                            ok("Toggled.") if toggle_scheduled_task(name, new_state, logger) else err("Failed.")
                        else:
                            err(f"Task '{name}' not found.")
                    else:
                        warn(f"Delete task '{name}'?")
                        if prompt("Type YES: ").upper() == "YES":
                            from core.scheduler import delete_scheduled_task
                            ok("Deleted.") if delete_scheduled_task(name, logger) else err("Failed.")
                except Exception as e:
                    err(str(e))
            pause()


# ── 17. TEAM CLEAN ──────────────────────────────────────────

def menu_team_clean(logger: CleanerLogger):
    """All-in-one comprehensive clean: deep system + browsers + tracking files."""
    header("Team Clean — All-in-One")
    print(f"  This will run:")
    print(f"    {G}•{RST} Deep system clean   (temp, WU cache, logs, DNS, thumbnails)")
    print(f"    {G}•{RST} All-browser clean   (cache, cookies)")
    print(f"    {G}•{RST} Privacy clean       (tracking files, activity history)")
    sep()
    warn("ALL cleanable data will be removed. This cannot be undone.")
    confirm = prompt("Type YES to start: ")
    if confirm.upper() != "YES":
        info("Cancelled.")
        pause()
        return

    import psutil, json
    disk_root = "C:\\" if os.name == "nt" else "/"
    try:
        disk_before = psutil.disk_usage(disk_root).free
    except Exception:
        disk_before = None

    total_freed = 0

    # ── 1. Deep system clean ────────────────────────────────
    info("[1/3] Deep system clean...")
    try:
        from core.cleaner import clean_all
        cfg_path = Path(__file__).parent / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        deep_profile = cfg.get("cleaning_profiles", {}).get("deep")
        results = clean_all(logger, deep_profile)
        freed = results.get("total_freed", 0)
        total_freed += freed
        ok(f"System clean done  — {fmt_bytes(freed)}")
        for name, size in results.get("actions", []):
            if size:
                print(f"      {name:<30} {fmt_bytes(size)}")
    except Exception as e:
        err(f"System clean failed: {e}")

    # ── 2. Browser clean ────────────────────────────────────
    info("[2/3] Browser clean (cache + cookies)...")
    try:
        from core.browser import clean_all_browsers
        browser_results = clean_all_browsers(logger, cache=True, cookies=True, history=False)
        browser_freed = sum(sum(v.values()) for v in browser_results.values() if isinstance(v, dict))
        total_freed += browser_freed
        ok(f"Browser clean done — {fmt_bytes(browser_freed)}")
    except Exception as e:
        err(f"Browser clean failed: {e}")

    # ── 3. Privacy / tracking clean ─────────────────────────
    info("[3/3] Privacy clean (tracking files)...")
    try:
        from core.privacy import clean_tracking_files
        privacy_freed = clean_tracking_files(logger)
        total_freed += privacy_freed
        ok(f"Privacy clean done — {fmt_bytes(privacy_freed)}")
    except Exception as e:
        err(f"Privacy clean failed: {e}")

    # ── Summary ─────────────────────────────────────────────
    sep("═")
    ok(f"Team Clean complete!")
    print(f"  Files cleaned (reported) : {fmt_bytes(total_freed)}")
    try:
        disk_after = psutil.disk_usage(disk_root).free
        disk_delta = disk_after - disk_before if disk_before is not None else 0
        if disk_delta > 0:
            ok(f"Disk space actually gained: {fmt_bytes(disk_delta)}")
        else:
            info("Disk free space unchanged — files may still be cached by OS")
    except Exception:
        pass
    sep("═")
    pause()


# ── 16. LOGS ────────────────────────────────────────────────

def menu_logs(logger: CleanerLogger):
    while True:
        header("Logs & Reports")
        stats = logger.get_session_stats()
        sep()
        print(f"  Session start  : {stats.get('session_start','N/A')}")
        print(f"  Duration       : {stats.get('duration_seconds',0):.0f} s")
        print(f"  Total freed    : {stats.get('total_freed_readable','0 B')}")
        print(f"  Actions taken  : {stats.get('actions_taken',0)}")
        print(f"  Errors         : {stats.get('errors',0)}")
        sep()
        print(f"  {C}[1]{RST} Export TXT   {C}[2]{RST} Export JSON   {C}[3]{RST} Show last 20 entries   {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            p = logger.export_txt()
            ok(f"Saved: {p}")
            pause()
        elif c == "2":
            p = logger.export_json()
            ok(f"Saved: {p}")
            pause()
        elif c == "3":
            sep()
            for e in (logger.session_log or [])[-20:]:
                ts = str(e.get("timestamp",""))[-8:]
                sym = f"{G}✓{RST}" if e.get("success") else f"{R}✗{RST}"
                print(f"  {ts}  [{sym}]  {e.get('action',''):<25}  {e.get('details','')[:50]}")
            pause()


# ── 18. SCOUT MODE ──────────────────────────────────────────

def menu_scout(logger: CleanerLogger):
    """Scout Mode — deep real-time monitoring of a specific application."""
    from core.scout import ScoutSession
    profile_path = Path(__file__).parent / "profiles"
    profile_path.mkdir(exist_ok=True)
    current: ScoutSession | None = None

    # Event type display config
    TYPE_COLOR = {
        "CREATE":        G,
        "MODIFY":        Y,
        "DELETE":        R,
        "MOVE":          C,
        "DOWNLOAD":      G,
        "DOWNLOAD_UPDATE": Y,
        "SPAWN":         G,
        "EXIT":          DIM,
        "TARGET_FOUND":  Y,
        "CONNECT":       C,
        "REG_ADD":       G,
        "REG_ADD_KEY":   G,
        "REG_MODIFY":    Y,
        "REG_DELETE":    R,
        "REG_DEL_KEY":   R,
    }
    TYPE_LABEL = {
        "CREATE":        "FILE+  ",
        "MODIFY":        "FILE~  ",
        "DELETE":        "FILE-  ",
        "MOVE":          "MOVE   ",
        "DOWNLOAD":      "DL+    ",
        "DOWNLOAD_UPDATE": "DL~  ",
        "SPAWN":         "PROC+  ",
        "EXIT":          "PROC-  ",
        "TARGET_FOUND":  "TARGET ",
        "CONNECT":       "NET    ",
        "REG_ADD":       "REG+   ",
        "REG_ADD_KEY":   "REG+K  ",
        "REG_MODIFY":    "REG~   ",
        "REG_DELETE":    "REG-   ",
        "REG_DEL_KEY":   "REG-K  ",
    }

    while True:
        header("Scout Mode")
        if current and current.is_running:
            s = current.get_summary()
            print(f"  {G}[LIVE]{RST} Scouting {B}'{current.app_name}'{RST}")
            print(f"  Files:{G}{s['file_events']}{RST}  "
                  f"Reg:{Y}{s['registry_events']}{RST}  "
                  f"Net:{C}{s['network_events']}{RST}  "
                  f"Procs:{G}{s['process_events']}{RST}  "
                  f"Downloads:{G}{s['download_events']}{RST}")
        sep()
        print(f"  {C}[1]{RST} Start Scout session  (live feed)")
        print(f"  {C}[2]{RST} Stop active session")
        print(f"  {C}[3]{RST} List saved sessions")
        print(f"  {C}[4]{RST} View session report")
        print(f"  {C}[5]{RST} Delete a session")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()

        if c == "0":
            if current and current.is_running:
                current.stop()
            break

        elif c == "1":
            if current and current.is_running:
                warn("Already running a session. Stop it first [2].")
                pause()
                continue

            clr()
            sep()
            print(f"  {C}{B}Scout Mode — setup{RST}")
            sep()
            print(f"  {DIM}Label    — session name (e.g. 'teams', 'installer').{RST}")
            print(f"  {DIM}Watch    — folder to monitor for file changes (recursive).{RST}")
            print(f"  {DIM}Target   — target process exe (e.g. 'Teams.exe') [optional].{RST}")
            print(f"  {DIM}Monitors — files, registry (HKCU Run/Software), network,{RST}")
            print(f"  {DIM}           downloads folder, and spawned processes.{RST}")
            sep()

            app_name = prompt("Session label: ").strip()
            if not app_name:
                continue

            default_path = os.path.expanduser("~")
            watch_path = prompt(f"Watch path [{default_path}]: ").strip() or default_path
            if not os.path.isdir(watch_path):
                err(f"Directory not found: {watch_path}")
                pause()
                continue

            target_proc = prompt("Target process (e.g. Teams.exe) [Enter = skip]: ").strip() or None

            current = ScoutSession(app_name, str(profile_path), logger)
            current.start(watch_path=watch_path, target_process=target_proc)

            clr()
            sep("═")
            print(f"  {G}{B}SCOUT MODE — LIVE{RST}  {B}{app_name}{RST}")
            print(f"  watch : {watch_path}")
            if target_proc:
                print(f"  target: {Y}{target_proc}{RST}")
            sep("═")
            print(f"  {DIM}Legend:{RST}  "
                  f"{G}FILE+{RST}=create  {Y}FILE~{RST}=modify  {R}FILE-{RST}=delete  {C}MOVE{RST}  "
                  f"{G}PROC+{RST}=spawn  {G}DL+{RST}=download  "
                  f"{C}NET{RST}=connect  {G}REG+{RST}=reg add  {Y}REG~{RST}=reg mod  {R}REG-{RST}=reg del")
            sep()
            print(f"  {DIM}Press Enter to stop{RST}\n")

            stop_flag = threading.Event()

            def _wait_enter():
                try:
                    input()
                except Exception:
                    pass
                stop_flag.set()

            threading.Thread(target=_wait_enter, daemon=True).start()

            import queue as _q
            while not stop_flag.is_set():
                try:
                    ev = current.event_queue.get(timeout=0.2)
                    etype = ev.get("type", "")
                    col   = TYPE_COLOR.get(etype, W)
                    label = TYPE_LABEL.get(etype, f"{etype:<7}")
                    path  = ev.get("path", "")
                    dest  = ev.get("dest", "")
                    extra = ""
                    if etype == "DOWNLOAD_UPDATE":
                        size = ev.get("size", 0)
                        extra = f"  ({fmt_bytes(size)})" if size else ""
                    elif etype == "CONNECT":
                        extra = f"  [{ev.get('remote_host','')}]"
                    elif etype == "SPAWN":
                        extra = f"  pid={ev.get('pid','')} parent={ev.get('parent_pid','')}"
                    elif etype in ("REG_ADD", "REG_MODIFY", "REG_DELETE"):
                        extra = f"  val={str(ev.get('new_value', ev.get('value', '')))[:60]}"
                    move_str = f"  →  {dest}" if dest else ""
                    print(f"  {DIM}{ev['time']}{RST}  {col}{label}{RST}  {path}{move_str}{extra}")
                except _q.Empty:
                    pass

            current.stop()
            sep("═")
            s = current.get_summary()
            ok(f"Session saved — "
               f"files:{G}{s['file_events']}{RST}  "
               f"reg:{Y}{s['registry_events']}{RST}  "
               f"net:{C}{s['network_events']}{RST}  "
               f"procs:{G}{s['process_events']}{RST}  "
               f"dl:{G}{s['download_events']}{RST}")
            current = None
            pause()

        elif c == "2":
            if current and current.is_running:
                current.stop()
                ok(f"Session stopped.")
                current = None
            else:
                warn("No active session.")
            pause()

        elif c == "3":
            sessions = ScoutSession.load_sessions(str(profile_path))
            sep()
            if not sessions:
                warn("No Scout sessions found.")
            else:
                print(f"  {'Session ID':<20}  {'Label':<18}  {'Target':<15}  Files  Reg  Net  Procs  DL  Total")
                sep("-")
                for s in sessions:
                    sm = s.get("summary", {})
                    print(f"  {s.get('session_id',''):<20}  "
                          f"{s.get('app_name',''):<18}  "
                          f"{(s.get('target_process') or '-'):<15}  "
                          f"{sm.get('file_events',0):>5}  "
                          f"{sm.get('registry_events',0):>4}  "
                          f"{sm.get('network_events',0):>4}  "
                          f"{sm.get('process_events',0):>5}  "
                          f"{sm.get('download_events',0):>4}  "
                          f"{sm.get('total_events',0):>5}")
            pause()

        elif c == "4":
            sessions = ScoutSession.load_sessions(str(profile_path))
            sid = prompt("Session ID: ")
            session = next((s for s in sessions if s.get("session_id") == sid), None)
            if not session:
                err("Session not found.")
                pause()
                continue

            sep()
            sm = session.get("summary", {})
            ok(f"Scout Report — {session.get('app_name')}  [{sid}]")
            print(f"  Duration : {sm.get('duration_s', 0):.1f} s")
            print(f"  Watch    : {session.get('watch_path','')}")
            print(f"  Target   : {session.get('target_process') or 'all processes'}")
            sep()

            sections = [
                ("NETWORK CONNECTIONS",  "network_events",  C),
                ("REGISTRY CHANGES",     "registry_events", Y),
                ("DOWNLOADS",            "download_events", G),
                ("PROCESSES SPAWNED",    "process_events",  G),
                ("FILES CREATED/MODIFIED/DELETED", "file_events", W),
            ]
            for title, key, col in sections:
                events = session.get(key, [])
                if not events:
                    continue
                print(f"\n  {col}{title} ({len(events)}){RST}")
                for ev in events[:25]:
                    etype = ev.get("type", "")
                    label = TYPE_LABEL.get(etype, f"{etype:<7}")
                    ecol  = TYPE_COLOR.get(etype, W)
                    extra = ""
                    if etype == "CONNECT":
                        host = ev.get("remote_host", ev.get("remote", ""))
                        extra = f"  [{host}]"
                    elif etype == "REG_MODIFY":
                        extra = f"  {ev.get('old_value','')[:40]} => {ev.get('new_value','')[:40]}"
                    elif etype == "SPAWN":
                        extra = f"  pid={ev.get('pid','')} {ev.get('cmdline','')[:50]}"
                    print(f"    {DIM}{ev.get('time','')}{RST}  {ecol}{label}{RST}  {ev.get('path','')[:70]}{extra}")
                if len(events) > 25:
                    print(f"    {DIM}... and {len(events)-25} more{RST}")
            pause()

        elif c == "5":
            sessions = ScoutSession.load_sessions(str(profile_path))
            sid = prompt("Session ID to delete: ")
            f = profile_path / f"scout_{sid}.json"
            if f.exists():
                warn(f"Delete scout session '{sid}'?")
                if prompt("Type YES: ").upper() == "YES":
                    f.unlink()
                    ok("Deleted.")
            else:
                err("Session not found.")
            pause()


# ── 19. SYSTEM HEALTH ───────────────────────────────────────

def menu_health(logger: CleanerLogger):
    """System Health Score — composite system health indicator."""
    header("System Health")
    info("Computing health score, please wait…")
    try:
        from core.health import get_health_score
        result = get_health_score(logger)
    except Exception as e:
        err(f"Health check failed: {e}")
        pause()
        return

    overall = result["overall_score"]
    grade   = result["grade"]

    # Color-code the grade
    grade_color = G if grade in ("A",) else Y if grade in ("B", "C") else R

    sep("═")
    print(f"\n  Overall Health Score:  {grade_color}{B}{overall}/100  (Grade {grade}){RST}\n")
    sep()

    # Bar chart
    bar_len = 40
    filled  = int(overall / 100 * bar_len)
    bar_col = G if overall >= 70 else Y if overall >= 45 else R
    bar     = f"{bar_col}{'█' * filled}{'░' * (bar_len - filled)}{RST}"
    print(f"  [{bar}]  {overall}%\n")
    sep()

    # Indicators table
    print(f"  {'Indicator':<22}  {'Value':<40}  {'Score':>5}  Status")
    sep("-")
    for ind in result["indicators"]:
        sc  = ind["score"]
        sc_col = G if sc >= 70 else Y if sc >= 45 else R
        print(f"  {ind['name']:<22}  {ind['value']:<40}  {sc_col}{sc:>5}{RST}  {ind['status']}")

    sep()
    print(f"  {Y}Recommendations:{RST}")
    for rec in result["recommendations"]:
        print(f"    {C}•{RST} {rec}")

    sep("═")
    pause()


# ── DISK HEALTH ─────────────────────────────────────────────

def menu_disk_health(logger: CleanerLogger):
    header(t("menu.disk_health"))
    info("Querying disk information — please wait…")
    try:
        from core.diskhealth import get_physical_disks, get_smart_counters, get_disk_partitions
        disks   = get_physical_disks(logger)
        smart   = get_smart_counters(logger)
        parts   = get_disk_partitions(logger)
    except Exception as e:
        err(str(e)); pause(); return

    sep("═")

    # Physical disks
    if disks:
        print(f"  {B}Physical Disks{RST}")
        sep("-")
        for d in disks:
            h = d["health"]
            h_col = G if h == "Healthy" else Y if h == "Warning" else R
            bar_total = 20
            if d["size"]:
                size_str = fmt_bytes(d["size"])
            else:
                size_str = "?"
            print(f"  {B}{d['model']}{RST}")
            print(f"    Type   : {d['media_type']}  ({d['bus']})")
            print(f"    Size   : {size_str}")
            print(f"    Health : {h_col}{h}{RST}  [{d['status']}]")
            print()
    else:
        warn("Could not read physical disk info (admin rights may be required).")

    # SMART counters
    if smart:
        print(f"  {B}SMART Reliability Counters{RST}")
        sep("-")
        for s in smart:
            temp = f"{s['temperature']} °C" if s["temperature"] is not None else "N/A"
            wear = f"{s['wear']}%" if s["wear"] is not None else "N/A"
            temp_col = G if s["temperature"] is None or s["temperature"] < 45 else \
                       Y if s["temperature"] < 55 else R
            wear_col = G if s["wear"] is None or s["wear"] < 70 else \
                       Y if s["wear"] < 90 else R
            print(f"  Device {s['device_id'] or 'unknown'}")
            print(f"    Temperature  : {temp_col}{temp}{RST}")
            print(f"    SSD Wear     : {wear_col}{wear}{RST}")
            print(f"    Read errors  : {s['read_errors']}  (corrected: {s['read_corrected']})")
            print(f"    Write errors : {s['write_errors']}")
            print(f"    Power-on hrs : {s['power_hours']}")
            if s["start_stop"]:
                print(f"    Start/Stop   : {s['start_stop']}")
            if s["load_unload"]:
                print(f"    Load/Unload  : {s['load_unload']}")
            print()
    else:
        warn("SMART data unavailable (requires admin + Storage cmdlets).")

    # Partitions
    if parts:
        sep()
        print(f"  {B}Partitions / Drives{RST}")
        sep("-")
        BAR = 30
        for p in parts:
            filled = int(p["pct"] / 100 * BAR)
            bar_col = G if p["pct"] < 75 else Y if p["pct"] < 90 else R
            bar = f"{bar_col}{'█' * filled}{'░' * (BAR - filled)}{RST}"
            print(f"  {C}{p['letter']}:{RST}  [{bar}] {p['pct']}%  "
                  f"free {fmt_bytes(p['free'])} / {fmt_bytes(p['total'])}"
                  + (f"  {DIM}{p['label']}{RST}" if p["label"] else ""))

    sep("═")
    pause()


# ── FILE RECOVERY ────────────────────────────────────────────

def menu_recovery(logger: CleanerLogger):
    while True:
        header(t("menu.recovery"))
        print(f"  {C}[1]{RST} Recycle Bin — browse and restore")
        print(f"  {C}[2]{RST} Shadow Copy (VSS) — restore a file from a snapshot")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break

        elif c == "1":
            _menu_recovery_recycle(logger)

        elif c == "2":
            _menu_recovery_shadow(logger)


def _menu_recovery_recycle(logger: CleanerLogger):
    while True:
        header("Recovery — Recycle Bin")
        info("Loading Recycle Bin contents…")
        try:
            from core.recovery import get_recycle_bin_items, restore_recycle_item, restore_all_recycle, empty_recycle_bin
            items = get_recycle_bin_items(logger)
        except Exception as e:
            err(str(e)); pause(); return

        sep()
        if not items:
            ok("Recycle Bin is empty.")
            pause()
            return

        total_sz = sum(i["size"] for i in items)
        print(f"  {len(items)} item(s)  —  {fmt_bytes(total_sz)} total")
        sep("-")
        print(f"  {'#':>4}  {'Size':>10}  {'Deleted':>20}  {'Type':<15}  Name")
        sep("-")
        for i, item in enumerate(items[:50]):
            print(f"  {i+1:>4}  {fmt_bytes(item['size']):>10}  {item['date']:>20}  "
                  f"{item['type'][:15]:<15}  {item['name'][:40]}")
        if len(items) > 50:
            print(f"  {DIM}… {len(items)-50} more{RST}")
        sep()
        print(f"  {C}[r 1,3]{RST} Restore   {C}[ra]{RST} Restore all   "
              f"{C}[empty]{RST} Empty bin   {C}[0]{RST} Back")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.lower() == "ra":
            warn(f"Restore ALL {len(items)} item(s) to their original locations?")
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                restore_all_recycle(logger)
                ok("All items restored.")
            pause()
            continue
        if cmd.lower() == "empty":
            warn(f"Permanently delete ALL {len(items)} item(s) from the Recycle Bin?")
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                empty_recycle_bin(logger)
                ok("Recycle Bin emptied.")
            pause()
            break
        parts = cmd.split(None, 1)
        if parts and parts[0] == "r" and len(parts) > 1:
            idxs = _parse_nums(parts[1], len(items))
            if not idxs:
                err("Invalid number.")
            else:
                for i in idxs:
                    restore_recycle_item(items[i], logger)
                ok(f"Restore command sent for {len(idxs)} item(s).")
            pause()


def _menu_recovery_shadow(logger: CleanerLogger):
    header("Recovery — Shadow Copies (VSS)")
    info("Loading available shadow copies…")
    try:
        from core.recovery import get_shadow_copies, restore_from_shadow
        shadows = get_shadow_copies(logger)
    except Exception as e:
        err(str(e)); pause(); return

    if not shadows:
        warn("No shadow copies found. Enable System Restore or Windows Backup to create snapshots.")
        pause()
        return

    sep()
    for i, s in enumerate(shadows):
        print(f"  {C}[{i+1}]{RST}  {s['date']}  {s['volume']}")
    sep()
    choice = prompt("Select shadow copy number: ").strip()
    try:
        idx = int(choice) - 1
        shadow = shadows[idx]
    except (ValueError, IndexError):
        err("Invalid number.")
        pause()
        return

    sep()
    info(f"Selected: {shadow['date']}  {shadow['volume']}")
    file_path = prompt("File path relative to volume root (e.g. Users\\alice\\doc.txt): ").strip()
    if not file_path:
        return

    dest = prompt("Destination folder for recovered file [Desktop]: ").strip()
    if not dest:
        dest = os.path.join(os.path.expanduser("~"), "Desktop")

    info(f"Recovering '{file_path}' from shadow {shadow['date']}…")
    try:
        if restore_from_shadow(shadow, file_path, dest, logger):
            ok(f"File recovered to: {dest}")
        else:
            err(f"File not found in this shadow copy: {file_path}")
    except Exception as e:
        err(str(e))
    pause()


# ── FILE TOOLS ──────────────────────────────────────────────

def menu_duplicates(logger: CleanerLogger):
    while True:
        header(t("menu.duplicates"))
        print(f"  {C}[1]{RST} Scan a folder for duplicate files")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break
        elif c == "1":
            default = os.path.expanduser("~")
            root = prompt(f"Folder to scan [{default}]: ").strip() or default
            if not os.path.isdir(root):
                err(f"Not a directory: {root}")
                pause()
                continue
            threshold_raw = prompt("Min file size to consider in KB [4]: ").strip()
            try:
                min_kb = int(threshold_raw) if threshold_raw else 4
            except ValueError:
                min_kb = 4
            info(f"Scanning '{root}' for duplicates (min {min_kb} KB)…")
            try:
                from core.duplicates import find_duplicates, delete_files
                groups = find_duplicates(root, min_size=min_kb * 1024, logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue

            if not groups:
                ok("No duplicates found.")
                pause()
                continue

            total_wasted = sum(g[0]["size"] * (len(g) - 1) for g in groups)
            sep()
            ok(f"Found {len(groups)} duplicate groups — {fmt_bytes(total_wasted)} wasted")
            sep("-")

            # Build a flat numbered list of deletable copies (keep first = newest)
            deletable: list[dict] = []
            for g in groups[:30]:
                g_sorted = sorted(g, key=lambda x: x["modified"], reverse=True)
                keeper = g_sorted[0]
                print(f"\n  {G}KEEP{RST}  {keeper['path'][:70]}  ({fmt_bytes(keeper['size'])})")
                for dup in g_sorted[1:]:
                    idx = len(deletable) + 1
                    print(f"  {R}[{idx:>3}]{RST}  {dup['path'][:70]}")
                    deletable.append(dup)
            if len(groups) > 30:
                print(f"  {DIM}… {len(groups)-30} more groups not shown{RST}")

            sep()
            print(f"  {C}[d 1,3]{RST} Delete selected   {C}[all]{RST} Delete ALL copies   {C}[0]{RST} Back")
            sep()
            cmd = prompt()
            if cmd == "0":
                continue
            if cmd.lower() == "all":
                warn(f"Delete ALL {len(deletable)} duplicate copies?")
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    freed = delete_files([d["path"] for d in deletable], logger)
                    ok(f"Freed {fmt_bytes(freed)}")
            else:
                parts = cmd.split(None, 1)
                if parts and parts[0] == "d" and len(parts) > 1:
                    try:
                        nums = [int(x) - 1 for x in parts[1].split()]
                        to_del = [deletable[n]["path"] for n in nums if 0 <= n < len(deletable)]
                        freed = delete_files(to_del, logger)
                        ok(f"Deleted {len(to_del)} file(s) — freed {fmt_bytes(freed)}")
                    except (ValueError, IndexError):
                        err("Invalid number.")
            pause()


def menu_large_files(logger: CleanerLogger):
    PAGE = 20
    while True:
        header(t("menu.large_files"))
        print(f"  {C}[1]{RST} Scan a folder for large files")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break
        elif c != "1":
            continue

        default = "C:\\" if os.name == "nt" else os.path.expanduser("~")
        root = prompt(f"Folder to scan [{default}]: ").strip() or default
        if not os.path.isdir(root):
            err(f"Not a directory: {root}")
            pause()
            continue
        threshold_raw = prompt("Minimum size in MB [100]: ").strip()
        try:
            min_mb = int(threshold_raw) if threshold_raw else 100
        except ValueError:
            min_mb = 100

        info(f"Scanning '{root}' for files ≥ {min_mb} MB…")
        try:
            from core.largefile import find_large_files, delete_file as lf_delete
            files = find_large_files(root, min_bytes=min_mb * 1024 * 1024, logger=logger)
        except Exception as e:
            err(str(e)); pause(); continue

        if not files:
            ok(f"No files ≥ {min_mb} MB found.")
            pause()
            continue

        page = 0
        deleted_paths: set[str] = set()

        while True:
            # Filter out already-deleted entries
            visible = [f for f in files if f["path"] not in deleted_paths]
            if not visible:
                ok("All files on the list have been deleted.")
                pause()
                break

            total_pages = max(1, (len(visible) + PAGE - 1) // PAGE)
            page = max(0, min(page, total_pages - 1))
            start = page * PAGE
            page_files = visible[start: start + PAGE]

            clr()
            sep()
            total_wasted = sum(f["size"] for f in visible)
            print(f"  {C}{B}Large Files{RST}  —  "
                  f"{len(visible)} file(s)  {fmt_bytes(total_wasted)} total  "
                  f"  {DIM}page {page+1}/{total_pages}{RST}")
            sep()
            print(f"  {'#':>4}  {'Size':>10}  Path")
            sep("-")
            for i, f in enumerate(page_files):
                global_num = start + i + 1
                print(f"  {global_num:>4}  {fmt_bytes(f['size']):>10}  {f['path'][:72]}")
            sep()
            print(f"  {C}[← →]{RST} / {C}[n p]{RST} page   "
                  f"{C}[d 1,3,5]{RST} delete   "
                  f"{C}[d all]{RST} delete page   "
                  f"{C}[0]{RST} back")
            sep()

            cmd = nav_prompt()

            if cmd in ("0", "q"):
                break
            if cmd in ("__next__", "n"):
                page = min(page + 1, total_pages - 1)
                continue
            if cmd in ("__prev__", "p"):
                page = max(page - 1, 0)
                continue

            parts = cmd.split(None, 1)
            if not parts or parts[0] != "d":
                continue
            arg = parts[1].strip() if len(parts) > 1 else ""

            # Resolve which files to delete
            if arg.lower() == "all":
                targets = list(page_files)
            else:
                try:
                    nums = [int(x) for x in arg.split()]
                    targets = []
                    for n in nums:
                        idx = n - 1  # global 1-based → 0-based into visible
                        if 0 <= idx < len(visible):
                            targets.append(visible[idx])
                        else:
                            err(f"No file #{n}.")
                except ValueError:
                    err("Invalid number.")
                    continue

            if not targets:
                continue

            total_sz = sum(f["size"] for f in targets)
            warn(f"Delete {len(targets)} file(s)  ({fmt_bytes(total_sz)})? This cannot be undone.")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue

            freed = 0
            ok_count = 0
            for f in targets:
                sz = f["size"]
                if lf_delete(f["path"], logger):
                    freed += sz
                    ok_count += 1
                    deleted_paths.add(f["path"])
                else:
                    err(f"Could not delete: {f['path']}")
            ok(f"Deleted {ok_count}/{len(targets)} file(s) — freed {fmt_bytes(freed)}")


def menu_empty_folders(logger: CleanerLogger):
    while True:
        header(t("menu.empty_folders"))
        print(f"  {C}[1]{RST} Scan a folder for empty subdirectories")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break
        elif c == "1":
            default = os.path.expanduser("~")
            root = prompt(f"Folder to scan [{default}]: ").strip() or default
            if not os.path.isdir(root):
                err(f"Not a directory: {root}")
                pause()
                continue
            info(f"Scanning '{root}' for empty folders…")
            try:
                from core.emptyfolders import find_empty_folders, delete_folders
                empties = find_empty_folders(root, logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue

            if not empties:
                ok("No empty folders found.")
                pause()
                continue

            sep()
            ok(f"Found {len(empties)} empty folder(s)")
            sep("-")
            for i, p in enumerate(empties[:50]):
                print(f"  {i+1:>4}  {p}")
            if len(empties) > 50:
                print(f"  {DIM}… {len(empties)-50} more{RST}")
            sep()
            print(f"  {C}[d 1,3]{RST} Delete selected   {C}[all]{RST} Delete ALL   {C}[0]{RST} Back")
            sep()
            cmd = prompt()
            if cmd == "0":
                continue
            if cmd.lower() == "all":
                warn(f"Delete all {len(empties)} empty folder(s)?")
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    n = delete_folders(empties, logger)
                    ok(f"Deleted {n} folder(s).")
            else:
                parts = cmd.split(None, 1)
                if parts and parts[0] == "d" and len(parts) > 1:
                    try:
                        nums = [int(x) - 1 for x in parts[1].split()]
                        sel = [empties[n] for n in nums if 0 <= n < len(empties)]
                        count = delete_folders(sel, logger)
                        ok(f"Deleted {count} folder(s).")
                    except (ValueError, IndexError):
                        err("Invalid number.")
            pause()


def menu_secure_wipe(logger: CleanerLogger):
    header(t("menu.secure_wipe"))
    print(f"  Overwrite file content before deletion so it cannot be recovered.")
    print(f"  {Y}Passes:{RST}  1 = zeros only   3 = DoD (zeros/ones/random)   7 = extra thorough")
    sep()
    target = prompt("File or folder to wipe: ").strip()
    if not target:
        return
    if not os.path.exists(target):
        err(f"Not found: {target}")
        pause()
        return
    passes_raw = prompt("Overwrite passes [3]: ").strip()
    try:
        passes = int(passes_raw) if passes_raw else 3
        passes = max(1, min(passes, 35))
    except ValueError:
        passes = 3
    scope = "folder" if os.path.isdir(target) else "file"
    warn(f"Securely wipe {scope} '{target}' with {passes} pass(es)? This CANNOT be undone.")
    if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
        info("Cancelled.")
        pause()
        return
    info(f"Wiping… ({passes} pass{'es' if passes > 1 else ''})")
    try:
        from core.securewipe import secure_wipe, secure_wipe_dir
        if os.path.isdir(target):
            wiped, freed = secure_wipe_dir(target, passes=passes, logger=logger)
            ok(f"Wiped {wiped} file(s) — {fmt_bytes(freed)} overwritten and deleted.")
        else:
            if secure_wipe(target, passes=passes, logger=logger):
                ok("File securely wiped.")
            else:
                err("Wipe failed — check permissions.")
    except Exception as e:
        err(str(e))
    pause()


# ── MONITORING ADDITIONS ─────────────────────────────────────

def menu_crash_logs(logger: CleanerLogger):
    while True:
        header(t("menu.crash_logs"))
        print(f"  {C}[1]{RST} Recent critical/error events  (Event Log)")
        print(f"  {C}[2]{RST} BSOD history")
        print(f"  {C}[3]{RST} Minidump files")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break

        elif c == "1":
            hours_raw = prompt("Look back how many hours? [72]: ").strip()
            try:
                hours = int(hours_raw) if hours_raw else 72
            except ValueError:
                hours = 72
            info(f"Reading Event Log (last {hours} h)…")
            try:
                from core.crashlog import get_crash_events
                events = get_crash_events(hours=hours, logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue

            sep()
            if not events:
                ok("No critical/error events found in this window.")
            else:
                print(f"  {'Time':<20}  {'Lvl':<8}  {'Source':<30}  {'ID':>5}  Message")
                sep("-")
                for ev in events:
                    lv_col = R if ev["level"] in ("Critical", "Error") else Y
                    print(f"  {ev['time']:<20}  {lv_col}{ev['level'][:8]:<8}{RST}  "
                          f"{ev['source'][:30]:<30}  {ev['id']:>5}  {ev['message'][:60]}")
                ok(f"{len(events)} event(s) found.")
            pause()

        elif c == "2":
            info("Reading BSOD (BugCheck) history…")
            try:
                from core.crashlog import get_bsod_summary
                bsods = get_bsod_summary(logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue

            sep()
            if not bsods:
                ok("No BSOD events found.")
            else:
                for b in bsods:
                    print(f"  {R}{b['time']}{RST}  {b['message'][:100]}")
            pause()

        elif c == "3":
            try:
                from core.crashlog import get_minidumps
                dumps = get_minidumps(logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue

            sep()
            if not dumps:
                ok("No minidump files found (C:\\Windows\\Minidump).")
            else:
                print(f"  {'Name':<30}  {'Size':>10}  Modified")
                sep("-")
                for d in dumps:
                    print(f"  {d['name']:<30}  {fmt_bytes(d['size']):>10}  {d['modified']}")
                ok(f"{len(dumps)} minidump(s)")
            pause()


# ── TOOLS ADDITIONS ──────────────────────────────────────────

def menu_autoruns(logger: CleanerLogger):
    while True:
        header(t("menu.autoruns"))
        print(f"  {C}[1]{RST} View all autorun entries")
        print(f"  {C}[2]{RST} View scheduled tasks")
        print(f"  {C}[3]{RST} View shell extensions")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break

        elif c == "1":
            info("Loading autorun entries…")
            try:
                from core.autoruns import get_autoruns, disable_run_entry
                data = get_autoruns(logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue

            run_entries: list[dict] = data.get("Run Keys", []) + data.get("Winlogon", [])
            sep()
            if not run_entries:
                warn("No Run key / Winlogon entries found.")
            else:
                print(f"  {'#':>4}  {'Source':<18}  {'Name':<30}  Command")
                sep("-")
                for i, e in enumerate(run_entries):
                    print(f"  {i+1:>4}  {e.get('source','')[:18]:<18}  "
                          f"{e.get('name','')[:30]:<30}  {e.get('command','')[:50]}")
                sep()
                print(f"  {C}[d 1,3]{RST} Delete from startup   {C}[Enter]{RST} Back")
                sep()
                cmd = prompt()
                parts = cmd.split(None, 1)
                if parts and parts[0] == "d" and len(parts) > 1:
                    idxs = _parse_nums(parts[1], len(run_entries))
                    sel = [run_entries[i] for i in idxs]
                    if not sel:
                        err("Invalid number.")
                    else:
                        names = ", ".join(e["name"] for e in sel)
                        warn(f"Remove {len(sel)} startup entry/entries: {names[:80]}?")
                        if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                            done = sum(1 for e in sel if disable_run_entry(e, logger))
                            ok(f"Removed {done}/{len(sel)}.")
                            if done < len(sel):
                                err("Some failed — admin rights may be required.")
            pause()

        elif c == "2":
            info("Loading scheduled tasks…")
            try:
                from core.autoruns import get_autoruns, disable_scheduled_task, enable_scheduled_task
                data = get_autoruns(logger=logger)
                tasks = data.get("Scheduled Tasks", [])
            except Exception as e:
                err(str(e)); pause(); continue

            sep()
            if not tasks:
                warn("No scheduled tasks found.")
                pause()
                continue

            while True:
                enabled_t  = [t2 for t2 in tasks if t2.get("enabled")]
                disabled_t = [t2 for t2 in tasks if not t2.get("enabled")]
                print(f"  {'#':>4}  {'Status':<10}  {'Name':<40}  Command")
                sep("-")
                for i, t2 in enumerate(tasks[:50]):
                    st_col = G if t2.get("enabled") else DIM
                    st_lbl = "Active" if t2.get("enabled") else "Disabled"
                    print(f"  {i+1:>4}  {st_col}{st_lbl:<10}{RST}  "
                          f"{t2.get('name','')[:40]:<40}  {t2.get('command','')[:40]}")
                sep()
                print(f"  {C}[tog 1,3]{RST} Toggle enable/disable   {C}[0]{RST} Back")
                sep()
                cmd = prompt()
                if cmd == "0":
                    break
                parts = cmd.split(None, 1)
                if parts and parts[0] == "tog" and len(parts) > 1:
                    idxs = _parse_nums(parts[1], len(tasks[:50]))
                    if not idxs:
                        err("Invalid number.")
                        continue
                    for idx in idxs:
                        task = tasks[:50][idx]
                        if task.get("enabled"):
                            disable_scheduled_task(task, logger)
                            task["enabled"] = False
                            ok(f"Disabled '{task['name']}'.")
                        else:
                            enable_scheduled_task(task, logger)
                            task["enabled"] = True
                            ok(f"Enabled '{task['name']}'.")

        elif c == "3":
            info("Loading shell extensions…")
            try:
                from core.autoruns import get_autoruns
                data = get_autoruns(logger=logger)
                exts = data.get("Shell Extensions", [])
            except Exception as e:
                err(str(e)); pause(); continue

            sep()
            if not exts:
                warn("No approved shell extensions found.")
            else:
                print(f"  {'Name':<50}  CLSID")
                sep("-")
                for e in exts[:50]:
                    print(f"  {e.get('name','')[:50]:<50}  {e.get('command','')}")
                if len(exts) > 50:
                    print(f"  {DIM}… {len(exts)-50} more{RST}")
            pause()


def menu_context_menu(logger: CleanerLogger):
    while True:
        header(t("menu.context_menu"))
        info("Loading context menu entries…")
        try:
            from core.contextmenu import get_context_menu_entries, disable_entry, enable_entry, delete_entry
            entries = get_context_menu_entries(logger=logger)
        except Exception as e:
            err(str(e)); pause(); return

        if not entries:
            warn("No context menu entries found.")
            pause()
            return

        sep()
        print(f"  {'#':>4}  {'Status':<9}  {'Location':<22}  {'Name':<28}  Command")
        sep("-")
        for i, e in enumerate(entries[:60]):
            st_col = G if e.get("enabled") else DIM
            st_lbl = "Enabled" if e.get("enabled") else "Disabled"
            print(f"  {i+1:>4}  {st_col}{st_lbl:<9}{RST}  "
                  f"{e.get('location','')[:22]:<22}  "
                  f"{e.get('name','')[:28]:<28}  "
                  f"{e.get('command','')[:40]}")
        if len(entries) > 60:
            print(f"  {DIM}… {len(entries)-60} more entries{RST}")
        sep()
        print(f"  {C}[tog 1,3]{RST} Toggle   {C}[del 1,3]{RST} Delete permanently   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        parts = cmd.split(None, 1)
        if not parts or len(parts) < 2:
            continue
        action, rest = parts[0], parts[1]
        idxs = _parse_nums(rest, len(entries[:60]))
        if not idxs:
            err("Invalid number."); continue
        sel = [entries[:60][i] for i in idxs]
        if action == "tog":
            for entry in sel:
                if entry.get("enabled"):
                    ok(f"Disabled '{entry['name']}'.") if disable_entry(entry, logger) else err(f"Failed: '{entry['name']}' — try admin.")
                else:
                    ok(f"Enabled '{entry['name']}'.") if enable_entry(entry, logger) else err(f"Failed: '{entry['name']}' — try admin.")
        elif action == "del":
            names = ", ".join(e["name"] for e in sel)
            warn(f"Permanently delete {len(sel)} entry/entries: {names[:80]}?")
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                done = sum(1 for e in sel if delete_entry(e, logger))
                ok(f"Deleted {done}/{len(sel)}.")


# ── SYSTEM ADDITIONS ─────────────────────────────────────────

def menu_restore_points(logger: CleanerLogger):
    while True:
        header(t("menu.restore_points"))
        print(f"  {C}[1]{RST} List restore points")
        print(f"  {C}[2]{RST} Create a restore point")
        print(f"  {C}[3]{RST} Delete a restore point")
        print(f"  {C}[4]{RST} Delete ALL restore points  {R}(frees disk space){RST}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break

        elif c == "1":
            info("Loading restore points…")
            try:
                from core.restore import list_restore_points
                points = list_restore_points(logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue
            sep()
            if not points:
                warn("No restore points found (or System Restore is disabled).")
            else:
                print(f"  {'Seq':>5}  {'Created':<18}  {'Type':<6}  Description")
                sep("-")
                for p in points:
                    print(f"  {p['seq']:>5}  {p['created']:<18}  {p['type'][:6]:<6}  {p['description']}")
            pause()

        elif c == "2":
            desc = prompt("Description [System Cleaner checkpoint]: ").strip() or "System Cleaner checkpoint"
            info("Creating restore point — this may take a moment…")
            try:
                from core.restore import create_restore_point
                if create_restore_point(desc, logger):
                    ok("Restore point created.")
                else:
                    err("Failed — ensure System Restore is enabled and run as admin.")
            except Exception as e:
                err(str(e))
            pause()

        elif c == "3":
            info("Loading restore points…")
            try:
                from core.restore import list_restore_points, delete_restore_point
                points = list_restore_points(logger=logger)
            except Exception as e:
                err(str(e)); pause(); continue
            sep()
            if not points:
                warn("No restore points found.")
                pause()
                continue
            for p in points:
                print(f"  {C}[{p['seq']}]{RST}  {p['created']}  {p['description']}")
            sep()
            seq_raw = prompt("Sequence number to delete: ").strip()
            try:
                seq = int(seq_raw)
                pt = next((p for p in points if p["seq"] == seq), None)
                if not pt:
                    err("Sequence number not found.")
                else:
                    warn(f"Delete restore point {seq} '{pt['description']}'?")
                    if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                        from core.restore import delete_restore_point
                        ok("Deleted.") if delete_restore_point(seq, logger) else err("Failed.")
            except ValueError:
                err("Invalid number.")
            pause()

        elif c == "4":
            warn("Delete ALL restore points for C:\\ — this CANNOT be undone.")
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    from core.restore import delete_all_restore_points
                    ok("All restore points cleared.") if delete_all_restore_points(logger) else err("Failed.")
                except Exception as e:
                    err(str(e))
            pause()


# ── 20. HISTORY MANAGER ─────────────────────────────────────

def _menu_history_network(logger: CleanerLogger):
    while True:
        header(t("hist.net_lbl"))
        info(t("hist.loading"))
        try:
            from core.history import get_network_history, delete_network_profile, clear_all_network_history
            profiles = get_network_history(logger)
        except Exception as e:
            err(str(e)); pause(); return

        sep()
        info(t("hist.net_note"))
        sep()
        if not profiles:
            warn(t("hist.no_entries"))
        else:
            print(f"  {'#':>4}  {'Name':<30}  {'Type':<8}  {t('hist.created'):<20}  {t('hist.last_conn')}")
            sep("-")
            for i, p in enumerate(profiles):
                ctype = p.get("conn_type", "")
                print(f"  {i+1:>4}  {p.get('name','')[:30]:<30}  {ctype:<8}  {p.get('date_created','')[:20]:<20}  {p.get('date_last_conn','')}")
        sep()
        print(f"  {C}[d 1,3]{RST} Delete entries   {C}[all]{RST} Clear all   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.lower() == "all":
            warn(t("hist.del_all"))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    count = clear_all_network_history(logger)
                    ok(t("hist.all_del", count=count))
                except Exception as e:
                    err(str(e))
            pause()
            continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "d" and len(parts) > 1:
            try:
                nums = [int(x) - 1 for x in parts[1].split()]
                deleted = 0
                for idx in nums:
                    try:
                        if delete_network_profile(profiles[idx].get("guid", ""), logger):
                            deleted += 1
                    except (IndexError, Exception) as e:
                        err(t("hist.del_fail", err=str(e)))
                ok(t("hist.entry_del", count=deleted))
            except ValueError:
                err(t("hist.bad_num"))
            pause()


def _menu_history_usb(logger: CleanerLogger):
    while True:
        header(t("hist.usb_lbl"))
        info(t("hist.loading"))
        try:
            from core.history import get_usb_history, delete_usb_entry, clear_all_usb_history
            devices = get_usb_history(logger)
        except Exception as e:
            err(str(e)); pause(); return

        sep()
        info(t("hist.usb_note"))
        sep()
        if not devices:
            warn(t("hist.no_entries"))
        else:
            print(f"  {'#':>4}  {'Friendly Name':<35}  {t('hist.vendor'):<20}  {t('hist.model'):<20}  {t('hist.serial')}")
            sep("-")
            for i, d in enumerate(devices):
                print(f"  {i+1:>4}  {d.get('friendly','')[:35]:<35}  {d.get('vendor','')[:20]:<20}  {d.get('model','')[:20]:<20}  {d.get('serial','')[:20]}")
        sep()
        print(f"  {C}[d 1,3]{RST} Delete entries   {C}[all]{RST} Clear all   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.lower() == "all":
            warn(t("hist.del_all"))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    count = clear_all_usb_history(logger)
                    ok(t("hist.all_del", count=count))
                except Exception as e:
                    err(str(e))
            pause()
            continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "d" and len(parts) > 1:
            try:
                nums = [int(x) - 1 for x in parts[1].split()]
                deleted = 0
                for idx in nums:
                    try:
                        if delete_usb_entry(devices[idx], logger):
                            deleted += 1
                    except (IndexError, Exception) as e:
                        err(t("hist.del_fail", err=str(e)))
                ok(t("hist.entry_del", count=deleted))
            except ValueError:
                err(t("hist.bad_num"))
            pause()


def _menu_history_apps(logger: CleanerLogger):
    while True:
        header(t("hist.app_lbl"))
        info(t("hist.loading"))
        try:
            from core.history import get_app_launch_history, delete_app_launch_entry, clear_app_launch_history
            data = get_app_launch_history(logger)
        except Exception as e:
            err(str(e)); pause(); return

        userassist = data.get("userassist", [])
        recent_docs = data.get("recent_docs", [])
        run_mru    = data.get("run_mru", [])
        all_entries = userassist + recent_docs + run_mru

        sep()
        info(t("hist.app_note"))
        print(f"  {DIM}{t('hist.app_doc')}: {len(recent_docs)}   {t('hist.app_run')}: {len(run_mru)}{RST}")
        sep()

        if not all_entries:
            warn(t("hist.no_entries"))
        else:
            print(f"  {'#':>4}  {'Name / Command':<45}  {t('hist.run_count'):>5}  {t('hist.last_run')}")
            sep("-")
            for i, e in enumerate(userassist[:50]):
                runs = e.get("run_count", 0)
                last = e.get("last_run", t("hist.never"))
                print(f"  {i+1:>4}  {e.get('name','')[:45]:<45}  {runs:>5}  {last}")
            base = len(userassist[:50])
            for i, e in enumerate(recent_docs[:20]):
                print(f"  {base+i+1:>4}  [doc] {e.get('name','')[:40]:<40}")
            base += len(recent_docs[:20])
            for i, e in enumerate(run_mru[:20]):
                print(f"  {base+i+1:>4}  [run] {e.get('command','')[:40]:<40}")

        sep()
        print(f"  {C}[d 1,3]{RST} Delete entries   {C}[all]{RST} Clear all   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.lower() == "all":
            warn(t("hist.del_all"))
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                try:
                    counts = clear_app_launch_history(logger)
                    total = sum(counts.values())
                    ok(t("hist.all_del", count=total))
                except Exception as e:
                    err(str(e))
            pause()
            continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "d" and len(parts) > 1:
            display_list = userassist[:50] + recent_docs[:20] + run_mru[:20]
            try:
                nums = [int(x) - 1 for x in parts[1].split()]
                deleted = 0
                for idx in nums:
                    try:
                        if delete_app_launch_entry(display_list[idx], logger):
                            deleted += 1
                    except (IndexError, Exception) as e:
                        err(t("hist.del_fail", err=str(e)))
                ok(t("hist.entry_del", count=deleted))
            except ValueError:
                err(t("hist.bad_num"))
            pause()


def menu_history(logger: CleanerLogger):
    while True:
        header(t("menu.history_mgr"))
        print(f"  {C}[1]{RST} {t('hist.net_lbl')}")
        print(f"  {C}[2]{RST} {t('hist.usb_lbl')}")
        print(f"  {C}[3]{RST} {t('hist.app_lbl')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()
        if c == "0":
            break
        elif c == "1":
            _menu_history_network(logger)
        elif c == "2":
            _menu_history_usb(logger)
        elif c == "3":
            _menu_history_apps(logger)


# ── 21. LANGUAGE ─────────────────────────────────────────────

def menu_language(logger: CleanerLogger):
    header(t("menu.language"))
    langs = available_languages()
    current_code = get_language()

    for i, lang in enumerate(langs):
        marker = f"{G}*{RST}" if lang["code"] == current_code else " "
        print(f"  {marker} {C}[{i+1}]{RST} {lang['name']} — {lang['native_name']}")

    sep()
    current_lang = next((l for l in langs if l["code"] == current_code), {})
    info(t("lang.current", lang=current_lang.get("name", current_code), native=current_lang.get("native_name", current_code)))
    sep()
    choice = prompt(t("lang.select"))

    try:
        idx = int(choice) - 1
        selected = langs[idx]
    except (ValueError, IndexError):
        err(t("lang.invalid"))
        pause()
        return

    set_language(selected["code"])

    # Persist to config.json
    cfg_path = Path(__file__).parent / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        cfg["language"] = selected["code"]
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        ok(t("lang.saved"))
    except Exception as e:
        err(str(e))

    ok(t("lang.changed", lang=selected["native_name"]))
    pause()


# ── ENTRY POINT ─────────────────────────────────────────────

class SystemCleanerApp:
    """Thin wrapper so main.py can still do: app = SystemCleanerApp(); app.run()"""
    def run(self):
        logger = CleanerLogger()
        try:
            main_menu(logger)
        except KeyboardInterrupt:
            clr()
            print(f"\n  {G}Bye.{RST}\n")
            logger.export_json()
            sys.exit(0)
