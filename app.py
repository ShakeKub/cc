"""System Cleaner - pure terminal interface."""

import json
import os
import queue as _queue
import sys
import threading
from pathlib import Path

# Ensure local cc/ is first so "core.*" imports do not get shadowed.
_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

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
_MENU_WATERMARK = " ShakeKub"


def clr():
    os.system("cls" if os.name == "nt" else "clear")


def sep(char="─", n=60):
    print(DIM + char * n + RST)


def _print_brand():
    print(f"{G}{B}")
    print("  ███████╗██╗   ██╗███████╗     ██████╗██╗     ███████╗ █████╗ ███╗   ██╗")
    print("  ██╔════╝╚██╗ ██╔╝██╔════╝    ██╔════╝██║     ██╔════╝██╔══██╗████╗  ██║")
    print("  ███████╗ ╚████╔╝ ███████╗    ██║     ██║     █████╗  ███████║██╔██╗ ██║")
    print("  ╚════██║  ╚██╔╝  ╚════██║    ██║     ██║     ██╔══╝  ██╔══██║██║╚██╗██║")
    print("  ███████║   ██║   ███████║    ╚██████╗███████╗███████╗██║  ██║██║ ╚████║")
    print("  ╚══════╝   ╚═╝   ╚══════╝     ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝")
    print(f"{RST}")
    print(f"  {DIM}{_MENU_WATERMARK}{RST}")


def header(title=""):
    clr()
    _print_brand()
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
            ("36", t("menu.shortcut_fixer")),
            ("37", t("menu.msi_cache")),
            ("35", t("menu.font_mgr")),
        ]),
        (t("cat.security"), [
            ("47", t("menu.file_encrypt")),
            ("50", t("menu.hash_crack")),
            ("51", t("menu.pass_gen")),
            ("52", t("menu.integrity")),
            ("53", t("menu.net_scan")),
            ("54", t("menu.mem_scan")),
            ("55", t("menu.stego")),
            ("56", t("menu.metastrip")),
            ("57", t("menu.hibp")),
            ("58", t("menu.sslcheck")),
            ("59", t("menu.totp")),
            ("60", t("menu.fileanalyze")),
            ("61", t("menu.loganalyze")),
            ("62", t("menu.pwdmgr")),
            ("63", t("menu.backup")),
            ("64", t("menu.startupaudit")),
            ("69", t("menu.cam_audit")),
        ]),
        (t("cat.tools"), [
            ("11", t("menu.browser_tools")),
            ("12", t("menu.process_mgr")),
            ("13", t("menu.network_tools")),
            ("14", t("menu.startup_mgr")),
            ("15", t("menu.disk_tools")),
            ("16", t("menu.registry")),
            ("rE", t("menu.regedit")),
            ("17", t("menu.optimizer")),
            ("18", t("menu.privacy")),
            ("19", t("menu.uninstaller")),
            ("20", t("menu.autoruns")),
            ("21", t("menu.context_menu")),
            ("32", t("menu.perf_boost")),
            ("33", t("menu.env_vars")),
            ("34", t("menu.firewall")),
            ("44", t("menu.factory_wizard")),
            ("45", t("menu.tweaks")),
            ("46", t("menu.pkg_mgr")),
            ("49", t("menu.app_mgr")),
            ("71", t("menu.code_fmt")),
        ]),
        (t("cat.monitoring"), [
            ("22", t("menu.app_tracer")),
            ("23", t("menu.scout_mode")),
            ("24", t("menu.health")),
            ("25", t("menu.crash_logs")),
            ("26", t("menu.disk_health")),
            ("38", t("menu.sys_info")),
            ("39", t("menu.net_speed")),
            ("48", t("menu.driver_mgr")),
            ("65", t("menu.sys_dashboard")),
            ("66", t("menu.port_monitor")),
            ("67", t("menu.temp_monitor")),
            ("68", t("menu.battery_info")),
            ("70", t("menu.disk_analyzer")),
        ]),
        (t("cat.system"), [
            ("27", t("menu.history_mgr")),
            ("28", t("menu.restore_points")),
            ("29", t("menu.scheduler")),
            ("30", t("menu.logs")),
            ("31", t("menu.language")),
            ("40", t("menu.win_update")),
            ("41", t("menu.dns_hosts")),
            ("42", t("menu.ad_blocker")),
            ("43", t("menu.wol")),
        ]),
    ]


# Category icons for the home screen
_CAT_ICONS = ["⚙", "📁", "🔧", "📊", "🖥", "🔒"]


def _print_home_categories(categories):
    """Print only category names on the home screen in a 2-column grid."""
    print()
    for i, (cat_label, _) in enumerate(categories, 1):
        icon = _CAT_ICONS[i - 1] if i - 1 < len(_CAT_ICONS) else " "
        entry = f"  {C}[{i}]{RST} {icon}  {B}{cat_label}{RST}"
        print(entry)
    print()


def _menu_category_view(cat_label: str, items: list, logger: CleanerLogger):
    """Show all items inside a category and dispatch the user's choice."""
    while True:
        clr()
        _print_brand()
        sep()
        print(f"  {C}{B}{cat_label}{RST}")
        sep()

        COL_W = 32
        display_items = [(str(i + 1), label) for i, (_, label) in enumerate(items)]

        for i in range(0, len(display_items), 2):
            num_l, lbl_l = display_items[i]
            left = f"  {C}[{num_l:>2}]{RST} {lbl_l}"
            if i + 1 < len(display_items):
                num_r, lbl_r = display_items[i + 1]
                right = f"  {C}[{num_r:>2}]{RST} {lbl_r}"
            else:
                right = ""
            print(f"{left:<{COL_W + 12}}{right}")

        print()
        print(f"  {C}[ 0]{RST} {t('menu.back')}")
        sep()
        choice = prompt()

        if choice in ("0", "b", "back"):
            return

        action = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                action_key = items[idx][0]
                action = _DISPATCH.get(action_key)

        # Backward-compatible fallback for legacy IDs/aliases within this category.
        if action is None:
            normalized = choice.strip().lower()
            allowed = {key.lower() for key, _ in items}
            if normalized in allowed:
                action = _DISPATCH.get(choice) or _DISPATCH.get(choice.lower()) or _DISPATCH.get(choice.upper())

        if action:
            action(logger)
        else:
            err(t("app.unknown_option"))
            pause()


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
    "rE": lambda l: menu_regedit(l),
    "re": lambda l: menu_regedit(l),
    "RE": lambda l: menu_regedit(l),
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
    "32": lambda l: menu_performance_boost(l),
    "33": lambda l: menu_envvars(l),
    "34": lambda l: menu_firewall(l),
    "35": lambda l: menu_fontmgr(l),
    "36": lambda l: menu_shortcut_fixer(l),
    "37": lambda l: menu_msi_cache(l),
    "38": lambda l: menu_sysinfo(l),
    "39": lambda l: menu_netspeed(l),
    "40": lambda l: menu_winupdate(l),
    "41": lambda l: menu_dns_hosts(l),
    "42": lambda l: menu_adblocker(l),
    "43": lambda l: menu_wol(l),
    "44": lambda l: menu_factory_wizard(l),
    "45": lambda l: menu_tweaks(l),
    "46": lambda l: menu_pkgmgr(l),
    "47": lambda l: menu_fileencrypt(l),
    "48": lambda l: menu_drivermgr(l),
    "49": lambda l: menu_appmgr(l),
    "50": lambda l: menu_hashcrack(l),
    "51": lambda l: menu_passgen(l),
    "52": lambda l: menu_integrity(l),
    "53": lambda l: menu_netscanner(l),
    "54": lambda l: menu_memscanner(l),
    "55": lambda l: menu_stego(l),
    "56": lambda l: menu_metastrip(l),
    "57": lambda l: menu_hibp(l),
    "58": lambda l: menu_sslcheck(l),
    "59": lambda l: menu_totp(l),
    "60": lambda l: menu_fileanalyze(l),
    "61": lambda l: menu_loganalyze(l),
    "62": lambda l: menu_pwdmgr(l),
    "63": lambda l: menu_backup(l),
    "64": lambda l: menu_startupaudit(l),
    "65": lambda l: menu_sys_dashboard(l),
    "66": lambda l: menu_port_monitor(l),
    "67": lambda l: menu_temp_monitor(l),
    "68": lambda l: menu_battery_info(l),
    "69": lambda l: menu_cam_audit(l),
    "70": lambda l: menu_disk_analyzer(l),
    "71": lambda l: menu_code_fmt(l),
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

        categories = _menu_categories()
        _print_home_categories(categories)

        print(f"  {C}[ 0]{RST} {t('menu.exit')}")
        sep()
        choice = prompt()

        if choice in ("0", "q", "exit", "quit"):
            clr()
            print(f"\n  {G}{t('app.bye')}{RST}\n")
            logger.export_json()
            sys.exit(0)

        try:
            cat_idx = int(choice) - 1
            if 0 <= cat_idx < len(categories):
                cat_label, items = categories[cat_idx]
                _menu_category_view(cat_label, items, logger)
                continue
        except ValueError:
            pass

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


def _ask_snapshot_path(default_path: str = "") -> str:
    suffix = f" [{default_path}]" if default_path else ""
    path = prompt(f"Snapshot JSON path{suffix}: ").strip().strip('"')
    return path or default_path


def _ask_hive_and_key() -> tuple[str, str]:
    raw = prompt("Hive + key (example HKCU\\Software\\Vendor\\App): ").strip().strip('"').strip("\\")
    if not raw:
        return "", ""
    if "\\" in raw:
        hive, key_path = raw.split("\\", 1)
        return hive.upper(), key_path.strip("\\")
    key_path = prompt("Key path (without hive prefix): ").strip().strip('"').strip("\\")
    return raw.upper(), key_path


def menu_regedit(logger: CleanerLogger):
    """rE - snapshot-based registry editor/importer."""
    last_snapshot = ""

    while True:
        header(t("hdr.regedit"))
        info("Create full registry snapshots to JSON, then edit/delete entries and import them back.")
        if last_snapshot:
            print(f"  Last snapshot: {last_snapshot}")
        sep()
        print(f"  {C}[1]{RST} Create full registry snapshot (JSON)")
        print(f"  {C}[2]{RST} Show snapshot info")
        print(f"  {C}[3]{RST} Find keys in snapshot")
        print(f"  {C}[4]{RST} Edit/add snapshot value")
        print(f"  {C}[5]{RST} Delete snapshot key/value")
        print(f"  {C}[6]{RST} Re-import snapshot into registry")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt().strip()

        if c == "0":
            break

        elif c == "1":
            try:
                from core.registry import create_registry_snapshot_json
                out = prompt("Output file [auto in backups/]: ").strip().strip('"')
                info("Creating full registry snapshot... this can take a while.")
                snap_path = create_registry_snapshot_json(out, logger)
                if snap_path:
                    last_snapshot = snap_path
                    ok(f"Snapshot saved: {snap_path}")
                else:
                    err("Snapshot creation failed.")
            except Exception as e:
                err(str(e))
            pause()

        elif c == "2":
            path = _ask_snapshot_path(last_snapshot)
            if not path:
                err("No snapshot file specified.")
                pause()
                continue
            try:
                from core.registry import get_snapshot_info
                meta = get_snapshot_info(path)
                last_snapshot = path
                sep()
                print(f"  File     : {meta.get('path', path)}")
                print(f"  Format   : {meta.get('format', 'unknown')}")
                print(f"  Machine  : {meta.get('machine', 'N/A')}")
                print(f"  Created  : {meta.get('created_at', 'N/A')}")
                if meta.get("updated_at"):
                    print(f"  Updated  : {meta.get('updated_at')}")
                print(f"  Keys     : {meta.get('keys', 0)}")
                print(f"  Values   : {meta.get('values', 0)}")
                print(f"  Errors   : {meta.get('errors', 0)}")
            except Exception as e:
                err(str(e))
            pause()

        elif c == "3":
            path = _ask_snapshot_path(last_snapshot)
            if not path:
                err("No snapshot file specified.")
                pause()
                continue
            query = prompt("Search text (hive/key/value): ").strip()
            limit_raw = prompt("Max results [20]: ").strip()
            try:
                limit = int(limit_raw) if limit_raw else 20
            except ValueError:
                limit = 20

            try:
                from core.registry import list_snapshot_keys
                matches = list_snapshot_keys(path, query=query, limit=max(1, limit))
                last_snapshot = path
                sep()
                if not matches:
                    warn("No matching keys found.")
                else:
                    print(f"  {'#':>3}  {'Key':<72}  Values")
                    sep("-")
                    for i, item in enumerate(matches):
                        full_key = f"{item['hive']}\\{item['key_path']}" if item.get("key_path") else item["hive"]
                        print(f"  {i+1:>3}  {full_key[:72]:<72}  {item.get('value_count', 0):>6}")
                        samples = item.get("sample_values") or []
                        if samples:
                            print(f"       values: {', '.join(samples)}")
            except Exception as e:
                err(str(e))
            pause()

        elif c == "4":
            path = _ask_snapshot_path(last_snapshot)
            if not path:
                err("No snapshot file specified.")
                pause()
                continue

            hive, key_path = _ask_hive_and_key()
            if not hive:
                err("Hive is required.")
                pause()
                continue

            value_name = prompt("Value name (Enter for default value): ").strip()
            value_type = prompt(
                "Type [REG_SZ/REG_DWORD/REG_QWORD/REG_MULTI_SZ/REG_BINARY] "
                "(Enter = keep/current): "
            ).strip().upper()
            value_raw = prompt(
                "Value data (REG_MULTI_SZ uses |, REG_BINARY uses hex bytes): "
            )

            try:
                from core.registry import edit_snapshot_value
                edit_snapshot_value(
                    path,
                    hive,
                    key_path,
                    value_name,
                    value_raw,
                    value_type or None,
                    logger,
                )
                last_snapshot = path
                ok("Snapshot value updated.")
            except Exception as e:
                err(str(e))
            pause()

        elif c == "5":
            path = _ask_snapshot_path(last_snapshot)
            if not path:
                err("No snapshot file specified.")
                pause()
                continue

            mode = prompt("Delete [k]ey or [v]alue? ").strip().lower()
            hive, key_path = _ask_hive_and_key()
            if not hive:
                err("Hive is required.")
                pause()
                continue

            try:
                if mode == "k":
                    warn(f"Delete key from snapshot: {hive}\\{key_path} ?")
                    if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                        from core.registry import delete_snapshot_key
                        removed = delete_snapshot_key(path, hive, key_path, logger)
                        if removed:
                            ok("Snapshot key deleted.")
                        else:
                            err("Key not found in snapshot.")
                elif mode == "v":
                    value_name = prompt("Value name (Enter for default value): ").strip()
                    warn(
                        "Delete value from snapshot: "
                        f"{hive}\\{key_path}::{value_name or '(Default)'} ?"
                    )
                    if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                        from core.registry import delete_snapshot_value
                        removed = delete_snapshot_value(path, hive, key_path, value_name, logger)
                        if removed:
                            ok("Snapshot value deleted.")
                        else:
                            err("Value not found in snapshot.")
                else:
                    err("Unknown delete mode. Use 'k' or 'v'.")
                last_snapshot = path
            except Exception as e:
                err(str(e))
            pause()

        elif c == "6":
            path = _ask_snapshot_path(last_snapshot)
            if not path:
                err("No snapshot file specified.")
                pause()
                continue

            warn("This will write snapshot data back into Windows registry.")
            warn("Administrator privileges are recommended.")
            if prompt(t("prompt.type_yes_confirm")).upper() in ("YES", "ANO"):
                try:
                    from core.registry import import_registry_snapshot
                    results = import_registry_snapshot(path, logger)
                    last_snapshot = path
                    sep()
                    ok(
                        "Imported "
                        f"{results.get('values_imported', 0)}/{results.get('values_total', 0)} values"
                    )
                    print(f"  Keys processed : {results.get('keys_total', 0)}")
                    print(f"  Keys opened    : {results.get('keys_opened', 0)}")
                    print(f"  Failed actions : {results.get('failed', 0)}")
                except Exception as e:
                    err(str(e))
            pause()
        else:
            err(t("app.unknown_option"))
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
        print(f"  {C}[7]{RST} Smart Startup/Services analysis  {DIM}(impact + recommendations){RST}")
        print(f"  {C}[8]{RST} Apply Startup/Services profile   {DIM}(safe/balanced/aggressive){RST}")
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

        elif c == "7":
            mode = prompt("Profile [safe/balanced/aggressive] [balanced]: ").strip().lower() or "balanced"
            try:
                from core.factory import analyze_startup_services

                analysis = analyze_startup_services(logger, mode=mode)
                sep()
                print(f"  {B}Smart Optimizer Analysis{RST}  profile={analysis['mode']}")

                st = analysis["startup"]
                sv = analysis["services"]

                print(f"\n  {B}Startup Entries{RST}")
                print(f"    Total entries           : {st['total']}")
                print(f"    Recommended to disable  : {Y}{st['to_disable']}{RST}")
                print(f"    Estimated boot gain     : {G}{st['estimated_boot_gain_ms']/1000:.1f}s{RST}")

                print(f"\n  {B}Services{RST}")
                print(f"    Total services          : {sv['total']}")
                print(f"    Recommended to disable  : {Y}{sv['to_disable']}{RST}")

                print(f"\n  {B}Top Startup Recommendations{RST}")
                shown = 0
                for r in st["recommendations"]:
                    if r["action"] != "disable":
                        continue
                    shown += 1
                    ic = G if r["impact"] == "low" else Y if r["impact"] == "medium" else R
                    sus = f" {R}[SUS]{RST}" if r.get("suspicious") else ""
                    print(
                        f"    {shown:>2}. {r['name'][:32]:<32}  impact={ic}{r['impact']}{RST}"
                        f"  gain~{r['estimated_gain_ms']}ms{sus}"
                    )
                    print(f"        {DIM}{r['reason']}{RST}")
                    if shown >= 8:
                        break

                print(f"\n  {B}Top Service Recommendations{RST}")
                shown = 0
                for r in sv["recommendations"]:
                    if r["action"] != "disable":
                        continue
                    shown += 1
                    ic = G if r["impact"] == "low" else Y if r["impact"] == "medium" else R
                    print(
                        f"    {shown:>2}. {r['display_name'][:32]:<32}  impact={ic}{r['impact']}{RST}"
                        f"  category={r['category']}"
                    )
                    print(f"        {DIM}{r['reason']}{RST}")
                    if r.get("risk_note"):
                        print(f"        {Y}Risk:{RST} {r['risk_note']}")
                    if shown >= 8:
                        break

            except Exception as e:
                err(str(e))
            pause()

        elif c == "8":
            mode = prompt("Apply profile [safe/balanced/aggressive] [balanced]: ").strip().lower() or "balanced"
            startup_limit_raw = prompt("Max startup entries to disable [12]: ").strip()
            service_limit_raw = prompt("Max services to disable [8]: ").strip()
            try:
                startup_limit = int(startup_limit_raw) if startup_limit_raw else 12
            except ValueError:
                startup_limit = 12
            try:
                service_limit = int(service_limit_raw) if service_limit_raw else 8
            except ValueError:
                service_limit = 8

            warn(
                "This will apply startup/services optimizations with explanations in the report. "
                "All actions are reversible from Startup/Optimizer menus."
            )
            if prompt(t("prompt.type_yes_confirm")).upper() not in ("YES", "ANO"):
                continue

            try:
                from core.factory import apply_startup_services

                result = apply_startup_services(
                    logger,
                    mode=mode,
                    startup_limit=max(0, startup_limit),
                    service_limit=max(0, service_limit),
                )

                sep()
                ok(f"Smart optimizer applied (mode={result['mode']}).")
                print(
                    f"  Startup  : applied {len(result['startup']['applied'])}"
                    f"  failed {len(result['startup']['failed'])}"
                )
                print(
                    f"  Services : applied {len(result['services']['applied'])}"
                    f"  failed {len(result['services']['failed'])}"
                )

                if result["startup"]["applied"]:
                    print(f"\n  {B}Startup disabled:{RST}")
                    for name in result["startup"]["applied"][:10]:
                        print(f"    {G}•{RST} {name}")
                if result["services"]["applied"]:
                    print(f"\n  {B}Services disabled:{RST}")
                    for name in result["services"]["applied"][:10]:
                        print(f"    {G}•{RST} {name}")
                if result["startup"]["failed"] or result["services"]["failed"]:
                    print(f"\n  {Y}Some actions failed (usually admin rights or policy restrictions).{RST}")
                    for name in (result["startup"]["failed"] + result["services"]["failed"])[:10]:
                        print(f"    {R}•{RST} {name}")

            except Exception as e:
                err(str(e))
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
        sep("-")
        print(f"  {C}[8]{RST} Pre-launch scan   {DIM}— static trace scan before the app runs{RST}")
        print(f"  {C}[9]{RST} Protected run      {DIM}— snapshot + optional net block + diff on exit{RST}")
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

        # ── [8] Pre-launch scan ──────────────────────────────
        elif c == "8":
            app_name = prompt("App name or exe to scan (e.g. 'discord', 'obs64'): ").strip()
            if not app_name:
                continue
            info(f"Scanning existing traces for '{app_name}'…")
            try:
                from core.sandbox import pre_launch_scan
                result = pre_launch_scan(app_name, logger)
                summary = result["summary"]
                traces  = result["traces"]
                sep()
                print(f"  {B}Pre-launch snapshot — existing traces for '{app_name}'{RST}")
                sep("-")
                print(f"  Files        : {G if summary['files'] == 0 else Y}{summary['files']}{RST}")
                print(f"  Registry     : {G if summary['registry'] == 0 else Y}{summary['registry']}{RST}")
                print(f"  Services     : {summary['services']}")
                print(f"  Sched. tasks : {summary['scheduled_tasks']}")
                print(f"  Startup      : {summary['startup']}")
                print(f"  Processes    : {G if summary['processes'] == 0 else Y}{summary['processes']}{RST}")
                print(f"  Disk used    : {fmt_bytes(summary['total_size'])}")

                if traces.get("files"):
                    sep("-")
                    print(f"  {Y}Files found:{RST}")
                    for item in traces["files"][:15]:
                        print(f"    {item['category']:<12}  {item['path'][:65]}")
                    if len(traces["files"]) > 15:
                        print(f"    {DIM}… and {len(traces['files'])-15} more{RST}")

                if traces.get("registry"):
                    print(f"  {Y}Registry keys:{RST}")
                    for item in traces["registry"][:10]:
                        print(f"    {item['path'][:70]}")

                if traces.get("processes"):
                    print(f"  {R}Already running:{RST}")
                    for item in traces["processes"]:
                        print(f"    {item['name']}  PID {item['pid']}")

                sep()
                print(f"  {DIM}This is the state BEFORE you run the app.{RST}")
                print(f"  {DIM}Use [9] Protected Run to see what changes after launch.{RST}")
            except Exception as e:
                err(str(e))
            pause()

        # ── [9] Protected run ────────────────────────────────
        elif c == "9":
            exe = prompt("Path to .exe to launch: ").strip().strip('"')
            if not exe or not Path(exe).is_file():
                err("File not found."); pause(); continue

            watch_default = os.path.expanduser("~")
            watch_raw = prompt(f"Watch path [{watch_default}]: ").strip() or watch_default
            if not os.path.isdir(watch_raw):
                err("Directory not found."); pause(); continue

            block_net = prompt("Block internet while running? [Y/n]: ").strip().lower() != "n"

            print()
            if block_net:
                print(f"  {Y}Internet will be blocked for this process via Windows Firewall.{RST}")
            print(f"  {DIM}Taking before-snapshot of '{watch_raw}'… (may take a moment){RST}")

            try:
                from core.sandbox import launch_protected, finish_protected
                ctx = launch_protected(exe, block_network=block_net,
                                       watch_paths=[watch_raw], logger=logger)
                if not ctx["ok"]:
                    err(f"Failed to launch: {ctx.get('error','')}"); pause(); continue

                ok(f"Launched PID {ctx['pid']}  {'[internet BLOCKED]' if ctx['blocked'] else '[internet allowed]'}")
                if block_net and not ctx["blocked"]:
                    warn(f"Firewall block failed: {ctx.get('block_err','')} (admin required)")

                print(f"\n  {Y}App is running.  Press Enter when it exits or you want to stop…{RST}\n")
                try:
                    input()
                except (KeyboardInterrupt, EOFError):
                    pass

                # Kill if still running
                proc = ctx.get("process")
                if proc and proc.poll() is None:
                    warn("Process still running — killing it.")
                    try:
                        proc.kill()
                    except Exception:
                        pass

                info("Taking after-snapshot and computing diff…")
                diff = finish_protected(ctx, logger)
                s = diff["summary"]

                sep("═")
                print(f"  {B}Protected Run — Diff Report{RST}  {DIM}({Path(exe).name}){RST}")
                sep("-")
                print(f"  {G}Added    : {s['added']:>5} file(s){RST}")
                print(f"  {Y}Modified : {s['modified']:>5} file(s){RST}")
                print(f"  {R}Deleted  : {s['deleted']:>5} file(s){RST}")
                print(f"  {DIM}Unchanged: {s['unchanged']:>5} file(s){RST}")
                print(f"  {Y}Registry : {s['registry']:>5} change(s){RST}")
                sep("-")

                if diff["files_added"]:
                    print(f"\n  {G}ADDED FILES ({len(diff['files_added'])}){RST}")
                    for f in diff["files_added"][:20]:
                        print(f"    {G}+{RST} {f}")
                    if len(diff["files_added"]) > 20:
                        print(f"    {DIM}… and {len(diff['files_added'])-20} more{RST}")

                if diff["files_modified"]:
                    print(f"\n  {Y}MODIFIED FILES ({len(diff['files_modified'])}){RST}")
                    for f in diff["files_modified"][:20]:
                        print(f"    {Y}~{RST} {f}")
                    if len(diff["files_modified"]) > 20:
                        print(f"    {DIM}… and {len(diff['files_modified'])-20} more{RST}")

                if diff["files_deleted"]:
                    print(f"\n  {R}DELETED FILES ({len(diff['files_deleted'])}){RST}")
                    for f in diff["files_deleted"][:10]:
                        print(f"    {R}-{RST} {f}")

                if diff["registry"]:
                    print(f"\n  {Y}REGISTRY CHANGES ({len(diff['registry'])}){RST}")
                    for r in diff["registry"][:15]:
                        rtype = r["type"]
                        rcol  = G if "added" in rtype else R if "deleted" in rtype else Y
                        print(f"    {rcol}{rtype:<16}{RST}  {r['path'][:65]}")

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
        print(f"  {C}[5]{RST} Smart full uninstall (name or shortcut folder)")
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
        elif c == "5":
            _menu_uninstaller_smart(logger)


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


def _menu_uninstaller_smart(logger: CleanerLogger):
    """Smart full uninstall by query and/or shortcut location."""
    query = ""
    shortcut_path = ""

    while True:
        header("Uninstaller — Smart Full Wipe")
        print(f"  {C}[1]{RST} Set app query/name")
        print(f"  {C}[2]{RST} Set shortcut folder or .lnk path")
        print(f"  {C}[3]{RST} Find candidates and FULL remove")
        print(f"  {C}[0]{RST} Back")
        sep()
        print(f"  Query         : {query or '(not set)'}")
        print(f"  Shortcut path : {shortcut_path or '(not set)'}")
        sep()

        c = prompt()
        if c == "0":
            return
        if c == "1":
            query = prompt("App name/query: ").strip()
            continue
        if c == "2":
            shortcut_path = prompt("Shortcut folder or .lnk path: ").strip().strip('"')
            if shortcut_path and not Path(shortcut_path).exists():
                warn("Path does not exist. You can still continue with query-only matching.")
                pause()
            continue
        if c != "3":
            continue

        if not query and not shortcut_path:
            err("Set app query or shortcut path first.")
            pause()
            continue

        info("Loading installed programs and searching best candidates...")
        try:
            from core.uninstaller import list_installed_programs, find_program_candidates, full_uninstall_program
            programs = list_installed_programs(logger)
            candidates = find_program_candidates(
                programs,
                query=query,
                shortcut_path=shortcut_path,
                logger=logger,
                limit=15,
            )
        except Exception as e:
            err(str(e))
            pause()
            continue

        if not candidates:
            warn("No matching installed app found.")
            pause()
            continue

        sep()
        print(f"  {'#':>4}  {'Score':>5}  {'Name':<36}  Publisher")
        sep("-")
        for i, cand in enumerate(candidates):
            print(
                f"  {i+1:>4}  {cand.get('match_score', 0):>5}  "
                f"{cand.get('name', '')[:36]:<36}  {cand.get('publisher', '')[:24]}"
            )
        sep()
        pick_raw = prompt("Select # to FULL uninstall (0 = cancel): ").strip()
        if pick_raw in ("", "0"):
            continue

        try:
            pick_idx = int(pick_raw) - 1
            selected = candidates[pick_idx]
        except (ValueError, IndexError):
            err("Invalid number.")
            pause()
            continue

        reason = ", ".join(selected.get("match_reasons", []))
        warn(f"FULL remove '{selected['name']}' and all detected leftovers?")
        if reason:
            info(f"Match reasons: {reason}")
        warn("This removes app files, shortcuts and related registry artifacts.")
        if prompt("Type YES: ").upper() != "YES":
            info("Cancelled.")
            pause()
            continue

        try:
            result = full_uninstall_program(
                selected,
                logger,
                silent=True,
                shortcut_path=shortcut_path,
            )
            stats = result.get("leftovers_found", {})
            sep()
            ok(f"Full remove finished for: {result.get('name', selected['name'])}")
            print(f"  Uninstall command: {'OK' if result.get('uninstall_ok') else 'FAILED/NOT FOUND'}")
            print(f"  Leftovers removed: files={stats.get('files', 0)} dirs={stats.get('dirs', 0)}")
            print(f"                     reg_keys={stats.get('registry', 0)} reg_values={stats.get('registry_values', 0)}")
            print(f"  Freed: {fmt_bytes(int(result.get('bytes_freed', 0)))}")
            if not result.get("uninstall_ok"):
                warn("Uninstall command failed or missing, but cleanup still ran.")
        except Exception as e:
            err(str(e))
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
        print(
            f"  {C}[u #]{RST} Uninstall #   {C}[fu #]{RST} Full wipe #   "
            f"{C}[s word]{RST} Search   {C}[r]{RST} Reset filter"
        )
        print(f"  {C}[smart]{RST} Smart find+wipe   {C}[0]{RST} Back")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.strip().lower() == "smart":
            _menu_uninstaller_smart(logger)
            continue
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
        elif parts[0] == "fu" and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                prog = filtered[idx]
                shortcut_hint = prompt("Optional shortcut folder/.lnk path (Enter to skip): ").strip().strip('"')
                warn(f"FULL remove '{prog['name']}' and all detected leftovers?")
                if prompt("Type YES: ").upper() == "YES":
                    try:
                        from core.uninstaller import full_uninstall_program
                        result = full_uninstall_program(
                            prog,
                            logger,
                            silent=True,
                            shortcut_path=shortcut_hint,
                        )
                        stats = result.get("leftovers_found", {})
                        ok(
                            f"Full wipe done: {prog['name']} | freed {fmt_bytes(int(result.get('bytes_freed', 0)))}"
                        )
                        info(
                            "Removed artifacts: "
                            f"files={stats.get('files', 0)} "
                            f"dirs={stats.get('dirs', 0)} "
                            f"reg_keys={stats.get('registry', 0)} "
                            f"reg_values={stats.get('registry_values', 0)}"
                        )
                        if prog in all_programs:
                            all_programs.remove(prog)
                        if prog in filtered:
                            filtered.remove(prog)
                    except Exception as e:
                        err(str(e))
            except (ValueError, IndexError):
                err("Invalid number.")
            pause()
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
        print(f"  {C}[1]{RST} Export session TXT")
        print(f"  {C}[2]{RST} Export session JSON")
        print(f"  {C}[3]{RST} Show last 20 session entries")
        print(f"  {C}[4]{RST} Export AUDIT TXT  {DIM}(persistent cross-session trail){RST}")
        print(f"  {C}[5]{RST} Export AUDIT JSON")
        print(f"  {C}[6]{RST} Show last 25 audit events")
        print(f"  {C}[0]{RST} Back")
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
        elif c == "4":
            p = logger.export_audit_txt()
            ok(f"Saved: {p}")
            pause()
        elif c == "5":
            p = logger.export_audit_json()
            ok(f"Saved: {p}")
            pause()
        elif c == "6":
            sep()
            rows = logger.tail_audit(limit=25)
            if not rows:
                warn("No audit events yet.")
            else:
                for e in rows:
                    ts = str(e.get("timestamp", ""))[-8:]
                    ok_flag = bool(e.get("success", False))
                    sev = str(e.get("severity", "info")).upper()
                    evt = str(e.get("event", ""))
                    cat = str(e.get("category", ""))
                    details = str(e.get("details", ""))[:72]
                    marker = f"{G}OK{RST}" if ok_flag else f"{R}FAIL{RST}"
                    print(f"  {ts}  [{marker}] [{sev:<7}] [{cat:<10}] {evt:<26} {details}")
            pause()


# ── 18. SCOUT MODE ──────────────────────────────────────────

def menu_scout(logger: CleanerLogger):
    """Scout Mode — deep real-time monitoring of a specific application."""
    import psutil
    from core.scout import ScoutSession
    profile_path = Path(__file__).parent / "profiles"
    profile_path.mkdir(exist_ok=True)
    current: ScoutSession | None = None

    # Event type display config
    TYPE_COLOR = {
        "CREATE":          G,
        "MODIFY":          Y,
        "DELETE":          R,
        "MOVE":            C,
        "DOWNLOAD":        G,
        "DOWNLOAD_UPDATE": Y,
        "SPAWN":           G,
        "EXIT":            DIM,
        "TARGET_FOUND":    Y,
        "CONNECT":         C,
        "REG_ADD":         G,
        "REG_ADD_KEY":     G,
        "REG_MODIFY":      Y,
        "REG_DELETE":      R,
        "REG_DEL_KEY":     R,
        "DLL_LOAD":        C,
        "DLL_WARN":        Y,
        "FILE_ACCESS":     G,
        "DNS_QUERY":       C,
        "PIPE_NEW":        Y,
        "AUTO_STOP":       R,
    }
    TYPE_LABEL = {
        "CREATE":          "FILE+  ",
        "MODIFY":          "FILE~  ",
        "DELETE":          "FILE-  ",
        "MOVE":            "MOVE   ",
        "DOWNLOAD":        "DL+    ",
        "DOWNLOAD_UPDATE": "DL~    ",
        "SPAWN":           "PROC+  ",
        "EXIT":            "PROC-  ",
        "TARGET_FOUND":    "TARGET ",
        "CONNECT":         "NET    ",
        "REG_ADD":         "REG+   ",
        "REG_ADD_KEY":     "REG+K  ",
        "REG_MODIFY":      "REG~   ",
        "REG_DELETE":      "REG-   ",
        "REG_DEL_KEY":     "REG-K  ",
        "DLL_LOAD":        "DLL+   ",
        "DLL_WARN":        "DLL!   ",
        "FILE_ACCESS":     "FOPEN  ",
        "DNS_QUERY":       "DNS    ",
        "PIPE_NEW":        "PIPE+  ",
        "AUTO_STOP":       "STOP   ",
    }

    while True:
        header("Scout Mode")
        if current and current.is_running:
            s = current.get_summary()
            print(f"  {G}[LIVE]{RST} Scouting {B}'{current.app_name}'{RST}")
            print(f"  FOpen:{G}{s.get('file_access_events',0)}{RST}  "
                  f"Files:{G}{s['file_events']}{RST}  "
                  f"Reg:{Y}{s['registry_events']}{RST}  "
                  f"Net:{C}{s['network_events']}{RST}  "
                  f"Procs:{G}{s['process_events']}{RST}  "
                  f"DLL:{C}{s['dll_events']}{RST}")
        sep()
        print(f"  {C}[1]{RST} Start Scout session  (live feed)")
        print(f"  {C}[2]{RST} Stop active session")
        print(f"  {C}[3]{RST} List saved sessions")
        print(f"  {C}[4]{RST} View session report  {DIM}(added / modified / deleted / unchanged){RST}")
        print(f"  {C}[5]{RST} Delete a session")
        print(f"  {C}[6]{RST} Export session to file  {DIM}(HTML nebo JSON){RST}")
        print(f"  {C}[7]{RST} Compare two sessions    {DIM}(diff souborů a registrů){RST}")
        sep("-")
        print(f"  {C}[8]{RST} Pre-launch scan      {DIM}(static analýza stop před spuštěním){RST}")
        print(f"  {C}[9]{RST} Protected run         {DIM}(snapshot + net block + diff na výstupu){RST}")
        _vt_key_file = profile_path / "vt_key.txt"
        _vt_key_set  = _vt_key_file.exists()
        print(f"  {C}[v]{RST} VirusTotal API klíč   {DIM}({'nastaven ✓' if _vt_key_set else 'nenastaveno'}){RST}")
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
            sep("═")
            print(f"  {C}{B}Scout — Track Application{RST}")
            sep("═")
            print(f"  {DIM}Zadejte cestu k exe nebo název procesu.{RST}")
            print(f"  {DIM}Příklady:{RST}  C:\\tools\\spoofer.exe   nebo   spoofer.exe")
            sep()
            inp = prompt("  Aplikace: ").strip().strip('"')
            if not inp:
                continue

            exe_path   = None
            proc_name  = inp
            launch_it  = False

            if os.path.isfile(inp):
                exe_path  = inp
                proc_name = Path(inp).name
                sep()
                print(f"  Nalezeno: {G}{inp}{RST}")
                lc = prompt(f"  {C}[1]{RST} Spustit teď  {C}[2]{RST} Připojit k běžícímu: ").strip()
                launch_it = (lc != "2")
            else:
                # Not a file path — treat as process name; check if already running
                for p in psutil.process_iter(["name"]):
                    try:
                        if p.info["name"].lower() == inp.lower():
                            sep()
                            print(f"  {G}Proces '{inp}' běží (PID {p.pid}).{RST}")
                            proc_name = p.info["name"]
                            break
                    except Exception:
                        pass
                else:
                    sep()
                    print(f"  {DIM}Proces '{inp}' zatím neběží — čeká se na spuštění.{RST}")

            current = ScoutSession(proc_name, str(profile_path), logger)
            if launch_it and exe_path:
                current.start(exe_path=exe_path)
            else:
                current.start(target_process=proc_name)

            clr()
            sep("═")
            print(f"  {G}{B}TRACKING{RST}  {B}{proc_name}{RST}"
                  + (f"  {DIM}[spuštěno]{RST}" if launch_it else f"  {DIM}[attach]{RST}"))
            print(f"  {DIM}Sledované cesty:{RST} {', '.join(current.watch_paths)}")
            sep("═")
            print(f"  {DIM}FOPEN{RST}=soubor otevřen procesem  "
                  f"{G}FILE+{RST}=vytvořen  {Y}FILE~{RST}=změněn  {R}FILE-{RST}=smazán  "
                  f"{C}NET{RST}=síť  {C}DLL+{RST}=dll  "
                  f"{G}REG+{RST}=reg přidán  {Y}REG~{RST}=reg změněn  {R}REG-{RST}=reg smazán")
            sep()
            print(f"  {DIM}Enter=zastavit  p+Enter=pauza/pokračovat  auto-stop při ukončení procesu{RST}\n")

            stop_flag = threading.Event()
            cmd_queue: "_queue.Queue[str]" = _queue.Queue()

            def _read_cmds():
                while not stop_flag.is_set():
                    try:
                        line = input().strip().lower()
                        cmd_queue.put(line)
                    except Exception:
                        stop_flag.set()
                        break

            threading.Thread(target=_read_cmds, daemon=True).start()

            import queue as _q
            while not stop_flag.is_set():
                # handle keyboard commands
                try:
                    cmd = cmd_queue.get_nowait()
                    if cmd == "p":
                        if current.is_paused:
                            current.resume()
                            print(f"  {G}[POKRAČUJI]{RST}")
                        else:
                            current.pause()
                            print(f"  {Y}[PAUZA]{RST}  (p+Enter = pokračovat)")
                    else:
                        stop_flag.set()
                        break
                except _q.Empty:
                    pass

                # auto-stop when target process died
                if getattr(current, "_auto_stop_requested", False):
                    stop_flag.set()
                    break

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
                        extra = f"  [{ev.get('remote_host','')}]  pid={ev.get('pid','')}"
                    elif etype == "SPAWN":
                        extra = f"  pid={ev.get('pid','')} ← {ev.get('parent_pid','')}  {ev.get('exe','')[:50]}"
                    elif etype in ("REG_ADD", "REG_MODIFY", "REG_DELETE", "REG_ADD_KEY", "REG_DEL_KEY"):
                        extra = f"  {str(ev.get('new_value', ev.get('value', '')))[:70]}"
                    elif etype == "DLL_LOAD":
                        extra = f"  pid={ev.get('pid','')}"
                    elif etype == "FILE_ACCESS":
                        extra = f"  pid={ev.get('pid','')}"
                    elif etype == "DNS_QUERY":
                        extra = f"  {ev.get('hostname','')}"
                    elif etype == "PIPE_NEW":
                        extra = f"  {ev.get('path','')}"
                    elif etype == "AUTO_STOP":
                        print(f"  {R}[AUTO-STOP]{RST}  Sledovaný proces ukončen")
                        stop_flag.set()
                        break
                    move_str = f"  →  {dest}" if dest else ""
                    print(f"  {DIM}{ev['time']}{RST}  {col}{label}{RST}  {path}{move_str}{extra}")
                except _q.Empty:
                    pass

            current.stop()
            sep("═")
            s    = current.get_summary()
            risk = current.get_risk_score()
            risk_col = R if risk >= 50 else (Y if risk >= 20 else G)
            ok(f"Session uložena  "
               f"risk:{risk_col}{risk}/100{RST}  "
               f"fopen:{G}{s['file_access_events']}{RST}  "
               f"files:{G}{s['file_events']}{RST}  "
               f"reg:{Y}{s['registry_events']}{RST}  "
               f"net:{C}{s['network_events']}{RST}  "
               f"proc:{G}{s['process_events']}{RST}  "
               f"dll:{C}{s['dll_events']}{RST}  "
               f"dns:{C}{s.get('dns_events',0)}{RST}  "
               f"persist:{Y}{s.get('persistence_events',0)}{RST}  "
               f"risks:{risk_col}{s.get('risk_flags',0)}{RST}")
            verdict = s.get("verdict","")
            if verdict:
                print(f"  {B}Verdict:{RST} {verdict}")
            if current.last_html_export:
                print(f"  {G}HTML report:{RST} {current.last_html_export}")
            # Auto VT check if key is configured
            _vt_key_file = profile_path / "vt_key.txt"
            if _vt_key_file.exists() and current.file_hashes:
                info("VirusTotal check spuštěn na pozadí…")
                import threading as _thr2
                _ses_ref = current
                def _vt_bg():
                    key = _vt_key_file.read_text().strip()
                    _ses_ref.check_virustotal(key)
                    mal = sum(1 for r in _ses_ref.vt_results.values() if r.get("malicious",0)>0)
                    print(f"\n  {R if mal else G}[VT] {len(_ses_ref.vt_results)} hashů zkontrolováno"
                          + (f", {mal} MALICIOUS{RST}" if mal else f", vše čisté{RST}"))
                    # Re-export HTML with VT data
                    try:
                        path2 = _ses_ref.export_html()
                        print(f"  {G}[VT] HTML aktualizován:{RST} {path2}")
                    except Exception:
                        pass
                _thr2.Thread(target=_vt_bg, daemon=True).start()
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

            # ── file diff breakdown ──────────────────────────
            file_evs = session.get("file_events", [])
            created  = [e for e in file_evs if e.get("type") == "CREATE"]
            modified = [e for e in file_evs if e.get("type") == "MODIFY"]
            deleted  = [e for e in file_evs if e.get("type") == "DELETE"]
            moved    = [e for e in file_evs if e.get("type") == "MOVE"]

            if file_evs:
                print(f"\n  {W}{B}FILES  "
                      f"{G}+{len(created)}{RST}  "
                      f"{Y}~{len(modified)}{RST}  "
                      f"{R}-{len(deleted)}{RST}  "
                      f"{C}→{len(moved)}{RST}")
                for label2, subset, col2, prefix in [
                    ("CREATED",  created,  G, "+"),
                    ("MODIFIED", modified, Y, "~"),
                    ("DELETED",  deleted,  R, "-"),
                    ("MOVED",    moved,    C, "→"),
                ]:
                    if not subset:
                        continue
                    print(f"\n    {col2}{label2} ({len(subset)}){RST}")
                    for ev in subset[:20]:
                        dest = f"  →  {ev.get('dest','')}" if ev.get("dest") else ""
                        print(f"      {DIM}{ev.get('time','')}{RST}  {col2}{prefix}{RST}  {ev.get('path','')[:65]}{dest}")
                    if len(subset) > 20:
                        print(f"      {DIM}… and {len(subset)-20} more{RST}")

            # ── other sections ───────────────────────────────
            sections = [
                ("NETWORK CONNECTIONS",  "network_events",  C),
                ("REGISTRY CHANGES",     "registry_events", Y),
                ("DOWNLOADS",            "download_events", G),
                ("PROCESSES",            "process_events",  G),
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
                        extra = f"  {ev.get('old_value','')[:35]} => {ev.get('new_value','')[:35]}"
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

        elif c == "6":
            # ── Export session to file ───────────────────────
            sessions = ScoutSession.load_sessions(str(profile_path))
            if not sessions:
                err("No Scout sessions found.")
                pause()
                continue
            sep()
            print(f"  {'Session ID':<20}  {'Label':<18}  Events")
            sep("-")
            for s in sessions:
                sm = s.get("summary", {})
                print(f"  {s.get('session_id',''):<20}  "
                      f"{s.get('app_name',''):<18}  "
                      f"{sm.get('total_events', 0)}")
            sep()
            sid = prompt("Session ID to export: ").strip()
            session = next((s for s in sessions if s.get("session_id") == sid), None)
            if not session:
                err("Session not found.")
                pause()
                continue

            fmt = prompt("Format — [1] HTML  [2] JSON: ").strip()
            if fmt not in ("1", "2"):
                err("Invalid choice.")
                pause()
                continue

            ext = "html" if fmt == "1" else "json"
            default_out = str(profile_path / f"scout_export_{sid}.{ext}")
            out_path = prompt(f"Uložit do [{default_out}]: ").strip() or default_out

            try:
                tmp = ScoutSession(session.get("app_name", ""), str(profile_path), logger)
                tmp.session_id         = sid
                tmp.watch_paths        = session.get("watch_paths", [session.get("watch_path", "")])
                tmp.target_process     = session.get("target_process")
                tmp.start_time         = session.get("start_time")
                tmp.file_access_events = session.get("file_access_events", [])
                tmp.file_events        = session.get("file_events", [])
                tmp.registry_events    = session.get("registry_events", [])
                tmp.network_events     = session.get("network_events", [])
                tmp.process_events     = session.get("process_events", [])
                tmp.download_events    = session.get("download_events", [])
                tmp.dll_events         = session.get("dll_events", [])
                tmp.dns_events         = session.get("dns_events", [])
                tmp.pipe_events        = session.get("pipe_events", [])
                tmp.risk_flags         = session.get("risk_flags", [])
                tmp.file_hashes        = session.get("file_hashes", {})

                saved = tmp.export_html(out_path) if fmt == "1" else tmp.export_json(out_path)
                ok(f"Exportováno → {saved}")
            except Exception as e:
                err(str(e))
            pause()

        # ── [7] Compare two sessions ─────────────────────────
        elif c == "7":
            sessions = ScoutSession.load_sessions(str(profile_path))
            if len(sessions) < 2:
                err("Potřebuji alespoň dvě uložené session.")
                pause()
                continue
            sep()
            print(f"  {'Session ID':<20}  {'Label':<18}  Events")
            sep("-")
            for s in sessions:
                sm = s.get("summary", {})
                print(f"  {s.get('session_id',''):<20}  "
                      f"{s.get('app_name',''):<18}  "
                      f"{sm.get('total_events', 0)}")
            sep()
            sid_a = prompt("Session ID A: ").strip()
            sid_b = prompt("Session ID B: ").strip()
            sess_a = next((s for s in sessions if s.get("session_id") == sid_a), None)
            sess_b = next((s for s in sessions if s.get("session_id") == sid_b), None)
            if not sess_a or not sess_b:
                err("Session(s) not found."); pause(); continue
            sep()
            print(f"  {B}Porovnání: {sid_a}  vs  {sid_b}{RST}")
            sep("-")

            def _paths_set(sess, key):
                return {e.get("path","") for e in sess.get(key, [])}

            def _compare_list(label, col_a, set_a, set_b):
                only_a = set_a - set_b
                only_b = set_b - set_a
                both   = set_a & set_b
                print(f"  {B}{label}{RST}  A={len(set_a)}  B={len(set_b)}  "
                      f"obě={len(both)}  jen A={G}{len(only_a)}{RST}  jen B={Y}{len(only_b)}{RST}")
                for p in sorted(only_a)[:8]:
                    print(f"    {G}A only{RST}  {p[:80]}")
                for p in sorted(only_b)[:8]:
                    print(f"    {Y}B only{RST}  {p[:80]}")
                if max(len(only_a), len(only_b)) > 8:
                    print(f"    {DIM}… (zobrazeno 8 z každé strany){RST}")

            _compare_list("Soubory (create/modify)",
                          G,
                          _paths_set(sess_a, "file_events"),
                          _paths_set(sess_b, "file_events"))

            _compare_list("Soubory (přístup proc.)",
                          G,
                          _paths_set(sess_a, "file_access_events"),
                          _paths_set(sess_b, "file_access_events"))

            reg_a = {e.get("key","") for e in sess_a.get("registry_events", [])}
            reg_b = {e.get("key","") for e in sess_b.get("registry_events", [])}
            _compare_list("Registr", Y, reg_a, reg_b)

            net_a = {e.get("remote","") for e in sess_a.get("network_events", [])}
            net_b = {e.get("remote","") for e in sess_b.get("network_events", [])}
            _compare_list("Síť (remote)", C, net_a, net_b)

            dns_a = {e.get("hostname","") for e in sess_a.get("dns_events", [])}
            dns_b = {e.get("hostname","") for e in sess_b.get("dns_events", [])}
            _compare_list("DNS dotazy", C, dns_a, dns_b)

            sep()
            ra = sess_a.get("summary",{}).get("risk_score", "?")
            rb = sess_b.get("summary",{}).get("risk_score", "?")
            print(f"  Risk score:  A={R}{ra}{RST}  B={Y}{rb}{RST}")
            pause()

        # ── [8] Pre-launch scan ──────────────────────────────
        elif c == "8":
            app_name = prompt("App name or exe to scan before launch: ").strip()
            if not app_name:
                continue
            info(f"Scanning existing traces for '{app_name}'…")
            try:
                from core.sandbox import pre_launch_scan
                result = pre_launch_scan(app_name, logger)
                summary = result["summary"]
                traces  = result["traces"]
                sep()
                print(f"  {B}Pre-launch — traces found for '{app_name}'{RST}")
                sep("-")
                print(f"  Files      : {Y if summary['files'] else DIM}{summary['files']}{RST}"
                      f"   ({fmt_bytes(summary['total_size'])})")
                print(f"  Registry   : {Y if summary['registry'] else DIM}{summary['registry']}{RST}")
                print(f"  Services   : {summary['services']}")
                print(f"  Tasks      : {summary['scheduled_tasks']}")
                print(f"  Startup    : {summary['startup']}")
                print(f"  Running    : {R if summary['processes'] else DIM}{summary['processes']}{RST}")
                if traces.get("files"):
                    sep("-")
                    for item in traces["files"][:20]:
                        print(f"  {DIM}{item['category']:<12}{RST}  {item['path'][:68]}")
                    if len(traces["files"]) > 20:
                        print(f"  {DIM}… and {len(traces['files'])-20} more{RST}")
                if traces.get("registry"):
                    sep("-")
                    print(f"  {Y}Registry:{RST}")
                    for item in traces["registry"][:10]:
                        print(f"    {item['path'][:70]}")
                sep()
                print(f"  {DIM}Use [7] Protected Run to capture what changes when the app launches.{RST}")
            except Exception as e:
                err(str(e))
            pause()

        # ── [9] Protected / sandboxed run ────────────────────
        elif c == "9":
            exe = prompt("Path to .exe: ").strip().strip('"')
            if not exe or not Path(exe).is_file():
                err("File not found."); pause(); continue

            watch_default = os.path.expanduser("~")
            watch_raw = prompt(f"Watch path [{watch_default}]: ").strip() or watch_default
            if not os.path.isdir(watch_raw):
                err("Directory not found."); pause(); continue

            block_net = prompt("Block internet while running? [Y/n]: ").strip().lower() != "n"
            print(f"\n  {DIM}Snapshotting '{watch_raw}'… this may take a moment{RST}")
            try:
                from core.sandbox import launch_protected, finish_protected
                ctx = launch_protected(exe, block_network=block_net,
                                       watch_paths=[watch_raw], logger=logger)
                if not ctx["ok"]:
                    err(f"Launch failed: {ctx.get('error','')}"); pause(); continue

                ok(f"Launched PID {ctx['pid']}  "
                   f"{'[net BLOCKED]' if ctx['blocked'] else '[net allowed]'}")
                if block_net and not ctx["blocked"]:
                    warn(f"Firewall block failed (admin required): {ctx.get('block_err','')}")

                # Also start a live scout session for maximum detail
                app_label = Path(exe).stem
                scout_ses = ScoutSession(f"protected_{app_label}", str(profile_path), logger)
                scout_ses.start(watch_path=watch_raw)

                print(f"\n  {Y}Monitoring live. Press Enter when done…{RST}\n")
                stop_flag = threading.Event()
                def _wait():
                    try: input()
                    except Exception: pass
                    stop_flag.set()
                threading.Thread(target=_wait, daemon=True).start()

                import queue as _q2
                while not stop_flag.is_set():
                    try:
                        ev = scout_ses.event_queue.get(timeout=0.2)
                        etype = ev.get("type", "")
                        col2  = TYPE_COLOR.get(etype, W)
                        lbl   = TYPE_LABEL.get(etype, f"{etype:<7}")
                        print(f"  {DIM}{ev['time']}{RST}  {col2}{lbl}{RST}  {ev.get('path','')[:70]}")
                    except _q2.Empty:
                        pass

                scout_ses.stop()
                proc = ctx.get("process")
                if proc and proc.poll() is None:
                    try: proc.kill()
                    except Exception: pass

                info("Computing diff…")
                diff = finish_protected(ctx, logger)
                s = diff["summary"]
                sep("═")
                print(f"  {B}Diff Report — {Path(exe).name}{RST}")
                sep("-")
                print(f"  {G}Added    {s['added']:>5}{RST}  {Y}Modified {s['modified']:>5}{RST}  "
                      f"{R}Deleted  {s['deleted']:>5}{RST}  {DIM}Unchanged {s['unchanged']:>5}{RST}  "
                      f"{Y}Registry {s['registry']:>4}{RST}")
                sep("-")
                for label2, subset, col2, prefix in [
                    ("ADDED",    diff["files_added"],    G, "+"),
                    ("MODIFIED", diff["files_modified"], Y, "~"),
                    ("DELETED",  diff["files_deleted"],  R, "-"),
                ]:
                    if not subset:
                        continue
                    print(f"\n  {col2}{label2} ({len(subset)}){RST}")
                    for f in subset[:15]:
                        print(f"    {col2}{prefix}{RST}  {f}")
                    if len(subset) > 15:
                        print(f"    {DIM}… and {len(subset)-15} more{RST}")
                if diff["registry"]:
                    print(f"\n  {Y}REGISTRY ({len(diff['registry'])}){RST}")
                    for r in diff["registry"][:10]:
                        rcol = G if "added" in r["type"] else R if "deleted" in r["type"] else Y
                        print(f"    {rcol}{r['type']:<16}{RST}  {r['path'][:65]}")
                ss = scout_ses.get_summary()
                sep("-")
                ok(f"Scout session also saved — "
                   f"files:{G}{ss['file_events']}{RST}  "
                   f"reg:{Y}{ss['registry_events']}{RST}  "
                   f"net:{C}{ss['network_events']}{RST}  "
                   f"procs:{G}{ss['process_events']}{RST}")
            except Exception as e:
                err(str(e))
            pause()

        # ── [v] VirusTotal API key ────────────────────────────
        elif c == "v":
            _vt_key_file = profile_path / "vt_key.txt"
            sep()
            if _vt_key_file.exists():
                existing = _vt_key_file.read_text().strip()
                print(f"  Aktuální klíč: {DIM}{existing[:8]}…{existing[-4:]}{RST}")
                print(f"  [1] Změnit  [2] Smazat  [0] Zpět")
                ch = prompt().strip()
                if ch == "2":
                    _vt_key_file.unlink()
                    ok("VT klíč smazán.")
                elif ch == "1":
                    new_key = prompt("Nový VT API klíč: ").strip()
                    if new_key:
                        _vt_key_file.write_text(new_key)
                        ok("VT klíč uložen.")
            else:
                print(f"  {DIM}Získej klíč zdarma na virustotal.com → API → Get Free API Key{RST}")
                new_key = prompt("VT API klíč (Enter = přeskočit): ").strip()
                if new_key:
                    _vt_key_file.write_text(new_key)
                    ok("VT klíč uložen. Bude automaticky použit po každé session.")
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
    from datetime import datetime, timedelta
    DAYS = 3
    while True:
        header(t("hist.app_lbl"))
        info(t("hist.loading"))
        try:
            from core.history import get_app_launch_history, delete_app_launch_entry, clear_app_launch_history
            data = get_app_launch_history(logger)
        except Exception as e:
            err(str(e)); pause(); return

        cutoff = datetime.now() - timedelta(days=DAYS)

        raw_ua = data.get("userassist", [])
        # Filter to last 3 days; keep entries with no date too (run_count > 0)
        userassist = []
        for entry in raw_ua:
            last = entry.get("last_run", "")
            if last:
                try:
                    if datetime.strptime(last[:16], "%Y-%m-%d %H:%M") >= cutoff:
                        userassist.append(entry)
                except ValueError:
                    pass
            elif entry.get("run_count", 0) > 0:
                userassist.append(entry)

        recent_docs = data.get("recent_docs", [])
        run_mru    = data.get("run_mru", [])
        display_list = userassist + recent_docs + run_mru

        sep()
        print(f"  {DIM}Showing activity from last {DAYS} days — {len(userassist)} apps, "
              f"{len(recent_docs)} docs, {len(run_mru)} run commands{RST}")
        warn("Deleting an item wipes its ENTIRE launch history from the registry.")
        sep()

        if not display_list:
            warn(t("hist.no_entries"))
        else:
            print(f"  {'#':>4}  {'Name / Command':<45}  {t('hist.run_count'):>5}  {t('hist.last_run')}")
            sep("-")
            for i, entry in enumerate(userassist):
                runs = entry.get("run_count", 0)
                last = entry.get("last_run", t("hist.never"))
                print(f"  {i+1:>4}  {entry.get('name','')[:45]:<45}  {runs:>5}  {last}")
            base = len(userassist)
            for i, entry in enumerate(recent_docs):
                print(f"  {base+i+1:>4}  [doc] {entry.get('name','')[:40]:<40}")
            base += len(recent_docs)
            for i, entry in enumerate(run_mru):
                print(f"  {base+i+1:>4}  [run] {entry.get('command','')[:40]:<40}")

        sep()
        print(f"  {C}[d 1,3]{RST} Delete & wipe history   {C}[all]{RST} Clear all   {C}[0]{RST} {t('menu.back')}")
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
            idxs = _parse_nums(parts[1], len(display_list))
            if not idxs:
                err(t("hist.bad_num")); pause(); continue
            deleted = 0
            for idx in idxs:
                try:
                    if delete_app_launch_entry(display_list[idx], logger):
                        deleted += 1
                except Exception as e:
                    err(t("hist.del_fail", err=str(e)))
            ok(t("hist.entry_del", count=deleted))
            pause()


def menu_performance_boost(logger: CleanerLogger):
    from core.perfboost import (kill_background_apps, trim_ram,
                                 set_high_performance, disable_visual_effects,
                                 stop_heavy_services)
    while True:
        header("Performance Boost")
        print(f"  {DIM}Apply one or more optimizations for an immediate speed boost.{RST}")
        sep()
        print(f"  {C}[1]{RST} Kill background apps  (Teams, Discord, OneDrive, Spotify…)")
        print(f"  {C}[2]{RST} Trim RAM working sets (release memory held by all processes)")
        print(f"  {C}[3]{RST} Switch to High Performance power plan")
        print(f"  {C}[4]{RST} Disable visual effects (animations, shadows, transparency)")
        print(f"  {C}[5]{RST} Stop SysMain & Windows Search services temporarily")
        print(f"  {C}[all]{RST} Apply ALL optimizations at once")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break

        actions = []
        if cmd.lower() == "all":
            actions = ["1", "2", "3", "4", "5"]
        elif cmd in ("1", "2", "3", "4", "5"):
            actions = [cmd]
        else:
            err("Unknown option."); pause(); continue

        for act in actions:
            if act == "1":
                info("Killing background apps…")
                res = kill_background_apps(logger)
                if res["killed"]:
                    ok(f"Killed {res['killed']} app(s): {', '.join(res['names'])}")
                else:
                    print(f"  {DIM}No targeted apps were running.{RST}")

            elif act == "2":
                info("Trimming RAM…")
                res = trim_ram(logger)
                freed_mb = res["freed"] // 1024 // 1024
                ok(f"Trimmed {res['trimmed']} processes — freed ~{freed_mb} MB")

            elif act == "3":
                info("Switching power plan…")
                if set_high_performance(logger):
                    ok("Power plan set to High Performance.")
                else:
                    err("Failed to switch power plan (admin required?).")

            elif act == "4":
                info("Applying best-performance visual settings…")
                if disable_visual_effects(logger):
                    ok("Visual effects minimized. Sign out/in to fully apply.")
                else:
                    err("Failed to apply visual settings.")

            elif act == "5":
                info("Stopping heavy services…")
                res = stop_heavy_services(logger)
                for svc, success in res.items():
                    if success:
                        ok(f"Stopped: {svc}")
                    else:
                        warn(f"Could not stop: {svc}")

        pause()


# ── 33. ENVIRONMENT VARIABLES ─────────────────────────────────

def menu_envvars(logger: CleanerLogger):
    from core.envvars import get_env_vars, set_env_var, delete_env_var
    scope = "user"
    while True:
        header("Environment Variables")
        scope_lbl = f"{G}User{RST}" if scope == "user" else f"{Y}System{RST}"
        print(f"  Scope: {scope_lbl}   {C}[s]{RST} Switch scope")
        sep()
        info("Loading…")
        entries = get_env_vars(scope)
        if not entries:
            warn("No entries found.")
        else:
            print(f"  {'#':>4}  {'Variable':<35}  Value")
            sep("-")
            for i, e in enumerate(entries):
                val_short = e["value"][:60] + ("…" if len(e["value"]) > 60 else "")
                print(f"  {i+1:>4}  {e['name'][:35]:<35}  {val_short}")
        sep()
        print(f"  {C}[add]{RST} Add new   {C}[del 1,3]{RST} Delete   {C}[s]{RST} Switch scope   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.lower() == "s":
            scope = "system" if scope == "user" else "user"
            continue
        if cmd.lower() == "add":
            name = prompt("Variable name: ").strip()
            if not name:
                continue
            value = prompt("Value: ").strip()
            if set_env_var(name, value, scope, logger):
                ok(f"Set: {name}={value}")
            else:
                err("Failed (admin required for system scope).")
            pause()
            continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "del" and len(parts) > 1:
            idxs = _parse_nums(parts[1], len(entries))
            if not idxs:
                err("Invalid number."); pause(); continue
            deleted = 0
            for idx in idxs:
                if delete_env_var(entries[idx]["name"], scope, logger):
                    deleted += 1
            ok(f"Deleted {deleted} variable(s).")
            pause()


# ── 34. FIREWALL RULES ────────────────────────────────────────

def menu_firewall(logger: CleanerLogger):
    from core.firewall import get_firewall_rules, enable_rule, disable_rule, delete_rule
    direction = "all"
    PAGE = 25
    page = 0
    rules: list[dict] = []
    while True:
        header("Firewall Rules")
        dir_lbl = {"all": "All", "in": "Inbound", "out": "Outbound"}[direction]
        print(f"  Direction: {C}{dir_lbl}{RST}   {C}[f in/out/all]{RST} Filter   {C}[r]{RST} Reload")
        sep()
        if not rules:
            info("Loading rules…")
            rules = get_firewall_rules(direction, logger=logger)
        total = len(rules)
        start = page * PAGE
        end = min(start + PAGE, total)
        page_rules = rules[start:end]
        if not page_rules:
            warn("No rules found."); page = 0
        else:
            print(f"  {'#':>4}  {'Name':<45}  {'Dir':<4}  {'Action':<7}  En")
            sep("-")
            for i, rule in enumerate(page_rules):
                enabled = f"{G}Y{RST}" if rule["enabled"] else f"{R}N{RST}"
                direction_short = "IN" if "Inbound" in str(rule["direction"]) else "OUT"
                action_short = "Allow" if "Allow" in str(rule["action"]) else "Block"
                print(f"  {start+i+1:>4}  {rule['name'][:45]:<45}  {direction_short:<4}  {action_short:<7}  {enabled}")
        sep()
        pages = (total + PAGE - 1) // PAGE
        print(f"  Page {page+1}/{pages}   {C}[n]{RST} Next   {C}[p]{RST} Prev")
        print(f"  {C}[tog 1,3]{RST} Toggle   {C}[del 1,3]{RST} Delete   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd == "n":
            if page < pages - 1:
                page += 1
            continue
        if cmd == "p":
            if page > 0:
                page -= 1
            continue
        if cmd == "r":
            rules = []; page = 0; continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "f" and len(parts) > 1:
            direction = parts[1].strip()
            if direction not in ("in", "out", "all"):
                direction = "all"
            rules = []; page = 0; continue
        if parts and parts[0] in ("tog", "del") and len(parts) > 1:
            idxs = _parse_nums(parts[1], total)
            if not idxs:
                err("Invalid number."); pause(); continue
            for idx in idxs:
                rule = rules[idx]
                if parts[0] == "tog":
                    if rule["enabled"]:
                        disable_rule(rule["name"], logger)
                    else:
                        enable_rule(rule["name"], logger)
                else:
                    delete_rule(rule["name"], logger)
            ok(f"Done — {len(idxs)} rule(s) updated.")
            rules = []  # reload
            pause()


# ── 35. FONT MANAGER ─────────────────────────────────────────

def menu_fontmgr(logger: CleanerLogger):
    from core.fontmgr import get_installed_fonts, delete_font
    PAGE = 30
    page = 0
    fonts: list[dict] = []
    while True:
        header("Font Manager")
        if not fonts:
            info("Loading fonts…")
            fonts = get_installed_fonts(logger)
        total = len(fonts)
        start = page * PAGE
        end = min(start + PAGE, total)
        page_fonts = fonts[start:end]
        sep()
        if not page_fonts:
            warn("No fonts found.")
        else:
            print(f"  {'#':>4}  {'Font Name':<50}  {'File':<30}  Size")
            sep("-")
            for i, f in enumerate(page_fonts):
                size_kb = f["size"] // 1024
                miss = f"  {R}[missing]{RST}" if not f["exists"] else ""
                print(f"  {start+i+1:>4}  {f['name'][:50]:<50}  {f['filename'][:30]:<30}  {size_kb}KB{miss}")
        sep()
        pages = max(1, (total + PAGE - 1) // PAGE)
        print(f"  {total} fonts installed   Page {page+1}/{pages}")
        print(f"  {C}[n]{RST} Next   {C}[p]{RST} Prev   {C}[del 1,3]{RST} Delete   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd == "n":
            if page < pages - 1:
                page += 1
            continue
        if cmd == "p":
            if page > 0:
                page -= 1
            continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "del" and len(parts) > 1:
            idxs = _parse_nums(parts[1], total)
            if not idxs:
                err("Invalid number."); pause(); continue
            warn(f"About to delete {len(idxs)} font(s). This cannot be undone.")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            deleted = sum(1 for idx in idxs if delete_font(fonts[idx], logger))
            ok(f"Deleted {deleted} font(s).")
            fonts = []  # reload
            pause()


# ── 36. SHORTCUT FIXER ───────────────────────────────────────

def menu_shortcut_fixer(logger: CleanerLogger):
    from core.shortcutfix import find_broken_shortcuts, delete_shortcuts
    broken: list[dict] = []
    while True:
        header("Shortcut Fixer")
        sep()
        if not broken:
            info("Scanning Desktop, Start Menu…")
            extra = prompt("Scan extra folder (Enter to skip): ").strip()
            broken = find_broken_shortcuts(
                extra_dirs=[extra] if extra else None, logger=logger
            )
        if not broken:
            ok("No broken shortcuts found.")
            pause(); return
        print(f"  {'#':>4}  {'Name':<35}  {'Location':<35}  Target (missing)")
        sep("-")
        for i, s in enumerate(broken):
            print(f"  {i+1:>4}  {s['name'][:35]:<35}  {s['location'][-35:]:<35}  {s['target'][:50]}")
        sep()
        print(f"  {C}[d 1,3]{RST} Delete   {C}[all]{RST} Delete all   {C}[r]{RST} Rescan   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd == "r":
            broken = []; continue
        if cmd.lower() == "all":
            warn(f"Delete all {len(broken)} broken shortcuts?")
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                deleted = delete_shortcuts(broken, logger)
                ok(f"Deleted {deleted} shortcut(s).")
                broken = []
            pause(); continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "d" and len(parts) > 1:
            idxs = _parse_nums(parts[1], len(broken))
            if not idxs:
                err("Invalid number."); pause(); continue
            selected = [broken[i] for i in idxs]
            deleted = delete_shortcuts(selected, logger)
            ok(f"Deleted {deleted} shortcut(s).")
            broken = [b for j, b in enumerate(broken) if j not in idxs]
            pause()


# ── 37. MSI CACHE CLEANER ────────────────────────────────────

def menu_msi_cache(logger: CleanerLogger):
    from core.msicache import find_orphaned_msi, delete_msi_files
    orphans: list[dict] = []
    while True:
        header("MSI Installer Cache Cleaner")
        sep()
        if not orphans:
            info("Scanning C:\\Windows\\Installer for orphaned files…")
            orphans = find_orphaned_msi(logger)
        if not orphans:
            ok("No orphaned installer files found.")
            pause(); return
        total_size = sum(o["size"] for o in orphans)
        print(f"  Found {len(orphans)} orphaned file(s) — {total_size//1024//1024} MB reclaimable")
        sep("-")
        print(f"  {'#':>4}  {'Filename':<40}  {'Type':<5}  Size")
        sep("-")
        for i, o in enumerate(orphans):
            print(f"  {i+1:>4}  {o['name'][:40]:<40}  {o['ext']:<5}  {o['size']//1024}KB")
        sep()
        print(f"  {C}[d 1,3]{RST} Delete selected   {C}[all]{RST} Delete all   {C}[r]{RST} Rescan   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd == "r":
            orphans = []; continue
        if cmd.lower() == "all":
            warn(f"Delete all {len(orphans)} orphaned files ({total_size//1024//1024} MB)?")
            if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                deleted, freed = delete_msi_files(orphans, logger)
                ok(f"Deleted {deleted} files — freed {freed//1024//1024} MB.")
                orphans = []
            pause(); continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "d" and len(parts) > 1:
            idxs = _parse_nums(parts[1], len(orphans))
            if not idxs:
                err("Invalid number."); pause(); continue
            selected = [orphans[i] for i in idxs]
            deleted, freed = delete_msi_files(selected, logger)
            ok(f"Deleted {deleted} files — freed {freed//1024//1024} MB.")
            orphans = [o for j, o in enumerate(orphans) if j not in idxs]
            pause()


# ── 38. SYSTEM INFO ──────────────────────────────────────────

def menu_sysinfo(logger: CleanerLogger):
    from core.sysinfo import collect, export_to_file
    header("System Info Snapshot")
    info("Collecting system information…")
    data = collect(logger)

    def _fmt(val) -> str:
        return str(val) if val is not None else "—"

    sep()
    os_info = data.get("os", {})
    print(f"  {B}OS{RST}       {os_info.get('edition') or os_info.get('name','')}  build {os_info.get('build','')}")
    print(f"           Hostname: {os_info.get('hostname','')}   User: {os_info.get('username','')}")
    print(f"           Installed: {os_info.get('install_date','')}   Last boot: {os_info.get('last_boot','')}")

    cpu = data.get("cpu", {})
    print(f"\n  {B}CPU{RST}      {cpu.get('name','')}")
    print(f"           {cpu.get('physical_cores',0)} physical / {cpu.get('logical_cores',0)} logical cores   "
          f"{cpu.get('freq_mhz',0)} MHz   Usage: {cpu.get('usage_pct',0)}%")

    ram = data.get("ram", {})
    print(f"\n  {B}RAM{RST}      {ram.get('total_gb',0)} GB total   {ram.get('available_gb',0)} GB free   "
          f"{ram.get('used_pct',0)}% used")
    for stick in data.get("ram_sticks", []):
        print(f"           Stick: {stick.get('manufacturer','')} {stick.get('capacity_gb',0)} GB @ {stick.get('speed_mhz',0)} MHz")

    for gpu in data.get("gpu", []):
        print(f"\n  {B}GPU{RST}      {gpu.get('name','')}   VRAM: {gpu.get('vram_mb',0)} MB   Driver: {gpu.get('driver','')}")

    sep()
    print(f"\n  {B}Disks{RST}")
    for d in data.get("disks", []):
        bar_len = 20
        pct = d.get("pct", 0)
        filled = int(bar_len * pct / 100)
        bar = f"{G}{'█' * filled}{DIM}{'░' * (bar_len - filled)}{RST}"
        print(f"    {d.get('device',''):<12} {bar}  {pct}%  "
              f"{d.get('used_gb',0)}/{d.get('total_gb',0)} GB  ({d.get('fstype','')})")

    sep()
    print(f"\n  {B}Network{RST}")
    for net in data.get("network", []):
        print(f"    {net.get('interface',''):<20}  {', '.join(net.get('addresses', []))}")

    sep()
    print(f"\n  {C}[e]{RST} Export to file   {C}[0]{RST} {t('menu.back')}")
    sep()
    cmd = prompt()
    if cmd.lower() == "e":
        path = export_to_file(data, logger=logger)
        ok(f"Saved to: {path}")
        pause()


# ── 39. NETWORK SPEED TEST ───────────────────────────────────

def menu_netspeed(logger: CleanerLogger):
    from core.netspeed import run_full_test, ping_latency, dns_resolution_time
    while True:
        header("Network Speed Test")
        sep()
        print(f"  {C}[1]{RST} Full test (latency + DNS + download ~10 MB)")
        print(f"  {C}[2]{RST} Ping only")
        print(f"  {C}[3]{RST} DNS resolution test")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd == "1":
            info("Running full network test…")
            results = run_full_test(logger)
            sep()
            print(f"  {B}Latency{RST}")
            for p in results.get("ping", []):
                status = f"avg {p['avg_ms']} ms  min {p['min_ms']} ms  max {p['max_ms']} ms"
                if not p["success"]:
                    status = f"{R}unreachable{RST}"
                print(f"    {p['host']:<20}  {status}")
            print(f"\n  {B}DNS Resolution{RST}")
            for d in results.get("dns", []):
                status = f"{d['ms']} ms" if d["success"] else f"{R}failed{RST}"
                print(f"    {d['host']:<25}  {status}")
            dl = results.get("download", {})
            print(f"\n  {B}Download Speed{RST}")
            if dl.get("success"):
                print(f"    {G}{dl['mbps']} Mbps{RST}   "
                      f"({dl['bytes']//1024//1024} MB in {dl['elapsed_s']}s)")
            else:
                print(f"    {R}Download test failed: {dl.get('error','')}{RST}")
            sep()
            summary = results.get("summary", {})
            print(f"  Avg ping: {summary.get('avg_ping_ms',0)} ms   "
                  f"Download: {G}{summary.get('download_mbps',0)} Mbps{RST}")
            pause()
        elif cmd == "2":
            info("Pinging…")
            from core.netspeed import PING_HOSTS
            sep()
            for h in PING_HOSTS:
                res = ping_latency(h)
                status = f"avg {res['avg_ms']} ms" if res["success"] else f"{R}unreachable{RST}"
                print(f"    {h:<20}  {status}")
            pause()
        elif cmd == "3":
            info("Resolving hostnames…")
            from core.netspeed import DNS_HOSTS
            sep()
            for h in DNS_HOSTS:
                res = dns_resolution_time(h)
                status = f"{res['ms']} ms" if res["success"] else f"{R}failed{RST}"
                print(f"    {h:<25}  {status}")
            pause()


# ── 40. WINDOWS UPDATE MANAGER ───────────────────────────────

def menu_winupdate(logger: CleanerLogger):
    from core.winupdate import (get_installed_updates, check_pending_updates,
                                 get_update_pause_status, pause_updates,
                                 resume_updates, trigger_update_check)
    while True:
        header("Windows Update Manager")
        status = get_update_pause_status(logger)
        paused_lbl = f"  {Y}[PAUSED]{RST}" if status.get("paused") else f"  {G}[ACTIVE]{RST}"
        print(f"  Updates: {paused_lbl}")
        sep()
        print(f"  {C}[1]{RST} Show installed updates (last 30)")
        print(f"  {C}[2]{RST} Check for pending updates")
        print(f"  {C}[3]{RST} Pause updates (7 / 14 / 35 days)")
        print(f"  {C}[4]{RST} Resume updates")
        print(f"  {C}[5]{RST} Trigger update scan now")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        elif cmd == "1":
            info("Fetching installed updates…")
            updates = get_installed_updates(logger)
            sep()
            if not updates:
                warn("No updates found (or Get-HotFix unavailable).")
            else:
                print(f"  {'#':>3}  {'ID':<12}  {'Description':<20}  {'Installed':<12}  By")
                sep("-")
                for i, u in enumerate(updates):
                    print(f"  {i+1:>3}  {u['id']:<12}  {u['description'][:20]:<20}  {u['installed_on']:<12}  {u['installed_by'][:20]}")
            pause()
        elif cmd == "2":
            info("Searching for pending updates (may take 30–60s)…")
            pending = check_pending_updates(logger)
            sep()
            if not pending:
                ok("No pending updates found.")
            else:
                print(f"  {len(pending)} update(s) available:")
                sep("-")
                for u in pending:
                    sev_color = R if u["severity"] in ("Critical", "Important") else W
                    print(f"    {sev_color}[{u['severity'][:9]}]{RST}  {u['title']}  ({u['size_mb']} MB)")
            pause()
        elif cmd == "3":
            print(f"  {C}[1]{RST} Pause 7 days   {C}[2]{RST} Pause 14 days   {C}[3]{RST} Pause 35 days")
            c2 = prompt()
            days = {"1": 7, "2": 14, "3": 35}.get(c2, 0)
            if days:
                if pause_updates(days, logger):
                    ok(f"Updates paused for {days} days.")
                else:
                    err("Failed (admin required).")
            pause()
        elif cmd == "4":
            if resume_updates(logger):
                ok("Updates resumed.")
            else:
                err("Failed (admin required).")
            pause()
        elif cmd == "5":
            if trigger_update_check(logger):
                ok("Update scan triggered — check Windows Update in Settings.")
            else:
                err("Failed to trigger scan.")
            pause()


# ── 41. DNS + HOSTS ──────────────────────────────────────────

def menu_dns_hosts(logger: CleanerLogger):
    from core.dnstools import (flush_dns, get_dns_servers, read_hosts,
                                add_hosts_entry, delete_hosts_entry,
                                display_dns_cache)
    while True:
        header("DNS Tools & Hosts Editor")
        servers = get_dns_servers()
        print(f"  DNS servers: {', '.join(servers) or 'unknown'}")
        sep()
        print(f"  {C}[1]{RST} Flush DNS cache")
        print(f"  {C}[2]{RST} View hosts file entries")
        print(f"  {C}[3]{RST} Add hosts entry")
        print(f"  {C}[4]{RST} Delete hosts entry")
        print(f"  {C}[5]{RST} View cached DNS records")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        elif cmd == "1":
            if flush_dns(logger):
                ok("DNS cache flushed.")
            else:
                err("Flush failed (admin required).")
            pause()
        elif cmd == "2":
            entries = read_hosts(logger)
            sep()
            if not entries:
                warn("No custom entries in hosts file.")
            else:
                print(f"  {'#':>3}  {'IP':<20}  {'Hostname':<40}  Comment")
                sep("-")
                for i, e in enumerate(entries):
                    block_tag = f"  {DIM}[blocker]{RST}" if e.get("is_blocker") else ""
                    print(f"  {i+1:>3}  {e['ip']:<20}  {e['host'][:40]:<40}  {e.get('comment','')[:20]}{block_tag}")
            pause()
        elif cmd == "3":
            ip   = prompt("IP address: ").strip()
            host = prompt("Hostname:   ").strip()
            if ip and host:
                if add_hosts_entry(ip, host, logger):
                    ok(f"Added: {ip} → {host}")
                else:
                    err("Failed (admin required to edit hosts).")
            pause()
        elif cmd == "4":
            host = prompt("Hostname to remove: ").strip()
            if host:
                if delete_hosts_entry(host, logger):
                    ok(f"Removed: {host}")
                else:
                    err("Failed (admin required).")
            pause()
        elif cmd == "5":
            info("Reading DNS cache…")
            cache = display_dns_cache(logger)
            sep()
            if not cache:
                warn("Cache empty or unavailable.")
            else:
                for e in cache[:50]:
                    print(f"    {e.get('name',''):<40}  type {e.get('type',''):<5}  {e.get('data','')}")
            pause()


# ── 42. AD BLOCKER ────────────────────────────────────────────

def menu_adblocker(logger: CleanerLogger):
    from core.adblocker import is_enabled, enable, disable, get_blocked_domains, BLOCK_LIST
    while True:
        header("Hosts-based Ad Blocker")
        active = is_enabled()
        status_lbl = f"{G}ENABLED{RST}" if active else f"{R}DISABLED{RST}"
        print(f"  Status: {status_lbl}")
        if active:
            domains = get_blocked_domains()
            print(f"  {len(domains)} domains currently blocked")
        else:
            print(f"  {len(BLOCK_LIST)} domains in block list")
        sep()
        print(f"  {C}[1]{RST} {'Disable' if active else 'Enable'} ad blocker")
        print(f"  {C}[2]{RST} View block list")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        elif cmd == "1":
            if active:
                warn("This will remove the ad-blocking entries from your hosts file.")
                if prompt(t("prompt.type_yes")).upper() in ("YES", "ANO"):
                    if disable(logger):
                        ok("Ad blocker disabled.")
                    else:
                        err("Failed (admin required to edit hosts).")
            else:
                info("Adding block list to hosts file…")
                success, count = enable(logger)
                if success:
                    ok(f"Ad blocker enabled — {count} domains blocked.")
                else:
                    err("Failed (admin required to edit hosts).")
            pause()
        elif cmd == "2":
            domains = get_blocked_domains() if active else BLOCK_LIST
            sep()
            for d in domains:
                print(f"    0.0.0.0  {d}")
            pause()


# ── 43. WAKE-ON-LAN ──────────────────────────────────────────

_WOL_DEVICES_PATH = "wol_devices.json"


def menu_wol(logger: CleanerLogger):
    from core.wol import send_magic_packet, validate_mac, load_devices, save_devices
    devices: list[dict] = load_devices(_WOL_DEVICES_PATH)
    while True:
        header("Wake-on-LAN")
        sep()
        if devices:
            print(f"  {'#':>3}  {'Name':<25}  {'MAC Address':<20}  Broadcast")
            sep("-")
            for i, d in enumerate(devices):
                print(f"  {i+1:>3}  {d.get('name','')[:25]:<25}  {d['mac']:<20}  {d.get('broadcast','255.255.255.255')}")
        else:
            print(f"  {DIM}No saved devices.{RST}")
        sep()
        print(f"  {C}[w 1,3]{RST} Wake device(s)   {C}[add]{RST} Add device   {C}[del 1]{RST} Remove")
        print(f"  {C}[send <MAC>]{RST} Send one-time packet   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt()
        if cmd == "0":
            break
        if cmd.lower() == "add":
            name = prompt("Device name: ").strip()
            mac  = prompt("MAC address (XX:XX:XX:XX:XX:XX): ").strip()
            bc   = prompt("Broadcast IP (Enter for 255.255.255.255): ").strip() or "255.255.255.255"
            if not validate_mac(mac):
                err("Invalid MAC address format."); pause(); continue
            devices.append({"name": name, "mac": mac, "broadcast": bc})
            save_devices(devices, _WOL_DEVICES_PATH)
            ok(f"Saved: {name}")
            pause(); continue
        parts = cmd.split(None, 1)
        if parts and parts[0] == "send" and len(parts) > 1:
            mac = parts[1].strip()
            if send_magic_packet(mac, logger=logger):
                ok(f"Magic packet sent to {mac}")
            else:
                err("Failed — check MAC format.")
            pause(); continue
        if parts and parts[0] == "del" and len(parts) > 1:
            idxs = _parse_nums(parts[1], len(devices))
            if not idxs:
                err("Invalid number."); pause(); continue
            for idx in sorted(idxs, reverse=True):
                removed = devices.pop(idx)
                ok(f"Removed: {removed.get('name','')}")
            save_devices(devices, _WOL_DEVICES_PATH)
            pause(); continue
        if parts and parts[0] == "w" and len(parts) > 1:
            idxs = _parse_nums(parts[1], len(devices))
            if not idxs:
                err("Invalid number."); pause(); continue
            for idx in idxs:
                d = devices[idx]
                if send_magic_packet(d["mac"], d.get("broadcast", "255.255.255.255"), logger=logger):
                    ok(f"Woke: {d.get('name', d['mac'])}")
                else:
                    err(f"Failed: {d.get('name', d['mac'])}")
            pause()


# ── 49. APP MANAGER ─────────────────────────────────────────

def menu_appmgr(logger: CleanerLogger):
    from core import appmgr as _am

    while True:
        header(t("menu.app_mgr"))
        info("Loading running apps…")
        apps = _am.list_user_apps(logger)
        sep()

        if not apps:
            warn("No user apps found.")
        else:
            print(f"  {'#':>3}  {'Blk':<4}  {'Name':<28}  {'CPU':>5}  {'RAM':>8}  {'Conn':>4}  Exe")
            sep("-")
            for i, a in enumerate(apps, 1):
                blk_lbl = f"{R}[B]{RST}" if a["is_blocked"] else f"{DIM}   {RST}"
                conn_col = R if a["active_conns"] > 0 else DIM
                print(f"  {i:>3}  {blk_lbl}  {a['name'][:28]:<28}  "
                      f"{a['cpu_percent']:>4.1f}%  "
                      f"{fmt_bytes(a['memory_bytes']):>8}  "
                      f"{conn_col}{a['active_conns']:>4}{RST}  "
                      f"{DIM}{a['exe'][:40]}{RST}")
            print(f"\n  {len(apps)} apps  │  "
                  f"{sum(1 for a in apps if a['is_blocked'])} blocked  │  "
                  f"{sum(a['active_conns'] for a in apps)} active connections")

        sep()
        print(f"  {C}[k <n>]{RST}  Kill app by number")
        print(f"  {C}[b <n>]{RST}  Block internet  {DIM}(outbound firewall rule){RST}  {Y}[admin]{RST}")
        print(f"  {C}[u <n>]{RST}  Unblock internet")
        print(f"  {C}[ba]   {RST}  Block ALL apps that have active connections  {Y}[admin]{RST}")
        print(f"  {C}[r]    {RST}  Refresh")
        print(f"  {C}[0]    {RST}  {t('menu.back')}")
        sep()
        cmd = prompt().strip().lower()

        if cmd == "0":
            break

        elif cmd == "r":
            continue

        elif cmd == "ba":
            active = [a for a in apps if a["active_conns"] > 0 and not a["is_blocked"]]
            if not active:
                info("No unblocked apps with active connections."); pause(); continue
            warn(f"Block internet for {len(active)} app(s)?")
            print("  " + ", ".join(a["name"] for a in active))
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            for a in active:
                res = _am.block_app_internet(a["exe"], logger)
                ok(f"Blocked {a['name']}") if res["ok"] else err(f"Failed {a['name']}: {res['error']}")
            pause()

        elif cmd.startswith("k "):
            try:
                idx = int(cmd[2:].strip()) - 1
                a = apps[idx]
            except (ValueError, IndexError):
                err("Invalid number."); pause(); continue
            warn(f"Kill '{a['name']}' (PID {a['pid']})?")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            ok(f"Killed.") if _am.kill_app(a["pid"], logger) else err("Failed.")
            pause()

        elif cmd.startswith("b "):
            try:
                idx = int(cmd[2:].strip()) - 1
                a = apps[idx]
            except (ValueError, IndexError):
                err("Invalid number."); pause(); continue
            if a["is_blocked"]:
                warn(f"'{a['name']}' is already blocked."); pause(); continue
            res = _am.block_app_internet(a["exe"], logger)
            if res["ok"]:
                ok(f"Blocked outbound internet for '{a['name']}'.")
                print(f"  {DIM}Rule: {res['rule_name']}{RST}")
            else:
                err(f"Failed: {res['error']} (requires admin)")
            pause()

        elif cmd.startswith("u "):
            try:
                idx = int(cmd[2:].strip()) - 1
                a = apps[idx]
            except (ValueError, IndexError):
                err("Invalid number."); pause(); continue
            res = _am.unblock_app_internet(a["exe"], logger)
            ok(f"Unblocked '{a['name']}'.") if res["ok"] else err("Failed — rule may not exist.")
            pause()

        else:
            err(t("app.unknown_option"))


# ── 45. TWEAKS CENTER ───────────────────────────────────────

def _fmt_tweak_state(state):
    if state is True:
        return f"{G}ON{RST}"
    if state is False:
        return f"{DIM}OFF{RST}"
    return f"{Y}?{RST}"


def _show_dry_run(summary: dict):
    conflicts = summary.get("conflicts", [])
    if conflicts:
        warn(t("twk.conflicts_detected"))
        for c in conflicts:
            print(f"  {Y}•{RST} {c}")
        sep()

    print(f"  {B}{t('twk.dryrun_preview')}{RST}")
    req_admin = 0
    req_restart = 0
    for res in summary.get("results", []):
        mark = f"{G}OK{RST}" if res.get("ok") else f"{R}SKIP{RST}"
        mode = ""
        if res.get("kind") == "toggle":
            mode = f" -> {G}ON{RST}" if res.get("enabled") else f" -> {DIM}OFF{RST}"
        print(f"  [{mark}] {res.get('label', res.get('key', '?'))}{mode}")
        if not res.get("ok"):
            print(f"      {DIM}{res.get('message', '')}{RST}")
            continue

        if res.get("requires_admin"):
            req_admin += 1
        if res.get("restart_required"):
            req_restart += 1

        comp = res.get("compatibility", {})
        if not comp.get("compatible", True):
            print(
                f"      {Y}{t('twk.compatibility_label')}{RST} "
                f"{comp.get('reason', t('twk.not_compatible'))}"
            )

        plan = res.get("plan", [])
        for step in plan[:2]:
            kind = step.get("kind", "step")
            if kind == "registry_set":
                print(f"      {DIM}reg set {step.get('hive')}\\{step.get('key_path')}::{step.get('value_name')}{RST}")
            elif kind == "registry_delete":
                print(f"      {DIM}reg del {step.get('hive')}\\{step.get('key_path')}::{step.get('value_name')}{RST}")
            elif kind == "service_start":
                print(f"      {DIM}service {step.get('service_name')} -> {step.get('new_mode')}{RST}")
            elif kind == "power_scheme":
                print(f"      {DIM}power profile -> {step.get('new_guid')}{RST}")
            elif kind == "command":
                print(f"      {DIM}cmd: {str(step.get('command', ''))[:72]}{RST}")
            else:
                print(f"      {DIM}{kind}: {str(step.get('description', ''))[:72]}{RST}")

    sep()
    print(f"  {t('twk.requires_admin', count=req_admin)}")
    print(f"  {t('twk.requires_restart', count=req_restart)}")


def _run_tweak_batch(
    logger: CleanerLogger,
    tweak_keys: list[str],
    enable: bool | None = None,
    preview_only: bool = False,
):
    from core import tweaks as _tw

    if not tweak_keys:
        err(t("twk.no_selection"))
        return {}

    dry = _tw.dry_run_many(tweak_keys, logger=logger, enable=enable)
    sep()
    _show_dry_run(dry)
    if preview_only:
        return dry

    warn(t("twk.apply_now"))
    if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
        info(t("twk.cancelled_after_dryrun"))
        return dry

    summary = _tw.apply_many(tweak_keys, logger=logger, enable=enable)
    sep()
    print(f"  {B}{t('twk.apply_result')}{RST}")
    for res in summary.get("results", []):
        s = f"{G}OK{RST}" if res.get("ok") else f"{R}FAIL{RST}"
        mode = ""
        if res.get("kind") == "toggle":
            if res.get("enabled") is True:
                mode = f" [{G}ON{RST}]"
            elif res.get("enabled") is False:
                mode = f" [{DIM}OFF{RST}]"
        print(f"  [{s}] {res.get('label', res.get('key', '?'))}{mode}")
        if res.get("message"):
            print(f"      {DIM}{res['message']}{RST}")

    sep()
    bench = summary.get("benchmark", {})
    delta = bench.get("delta", {}) if isinstance(bench, dict) else {}
    if delta:
        print(f"  {B}{t('twk.measured_delta')}{RST}")
        for k in ("cpu_percent", "ram_percent", "startup_enabled", "optional_services_running", "disk_free"):
            if k in delta:
                print(f"    {k:<24} {delta[k]:+}")
        rp = bench.get("report_path", "")
        if rp:
            print(f"    {t('twk.report_path', path=rp)}")
        sep()

    pending = summary.get("pending_restart", {})
    if pending and pending.get("count", 0):
        warn(t("twk.pending_restart", count=pending.get("count", 0)))

    if summary.get("failed", 0):
        warn(t("twk.applied_partial", ok=summary.get("ok", 0), total=summary.get("total", 0)))
    else:
        ok(t("twk.applied_success", ok=summary.get("ok", 0)))
    return summary


def _menu_tweaks_group(logger: CleanerLogger, group_key: str, title: str):
    from core import tweaks as _tw

    while True:
        items = _tw.list_tweaks(group_key)
        header(f"{t('menu.tweaks')} — {title}")
        sep()

        if not items:
            warn(t("twk.group_empty"))
            pause()
            return

        for i, item in enumerate(items, 1):
            caution = f" {Y}[!]{RST}" if item.get("caution") else ""
            fav = "★" if item.get("favorite") else " "
            comp = item.get("compatibility", {})
            bad = f" {R}[X]{RST}" if not comp.get("compatible", True) else ""
            if item.get("kind") == "toggle":
                state = _fmt_tweak_state(item.get("state"))
                print(f"  {C}[{i:>2}]{RST} {fav} {item['label']:<50} {state}{caution}{bad}")
            else:
                print(f"  {C}[{i:>2}]{RST} {fav} {item['label']}{caution}{bad}")

        sep()
        if group_key == "preferences":
            print(
                f"  {C}[n]{RST} {t('twk.cmd_toggle_number')}   "
                f"{C}[on 1,3]{RST} {t('twk.cmd_force_on')}   "
                f"{C}[off 1,3]{RST} {t('twk.cmd_force_off')}"
            )
            print(
                f"  {C}[all on]{RST} {t('twk.cmd_enable_all')}      "
                f"{C}[all off]{RST} {t('twk.cmd_disable_all')}"
            )
        else:
            print(
                f"  {C}[n]{RST} {t('twk.cmd_apply_single')}   "
                f"{C}[a 1,3]{RST} {t('twk.cmd_apply_selected')}   "
                f"{C}[all]{RST} {t('twk.cmd_apply_all')}"
            )
        print(
            f"  {C}[p 1,3]{RST} {t('twk.cmd_preview_only')}     "
            f"{C}[f 1,3]{RST} {t('twk.cmd_toggle_favorite')}"
        )
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()

        cmd = prompt().strip().lower()
        if cmd == "0":
            return

        if cmd.startswith("f "):
            idxs = _parse_nums(cmd[2:], len(items))
            if not idxs:
                err(t("twk.invalid_selection"))
                pause()
                continue
            for i in idxs:
                _tw.toggle_favorite(items[i]["key"])
            ok(t("twk.favorites_updated_count", count=len(idxs)))
            pause()
            continue

        if cmd.startswith("p "):
            idxs = _parse_nums(cmd[2:], len(items))
            if not idxs:
                err(t("twk.invalid_selection"))
                pause()
                continue
            keys = [items[i]["key"] for i in idxs]
            _run_tweak_batch(logger, keys, enable=None, preview_only=True)
            pause()
            continue

        if group_key == "preferences":
            if cmd == "all on":
                keys = [it["key"] for it in items]
                _run_tweak_batch(logger, keys, enable=True)
                pause()
                continue
            if cmd == "all off":
                keys = [it["key"] for it in items]
                _run_tweak_batch(logger, keys, enable=False)
                pause()
                continue
            if cmd.startswith("on "):
                idxs = _parse_nums(cmd[3:], len(items))
                if not idxs:
                    err(t("twk.invalid_selection"))
                    pause()
                    continue
                keys = [items[i]["key"] for i in idxs]
                _run_tweak_batch(logger, keys, enable=True)
                pause()
                continue
            if cmd.startswith("off "):
                idxs = _parse_nums(cmd[4:], len(items))
                if not idxs:
                    err(t("twk.invalid_selection"))
                    pause()
                    continue
                keys = [items[i]["key"] for i in idxs]
                _run_tweak_batch(logger, keys, enable=False)
                pause()
                continue
            if cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(items):
                    _run_tweak_batch(logger, [items[idx]["key"]], enable=None)
                else:
                    err(t("twk.invalid_number"))
                pause()
                continue

            err(t("app.unknown_option"))
            pause()
            continue

        # Action categories
        if cmd == "all":
            caut = [it["label"] for it in items if it.get("caution")]
            if caut:
                warn(t("twk.caution_set"))
                for lbl in caut[:8]:
                    print(f"  {Y}•{RST} {lbl}")
                if len(caut) > 8:
                    print(f"  {DIM}{t('twk.more_count', count=len(caut)-8)}{RST}")
            _run_tweak_batch(logger, [it["key"] for it in items], enable=None)
            pause()
            continue

        if cmd.startswith("a "):
            idxs = _parse_nums(cmd[2:], len(items))
            if not idxs:
                err(t("twk.invalid_selection"))
                pause()
                continue
            selected = [items[i] for i in idxs]
            caut = [it["label"] for it in selected if it.get("caution")]
            if caut:
                warn(t("twk.caution_selected"))
                for lbl in caut:
                    print(f"  {Y}•{RST} {lbl}")
            _run_tweak_batch(logger, [it["key"] for it in selected], enable=None)
            pause()
            continue

        if cmd.isdigit():
            idx = int(cmd) - 1
            if not (0 <= idx < len(items)):
                err(t("twk.invalid_number"))
                pause()
                continue
            sel = items[idx]
            if sel.get("caution"):
                warn(t("twk.caution_single"))
                if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                    continue
            _run_tweak_batch(logger, [sel["key"]], enable=None)
            pause()
            continue

        err(t("app.unknown_option"))
        pause()


def _menu_tweaks_search(logger: CleanerLogger):
    from core import tweaks as _tw

    while True:
        header(f"{t('menu.tweaks')} — {t('twk.search_title')}")
        q = prompt(t("twk.search_prompt")).strip()
        if q == "0":
            return

        rows = _tw.search_tweaks(q, limit=80)
        sep()
        if not rows:
            warn(t("twk.search_none"))
            pause()
            continue

        for i, r in enumerate(rows, 1):
            fav = "★" if r.get("favorite") else " "
            comp = r.get("compatibility", {})
            bad = f" {R}[X]{RST}" if not comp.get("compatible", True) else ""
            if r.get("kind") == "toggle":
                st = _fmt_tweak_state(r.get("state"))
                print(f"  {C}[{i:>2}]{RST} {fav} {r.get('label',''):<50} {st}{bad}  {DIM}{r.get('group','')}{RST}")
            else:
                print(f"  {C}[{i:>2}]{RST} {fav} {r.get('label','')}{bad}  {DIM}{r.get('group','')}{RST}")

        sep()
        print(
            f"  {C}[n]{RST} {t('twk.cmd_apply_single')}   "
            f"{C}[a 1,3]{RST} {t('twk.cmd_apply_selected')}   "
            f"{C}[p 1,3]{RST} {t('twk.cmd_preview_only')}"
        )
        print(f"  {C}[f 1,3]{RST} {t('twk.cmd_toggle_favorite')}   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt().strip().lower()
        if cmd == "0":
            return
        if cmd.startswith("f "):
            idxs = _parse_nums(cmd[2:], len(rows))
            for i in idxs:
                _tw.toggle_favorite(rows[i]["key"])
            ok(t("twk.favorites_updated_count", count=len(idxs)))
            pause()
            continue
        if cmd.startswith("p "):
            idxs = _parse_nums(cmd[2:], len(rows))
            keys = [rows[i]["key"] for i in idxs]
            _run_tweak_batch(logger, keys, preview_only=True)
            pause()
            continue
        if cmd.startswith("a "):
            idxs = _parse_nums(cmd[2:], len(rows))
            keys = [rows[i]["key"] for i in idxs]
            _run_tweak_batch(logger, keys)
            pause()
            continue
        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(rows):
                _run_tweak_batch(logger, [rows[idx]["key"]])
            else:
                err(t("twk.invalid_number"))
            pause()
            continue

        err(t("app.unknown_option"))
        pause()


def _menu_tweaks_favorites(logger: CleanerLogger):
    from core import tweaks as _tw

    while True:
        header(f"{t('menu.tweaks')} — {t('twk.favorites_title')}")
        rows = _tw.list_favorites()
        sep()
        if not rows:
            warn(t("twk.favorites_none"))
            pause()
            return

        for i, r in enumerate(rows, 1):
            if r.get("kind") == "toggle":
                st = _fmt_tweak_state(r.get("state"))
                print(f"  {C}[{i:>2}]{RST} ★ {r.get('label',''):<50} {st}")
            else:
                print(f"  {C}[{i:>2}]{RST} ★ {r.get('label','')}")

        sep()
        print(f"  {C}[n]{RST} {t('twk.cmd_apply_tweak')}   {C}[a 1,3]{RST} {t('twk.cmd_apply_selected')}")
        print(f"  {C}[u 1,3]{RST} {t('twk.cmd_unfavorite')}   {C}[0]{RST} {t('menu.back')}")
        sep()
        cmd = prompt().strip().lower()
        if cmd == "0":
            return
        if cmd.startswith("u "):
            idxs = _parse_nums(cmd[2:], len(rows))
            for i in idxs:
                _tw.set_favorite(rows[i]["key"], is_favorite=False)
            ok(t("twk.favorites_updated"))
            pause()
            continue
        if cmd.startswith("a "):
            idxs = _parse_nums(cmd[2:], len(rows))
            keys = [rows[i]["key"] for i in idxs]
            _run_tweak_batch(logger, keys)
            pause()
            continue
        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(rows):
                _run_tweak_batch(logger, [rows[idx]["key"]])
            else:
                err(t("twk.invalid_number"))
            pause()
            continue
        err(t("app.unknown_option"))
        pause()


def _menu_tweaks_profiles(logger: CleanerLogger):
    from core import tweaks as _tw

    while True:
        header(f"{t('menu.tweaks')} — {t('twk.profiles_title')}")
        print(f"  {C}[1]{RST} {t('twk.profiles_list')}")
        print(f"  {C}[2]{RST} {t('twk.profiles_save')}")
        print(f"  {C}[3]{RST} {t('twk.profiles_apply')}")
        print(f"  {C}[4]{RST} {t('twk.profiles_export')}")
        print(f"  {C}[5]{RST} {t('twk.profiles_import')}")
        print(f"  {C}[6]{RST} {t('twk.profiles_delete')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt().strip()
        if c == "0":
            return

        if c == "1":
            rows = _tw.list_profiles()
            sep()
            if not rows:
                warn(t("twk.profiles_none"))
            else:
                for r in rows:
                    print(f"  {B}{r.get('name','')}{RST}  ({len(r.get('keys', []))} tweaks)")
                    if r.get("description"):
                        print(f"      {DIM}{r.get('description')}{RST}")
            pause()

        elif c == "2":
            name = prompt(t("twk.profiles_prompt_name")).strip()
            if not name:
                continue
            desc = prompt(t("twk.profiles_prompt_desc")).strip()
            keys_raw = prompt(t("twk.profiles_prompt_keys")).strip()
            if keys_raw.lower() == "favorites":
                keys = [r["key"] for r in _tw.list_favorites()]
            else:
                keys = [k.strip() for k in keys_raw.replace(";", ",").split(",") if k.strip()]
            res = _tw.save_profile(name, keys, description=desc)
            ok(t("twk.profiles_saved", name=res.get("name", ""))) if res.get("ok") else err(res.get("message", t("twk.failed")))
            pause()

        elif c == "3":
            name = prompt(t("twk.profiles_prompt_apply")).strip()
            loaded = _tw.load_profile(name)
            if not loaded.get("ok"):
                err(loaded.get("message", t("twk.profiles_not_found")))
                pause()
                continue
            keys = loaded.get("keys", [])
            if not keys:
                err(t("twk.profiles_no_valid_keys"))
                pause()
                continue
            _run_tweak_batch(logger, keys)
            pause()

        elif c == "4":
            name = prompt(t("twk.profiles_prompt_export")).strip()
            default = str(Path("profiles") / f"{name}.json") if name else ""
            path = prompt(t("twk.profiles_prompt_export_path", default=default)).strip().strip('"') or default
            res = _tw.export_profile(name, path)
            ok(t("twk.profiles_exported", path=res.get("path", ""))) if res.get("ok") else err(res.get("message", t("twk.profiles_export_failed")))
            pause()

        elif c == "5":
            path = prompt(t("twk.profiles_prompt_import_path")).strip().strip('"')
            if not path:
                continue
            name_override = prompt(t("twk.profiles_prompt_name_override")).strip()
            res = _tw.import_profile(path, name_override=name_override)
            ok(t("twk.profiles_imported", name=res.get("name", ""))) if res.get("ok") else err(res.get("message", t("twk.profiles_import_failed")))
            pause()

        elif c == "6":
            name = prompt(t("twk.profiles_prompt_delete")).strip()
            if not name:
                continue
            warn(t("twk.profiles_delete_confirm", name=name))
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            res = _tw.delete_profile(name)
            ok(t("twk.profiles_deleted")) if res.get("ok") else err(res.get("message", t("twk.profiles_delete_failed")))
            pause()

        else:
            err(t("app.unknown_option"))
            pause()


def _menu_tweaks_ops(logger: CleanerLogger):
    from core import tweaks as _tw

    while True:
        header(f"{t('menu.tweaks')} — {t('twk.ops_title')}")
        pend = _tw.get_pending_restart()
        hist = _tw.get_undo_overview(limit=8)
        print(f"  {t('twk.ops_pending_count', count=pend.get('count', 0))}")
        print(f"  {t('twk.ops_batches_count', count=len(hist.get('batches', [])))}")
        print(f"  {t('twk.ops_changes_count', count=len(hist.get('changes', [])))}")
        sep()
        print(f"  {C}[1]{RST} {t('twk.ops_undo_change')}")
        print(f"  {C}[2]{RST} {t('twk.ops_undo_batch')}")
        print(f"  {C}[3]{RST} {t('twk.ops_show_pending')}")
        print(f"  {C}[4]{RST} {t('twk.ops_clear_pending')}")
        print(f"  {C}[5]{RST} {t('twk.ops_show_history')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt().strip()
        if c == "0":
            return

        if c == "1":
            res = _tw.undo_last_change(logger)
            ok(res.get("message", t("twk.ops_undo_done"))) if res.get("ok") else err(res.get("message", t("twk.ops_undo_failed")))
            pause()

        elif c == "2":
            res = _tw.undo_last_batch(logger)
            ok(res.get("message", t("twk.ops_batch_undo_done"))) if res.get("ok") else err(res.get("message", t("twk.ops_batch_undo_failed")))
            pause()

        elif c == "3":
            sep()
            rows = pend.get("items", [])
            if not rows:
                info(t("twk.ops_no_pending"))
            else:
                for r in rows:
                    print(f"  {r.get('timestamp','')[:19]}  {r.get('label','')}  {DIM}({r.get('key','')}){RST}")
            pause()

        elif c == "4":
            res = _tw.clear_pending_restart()
            ok(t("twk.ops_cleared_pending", count=res.get("cleared", 0)))
            pause()

        elif c == "5":
            sep()
            print(f"  {B}{t('twk.ops_recent_batches')}{RST}")
            for b in hist.get("batches", [])[:8]:
                st = f"{DIM}{t('twk.state_undone')}{RST}" if b.get("undone") else f"{G}{t('twk.state_active')}{RST}"
                print(f"    #{b.get('id')}  {b.get('timestamp','')[:19]}  {st}  keys={len(b.get('keys', []))}")
            print(f"\n  {B}{t('twk.ops_recent_changes')}{RST}")
            for ch in hist.get("changes", [])[:8]:
                st = f"{DIM}{t('twk.state_undone')}{RST}" if ch.get("undone") else f"{G}{t('twk.state_active')}{RST}"
                rv = t("twk.reversible") if ch.get("reversible") else t("twk.non_reversible")
                print(f"    #{ch.get('id')}  {ch.get('label','')}  {st}  {rv}")
            pause()

        else:
            err(t("app.unknown_option"))
            pause()


def menu_tweaks(logger: CleanerLogger):
    while True:
        header(t("menu.tweaks"))
        print(f"  {DIM}{t('twk.menu_desc')}{RST}")
        sep()
        print(f"  {C}[1]{RST} {t('twk.menu_essential')}")
        print(f"  {C}[2]{RST} {t('twk.menu_advanced')}")
        print(f"  {C}[3]{RST} {t('twk.menu_preferences')}")
        print(f"  {C}[4]{RST} {t('twk.menu_performance')}")
        print(f"  {C}[5]{RST} {t('twk.menu_search')}")
        print(f"  {C}[6]{RST} {t('twk.menu_favorites')}")
        print(f"  {C}[7]{RST} {t('twk.menu_profiles')}")
        print(f"  {C}[8]{RST} {t('twk.menu_ops')}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()

        c = prompt().strip()
        if c == "0":
            break
        if c == "1":
            _menu_tweaks_group(logger, "essential", t("twk.menu_essential"))
        elif c == "2":
            _menu_tweaks_group(logger, "advanced", t("twk.menu_advanced"))
        elif c == "3":
            _menu_tweaks_group(logger, "preferences", t("twk.menu_preferences"))
        elif c == "4":
            _menu_tweaks_group(logger, "performance", t("twk.menu_performance"))
        elif c == "5":
            _menu_tweaks_search(logger)
        elif c == "6":
            _menu_tweaks_favorites(logger)
        elif c == "7":
            _menu_tweaks_profiles(logger)
        elif c == "8":
            _menu_tweaks_ops(logger)
        else:
            err(t("app.unknown_option"))
            pause()


# ── 44. FACTORY WIZARD ──────────────────────────────────────

def menu_factory_wizard(logger: CleanerLogger):
    from core import factory as _fw
    from core import pkgmgr as _pkg

    while True:
        profiles = _fw.get_factory_profiles()

        header(t("menu.factory_wizard"))
        print(f"  {DIM}Factory setup for a fresh PC: apps + startup/services tuning + audit trail.{RST}")
        sep()
        for i, p in enumerate(profiles, 1):
            print(f"  {C}[{i}]{RST} {p['label']}")
            print(f"      {DIM}{p['description']}{RST}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()

        raw = prompt("Select profile: ").strip()
        if raw == "0":
            break

        try:
            profile = profiles[int(raw) - 1]
        except (ValueError, IndexError):
            err("Invalid profile number.")
            pause()
            continue

        while True:
            plan = _fw.preview_factory_plan(profile["id"])
            header(f"{t('menu.factory_wizard')} — {profile['label']}")
            print(f"  {B}Plan summary{RST}")
            sep("-")
            print(f"  App bundle         : {plan['manifest_name']}")
            print(f"  Packages           : {plan['manifest_packages']}  ({plan['manifest_required']} required, {plan['manifest_optional']} optional)")
            print(f"  Optimizer profile  : {plan['optimizer_mode']}")
            print(f"  Power target       : {plan['power_target']}")
            sep()
            print(f"  {C}[1]{RST} Run full profile  {DIM}(recommended one-click){RST}")
            print(f"  {C}[2]{RST} Preview startup/services recommendations")
            print(f"  {C}[3]{RST} Apply only startup/services optimizer")
            print(f"  {C}[4]{RST} Install only app bundle (manifest)")
            print(f"  {C}[5]{RST} Export profile manifest template")
            print(f"  {C}[0]{RST} Back")
            sep()

            c = prompt().strip().lower()
            if c == "0":
                break

            elif c == "1":
                checkpoint = prompt("Create restore checkpoint first? [Y/n]: ").strip().lower() != "n"
                apps = prompt("Install app bundle? [Y/n]: ").strip().lower() != "n"
                optimize = prompt("Apply startup/services optimizer? [Y/n]: ").strip().lower() != "n"
                retries_raw = prompt("Retries per package [1]: ").strip()
                try:
                    retries = int(retries_raw) if retries_raw else 1
                except ValueError:
                    retries = 1

                warn("This will run provisioning actions that change system settings and startup behavior.")
                if prompt(t("prompt.type_yes_confirm")).upper() not in ("YES", "ANO"):
                    continue

                info("Running Factory Wizard profile…")
                try:
                    result = _fw.run_factory_wizard(
                        profile["id"],
                        logger,
                        create_checkpoint=checkpoint,
                        install_apps=apps,
                        optimize_system=optimize,
                        retries=max(0, retries),
                    )

                    sep("═")
                    if result.get("ok"):
                        ok("Factory Wizard completed successfully.")
                    else:
                        warn("Factory Wizard completed with issues. See summary below.")

                    chk = result.get("checkpoint", {})
                    if chk.get("enabled"):
                        if chk.get("ok"):
                            ok(f"Checkpoint: {chk.get('name', '')}")
                        else:
                            err(f"Checkpoint failed: {chk.get('error', 'unknown error')}")

                    man = result.get("manifest", {})
                    if man.get("enabled"):
                        line = (
                            f"Manifest '{man.get('name', '')}': installed {man.get('installed', 0)} "
                            f"failed {man.get('failed', 0)} skipped {man.get('skipped', 0)}"
                        )
                        ok(line) if man.get("ok") else err(line)

                    opt_res = result.get("optimizer", {})
                    if opt_res.get("enabled"):
                        line = (
                            f"Optimizer ({opt_res.get('mode', 'n/a')}): startup applied {opt_res.get('startup_applied', 0)} "
                            f"failed {opt_res.get('startup_failed', 0)}; services applied {opt_res.get('services_applied', 0)} "
                            f"failed {opt_res.get('services_failed', 0)}"
                        )
                        ok(line) if opt_res.get("ok") else err(line)

                    pwr = result.get("power", {})
                    if pwr:
                        if pwr.get("ok"):
                            ok(f"Power plan switched to: {pwr.get('name', pwr.get('target', ''))}")
                        else:
                            err(f"Power plan switch failed: {pwr.get('error', 'unknown error')}")

                except Exception as e:
                    err(str(e))
                pause()

            elif c == "2":
                try:
                    analysis = _fw.analyze_startup_services(logger, mode=profile["optimizer_mode"])
                    st = analysis["startup"]
                    sv = analysis["services"]

                    sep()
                    print(f"  {B}Startup recommendations{RST}")
                    print(
                        f"    Total: {st['total']}  |  Disable: {Y}{st['to_disable']}{RST}  |  "
                        f"Estimated boot gain: {G}{st['estimated_boot_gain_ms']/1000:.1f}s{RST}"
                    )
                    shown = 0
                    for r in st["recommendations"]:
                        if r["action"] != "disable":
                            continue
                        shown += 1
                        print(f"    {shown:>2}. {r['name'][:34]:<34}  {DIM}{r['reason']}{RST}")
                        if shown >= 10:
                            break

                    print(f"\n  {B}Service recommendations{RST}")
                    print(f"    Total: {sv['total']}  |  Disable: {Y}{sv['to_disable']}{RST}")
                    shown = 0
                    for r in sv["recommendations"]:
                        if r["action"] != "disable":
                            continue
                        shown += 1
                        print(f"    {shown:>2}. {r['display_name'][:34]:<34}  {DIM}{r['reason']}{RST}")
                        if r.get("risk_note"):
                            print(f"        {Y}Risk:{RST} {r['risk_note']}")
                        if shown >= 10:
                            break
                except Exception as e:
                    err(str(e))
                pause()

            elif c == "3":
                startup_limit_raw = prompt("Max startup entries to disable [12]: ").strip()
                service_limit_raw = prompt("Max services to disable [8]: ").strip()
                try:
                    startup_limit = int(startup_limit_raw) if startup_limit_raw else 12
                except ValueError:
                    startup_limit = 12
                try:
                    service_limit = int(service_limit_raw) if service_limit_raw else 8
                except ValueError:
                    service_limit = 8

                warn(
                    f"Apply optimizer profile '{profile['optimizer_mode']}' now? "
                    "Actions are reversible but require admin rights for some services."
                )
                if prompt(t("prompt.type_yes_confirm")).upper() not in ("YES", "ANO"):
                    continue

                try:
                    result = _fw.apply_startup_services(
                        logger,
                        mode=profile["optimizer_mode"],
                        startup_limit=max(0, startup_limit),
                        service_limit=max(0, service_limit),
                    )
                    sep()
                    ok(
                        f"Applied. Startup: {len(result['startup']['applied'])} ok / {len(result['startup']['failed'])} fail. "
                        f"Services: {len(result['services']['applied'])} ok / {len(result['services']['failed'])} fail."
                    )
                except Exception as e:
                    err(str(e))
                pause()

            elif c == "4":
                retries_raw = prompt("Retries per package [1]: ").strip()
                try:
                    retries = int(retries_raw) if retries_raw else 1
                except ValueError:
                    retries = 1

                warn(f"Install app bundle for profile '{profile['label']}'?")
                if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                    continue

                try:
                    manifest = _pkg.get_builtin_manifest(profile["manifest_profile"])
                    result = _pkg.install_from_manifest(manifest, logger=logger, retries=max(0, retries))
                    if result.get("ok"):
                        ok(
                            f"Bundle done: installed {result.get('installed', 0)} / {result.get('total', 0)}"
                            f" (optional skipped {result.get('skipped', 0)})."
                        )
                    else:
                        err(
                            f"Bundle finished with failures: failed {result.get('failed', 0)} / {result.get('total', 0)}."
                        )
                except Exception as e:
                    err(str(e))
                pause()

            elif c == "5":
                default_path = str(Path("manifests") / f"{profile['id']}_factory_template.json")
                path = prompt(f"Output path [{default_path}]: ").strip().strip('"') or default_path
                overwrite = prompt("Overwrite if exists? [y/N]: ").strip().lower() == "y"
                try:
                    out = _pkg.write_manifest_template(path, profile=profile["manifest_profile"], overwrite=overwrite)
                    ok(f"Template saved: {out}")
                except Exception as e:
                    err(str(e))
                pause()

            else:
                err(t("app.unknown_option"))
                pause()


# ── 46. PACKAGE MANAGER ─────────────────────────────────────

def menu_pkgmgr(logger: CleanerLogger):
    from core import pkgmgr as _pkg

    wg = _pkg.winget_available()
    ch = _pkg.choco_available()

    while True:
        header(t("menu.pkg_mgr"))
        wg_lbl = f"{G}available{RST}" if wg else f"{R}not found{RST}"
        ch_lbl = f"{G}available{RST}" if ch else f"{R}not found{RST}"
        print(f"  winget: {wg_lbl}   Chocolatey: {ch_lbl}")
        sep()
        print(f"  {C}[1]{RST} List installed packages")
        print(f"  {C}[2]{RST} Search packages")
        print(f"  {C}[3]{RST} Install a package")
        print(f"  {C}[4]{RST} Uninstall a package")
        print(f"  {C}[5]{RST} Show upgradable  {DIM}(winget){RST}")
        print(f"  {C}[6]{RST} Upgrade all  {DIM}(winget){RST}")
        print(f"  {C}[7]{RST} Upgrade all  {DIM}(choco){RST}")
        print(f"  {C}[8]{RST} Install from manifest JSON")
        print(f"  {C}[9]{RST} Create manifest template")
        print(f"  {C}[10]{RST} Install built-in app bundle")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "1":
            backend = _pick_backend(wg, ch)
            if not backend:
                err("No package manager found."); pause(); continue
            info("Loading installed packages…")
            pkgs = _pkg.winget_list(logger) if backend == "winget" else _pkg.choco_list(logger)
            sep()
            if not pkgs:
                warn("No packages found.")
            else:
                print(f"  {'#':>4}  {'Name':<35}  {'Version':<16}  {'Id'}")
                sep("-")
                for i, p in enumerate(pkgs, 1):
                    print(f"  {i:>4}  {p.get('Name','')[:35]:<35}  {p.get('Version','')[:16]:<16}  {p.get('Id','')}")
                print(f"\n  Total: {len(pkgs)}")
            pause()

        elif c == "2":
            q = prompt("Search query: ").strip()
            if not q:
                continue
            backend = _pick_backend(wg, ch)
            if not backend:
                err("No package manager found."); pause(); continue
            info(f"Searching '{q}'…")
            pkgs = _pkg.winget_search(q, logger) if backend == "winget" else _pkg.choco_search(q, logger)
            sep()
            if not pkgs:
                warn("No results.")
            else:
                print(f"  {'#':>4}  {'Name':<35}  {'Version':<16}  {'Id'}")
                sep("-")
                for i, p in enumerate(pkgs, 1):
                    print(f"  {i:>4}  {p.get('Name','')[:35]:<35}  {p.get('Version','')[:16]:<16}  {p.get('Id','')}")
            pause()

        elif c == "3":
            pkg_id = prompt("Package ID (e.g. Notepad++.Notepad++): ").strip()
            if not pkg_id:
                continue
            backend = _pick_backend(wg, ch)
            if not backend:
                err("No package manager found."); pause(); continue
            info(f"Installing '{pkg_id}' via {backend}… (this may take a minute)")
            result = _pkg.winget_install(pkg_id, logger) if backend == "winget" else _pkg.choco_install(pkg_id, logger)
            if result["ok"]:
                ok(f"Installed '{pkg_id}'.")
            else:
                err(f"Failed (code {result['code']}).")
                if result["error"]:
                    print(f"  {DIM}{result['error'][:200]}{RST}")
            pause()

        elif c == "4":
            pkg_id = prompt("Package ID to uninstall: ").strip()
            if not pkg_id:
                continue
            warn(f"Uninstall '{pkg_id}'?")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            backend = _pick_backend(wg, ch)
            if not backend:
                err("No package manager found."); pause(); continue
            info(f"Uninstalling '{pkg_id}'…")
            result = _pkg.winget_uninstall(pkg_id, logger) if backend == "winget" else _pkg.choco_uninstall(pkg_id, logger)
            ok(f"Done.") if result["ok"] else err(f"Failed (code {result['code']}).")
            pause()

        elif c == "5":
            if not wg:
                err("winget not available."); pause(); continue
            info("Checking for upgradable packages…")
            pkgs = _pkg.winget_upgradable(logger)
            sep()
            if not pkgs:
                ok("All packages up to date.")
            else:
                print(f"  {'Name':<35}  {'Current':<14}  {'Available'}")
                sep("-")
                for p in pkgs:
                    print(f"  {p.get('Name','')[:35]:<35}  {p.get('Version','')[:14]:<14}  {G}{p.get('Available','')}{RST}")
                print(f"\n  {len(pkgs)} upgrade(s) available.")
            pause()

        elif c == "6":
            if not wg:
                err("winget not available."); pause(); continue
            warn("Upgrade ALL packages via winget?")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            info("Upgrading all packages… (may take several minutes)")
            result = _pkg.winget_upgrade_all(logger)
            ok("Upgrade complete.") if result["ok"] else err(f"Some upgrades failed (code {result['code']}).")
            pause()

        elif c == "7":
            if not ch:
                err("Chocolatey not available."); pause(); continue
            warn("Upgrade ALL choco packages?")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            info("Upgrading all choco packages… (may take several minutes)")
            result = _pkg.choco_upgrade_all(logger)
            ok("Upgrade complete.") if result["ok"] else err(f"Failed (code {result['code']}).")
            pause()

        elif c == "8":
            default_path = str(Path("manifests") / "my_setup.json")
            path = prompt(f"Manifest JSON path [{default_path}]: ").strip().strip('"') or default_path
            retries_raw = prompt("Retries per package [1]: ").strip()
            try:
                retries = int(retries_raw) if retries_raw else 1
            except ValueError:
                retries = 1

            info(f"Installing from manifest: {path}")
            try:
                result = _pkg.install_from_manifest_file(path, logger=logger, retries=max(0, retries))
                if result.get("ok"):
                    ok(
                        f"Manifest done: installed {result.get('installed', 0)} / {result.get('total', 0)} "
                        f"(optional skipped {result.get('skipped', 0)})."
                    )
                else:
                    err(
                        f"Manifest finished with failures: failed {result.get('failed', 0)} / {result.get('total', 0)}."
                    )
                    if result.get("error"):
                        print(f"  {DIM}{result.get('error')}{RST}")

                failed_rows = [r for r in result.get("entries", []) if not r.get("ok") and not r.get("skipped")]
                if failed_rows:
                    sep("-")
                    print("  Failed packages:")
                    for row in failed_rows[:10]:
                        print(
                            f"    {R}•{RST} {row.get('name', row.get('id', 'unknown'))}  "
                            f"backend={row.get('backend', 'n/a')}  code={row.get('code', 'n/a')}"
                        )

            except Exception as e:
                err(str(e))
            pause()

        elif c == "9":
            profiles = _pkg.list_builtin_manifest_profiles()
            sep()
            print("  Built-in template sources:")
            for i, name in enumerate(profiles, 1):
                print(f"  {C}[{i}]{RST} {name}")
            sep()
            pick = prompt("Profile number [1]: ").strip() or "1"
            try:
                profile_name = profiles[int(pick) - 1]
            except (ValueError, IndexError):
                err("Invalid profile number.")
                pause()
                continue

            default_path = str(Path("manifests") / f"{profile_name}_template.json")
            path = prompt(f"Output path [{default_path}]: ").strip().strip('"') or default_path
            overwrite = prompt("Overwrite if exists? [y/N]: ").strip().lower() == "y"

            try:
                out = _pkg.write_manifest_template(path, profile=profile_name, overwrite=overwrite)
                ok(f"Template saved: {out}")
            except Exception as e:
                err(str(e))
            pause()

        elif c == "10":
            profiles = _pkg.list_builtin_manifest_profiles()
            sep()
            print("  Built-in app bundles:")
            for i, name in enumerate(profiles, 1):
                try:
                    m = _pkg.get_builtin_manifest(name)
                    desc = m.get("description", "")
                    total = len(m.get("packages", []))
                    print(f"  {C}[{i}]{RST} {name:<10}  {total:>2} packages  {DIM}{desc}{RST}")
                except Exception:
                    print(f"  {C}[{i}]{RST} {name}")
            sep()

            pick = prompt("Bundle number [1]: ").strip() or "1"
            retries_raw = prompt("Retries per package [1]: ").strip()
            try:
                retries = int(retries_raw) if retries_raw else 1
            except ValueError:
                retries = 1

            try:
                profile_name = profiles[int(pick) - 1]
            except (ValueError, IndexError):
                err("Invalid bundle number.")
                pause()
                continue

            warn(f"Install built-in bundle '{profile_name}'?")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue

            try:
                manifest = _pkg.get_builtin_manifest(profile_name)
                result = _pkg.install_from_manifest(manifest, logger=logger, retries=max(0, retries))
                if result.get("ok"):
                    ok(
                        f"Bundle done: installed {result.get('installed', 0)} / {result.get('total', 0)}"
                        f" (optional skipped {result.get('skipped', 0)})."
                    )
                else:
                    err(
                        f"Bundle finished with failures: failed {result.get('failed', 0)} / {result.get('total', 0)}."
                    )

                failed_rows = [r for r in result.get("entries", []) if not r.get("ok") and not r.get("skipped")]
                if failed_rows:
                    sep("-")
                    print("  Failed packages:")
                    for row in failed_rows[:10]:
                        print(
                            f"    {R}•{RST} {row.get('name', row.get('id', 'unknown'))}  "
                            f"backend={row.get('backend', 'n/a')}  code={row.get('code', 'n/a')}"
                        )
            except Exception as e:
                err(str(e))
            pause()

        else:
            err(t("app.unknown_option"))


def _pick_backend(wg: bool, ch: bool) -> str | None:
    if wg and not ch:
        return "winget"
    if ch and not wg:
        return "choco"
    if wg and ch:
        print(f"  {C}[1]{RST} winget   {C}[2]{RST} Chocolatey")
        choice = prompt("Backend: ")
        return "winget" if choice == "1" else "choco" if choice == "2" else None
    return None


# ── 47. FILE ENCRYPTION ──────────────────────────────────────

def menu_fileencrypt(logger: CleanerLogger):
    from core import fileencrypt as _enc
    from core import archivecrack as _arc
    from core import pdfcrack as _pdf

    if not _enc.crypto_available():
        header(t("menu.file_encrypt"))
        err("The 'cryptography' library is not installed.")
        print(f"  {DIM}Run:  pip install cryptography>=41.0.0{RST}")
        pause()
        return

    _algo = _enc.DEFAULT_ALGO   # currently selected algorithm

    def _pick_algo() -> str:
        """Show algorithm picker and return chosen name."""
        avail = _enc.available_algos()
        sep()
        print(f"  Dostupné algoritmy:")
        for i, name in enumerate(avail, 1):
            marker = f" {G}◀ aktuální{RST}" if name == _algo else ""
            print(f"  {C}[{i}]{RST} {name}{marker}")
        ch = prompt("Algoritmus (Enter = ponechat): ").strip()
        if ch.isdigit() and 1 <= int(ch) <= len(avail):
            return avail[int(ch) - 1]
        return _algo

    while True:
        header(t("menu.file_encrypt"))
        avail_algos = _enc.available_algos()
        print(f"  {DIM}Algoritmus: {B}{_algo}{RST}  {DIM}· scrypt KDF · .scenc extension{RST}")
        sep()
        print(f"  {C}[1]{RST} Zašifrovat soubor")
        print(f"  {C}[2]{RST} Dešifrovat soubor     {DIM}(.scenc — auto-detekce algoritmu){RST}")
        print(f"  {C}[3]{RST} Zašifrovat složku     {DIM}(všechny soubory rekurzivně){RST}")
        print(f"  {C}[4]{RST} Dešifrovat složku     {DIM}(všechny .scenc soubory){RST}")
        sep("-")
        print(f"  {C}[5]{RST} Auto-crack souboru    {DIM}(časté hesla + wordlist + brute-force){RST}")
        print(f"  {C}[6]{RST} Změnit algoritmus     {DIM}(aktuálně: {_algo}){RST}")
        sep("-")
        print(f"  {C}[7]{RST} Crack archivu         {DIM}(7-Zip · WinRAR · ZIP — heslo){RST}")
        print(f"  {C}[8]{RST} Crack PDF             {DIM}(zaheslovaný PDF soubor){RST}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "1":
            path = prompt("Cesta k souboru: ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_file():
                err("Soubor nenalezen."); pause(); continue
            pw = _ask_password()
            if not pw:
                continue
            info(f"Šifruji pomocí {_algo}…")
            r = _enc.encrypt_file(p, pw, logger, algo=_algo)
            if r["ok"]:
                ok(f"Zašifrováno [{r['algo']}]: {r['dst']}")
            else:
                err(f"Chyba: {r['error']}")
            pause()

        elif c == "2":
            path = prompt("Zašifrovaný soubor (.scenc): ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_file():
                err("Soubor nenalezen."); pause(); continue
            pw = _ask_password(confirm=False)
            if not pw:
                continue
            info("Dešifruji…")
            r = _enc.decrypt_file(p, pw, logger)
            if r["ok"]:
                ok(f"Dešifrováno [{r['algo']}]: {r['dst']}")
            else:
                err(f"Chyba: {r['error']}")
            pause()

        elif c == "3":
            path = prompt("Cesta ke složce: ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_dir():
                err("Složka nenalezena."); pause(); continue
            pw = _ask_password()
            if not pw:
                continue
            warn(f"Zašifrovat VŠECHNY soubory v '{p.name}'? Originály zůstanou.")
            if prompt(t("prompt.type_yes")).upper() not in ("YES", "ANO"):
                continue
            info(f"Šifruji složku pomocí {_algo}…")
            r = _enc.encrypt_folder(p, pw, logger, algo=_algo)
            ok(f"Zašifrováno: {r['encrypted']}   Přeskočeno: {r['skipped']}   Chyby: {len(r['errors'])}")
            for e in r["errors"][:5]:
                err(f"  {e}")
            pause()

        elif c == "4":
            path = prompt("Cesta ke složce: ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_dir():
                err("Složka nenalezena."); pause(); continue
            pw = _ask_password(confirm=False)
            if not pw:
                continue
            info("Dešifruji složku…")
            r = _enc.decrypt_folder(p, pw, logger)
            ok(f"Dešifrováno: {r['decrypted']}   Selhalo: {r['failed']}")
            for e in r["errors"][:5]:
                err(f"  {e}")
            pause()

        elif c == "5":
            # ── Auto-crack ────────────────────────────────────────────────
            path = prompt("Soubor k prolomení (.scenc): ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_file():
                err("Soubor nenalezen."); pause(); continue

            sep()
            print(f"  {B}Auto-crack konfigurace{RST}")
            _wl_size = _enc._bundled_wordlist_size()
            print(f"  {DIM}Fáze 1 : {len(_enc._COMMON_PASSWORDS)} nejčastějších hesel{RST}")
            if _wl_size:
                print(f"  {DIM}Fáze 2 : {_wl_size:,} hesel z vestavěného wordlistu{RST}")
            print(f"  {DIM}Fáze 3 : brute-force (systematic/random){RST}")
            sep("-")

            wl_path = prompt("Vlastní wordlist soubor (Enter = přeskočit): ").strip().strip('"')
            wl = Path(wl_path) if wl_path and Path(wl_path).is_file() else None
            if wl_path and not wl:
                warn("Wordlist nenalezen — přeskakuji.")

            extra_raw = prompt("Vlastní hesla oddělená čárkou (Enter = přeskočit): ").strip()
            extras = [x.strip() for x in extra_raw.split(",") if x.strip()] if extra_raw else []

            print(f"\n  {DIM}Charset pro brute-force:{RST}")
            cs_opts = list(_enc._CHARSETS.keys())
            for i, cs in enumerate(cs_opts, 1):
                sample = _enc._CHARSETS[cs][:20]
                print(f"    {C}[{i}]{RST} {cs:<14} {DIM}({sample}…){RST}")
            cs_ch = prompt("Charset (Enter = alnum): ").strip()
            charset = cs_opts[int(cs_ch)-1] if cs_ch.isdigit() and 1 <= int(cs_ch) <= len(cs_opts) else "alnum"

            min_l_raw = prompt("Min délka hesla pro BF (Enter = 1): ").strip()
            max_l_raw = prompt("Max délka hesla pro BF (Enter = 4): ").strip()
            min_l = int(min_l_raw) if min_l_raw.isdigit() else 1
            max_l = int(max_l_raw) if max_l_raw.isdigit() else 4

            rand_raw = prompt("Max random pokusů (Enter = 50000): ").strip()
            max_rand = int(rand_raw) if rand_raw.isdigit() else 50_000

            print(f"\n  {DIM}BF mód:{RST}")
            print(f"    {C}[1]{RST} systematic  {DIM}(exhaustivní, zaručený do max délky){RST}")
            print(f"    {C}[2]{RST} random      {DIM}(pokrývá větší délky, náhodný výběr){RST}")
            print(f"    {C}[3]{RST} both        {DIM}(systematic + random){RST}")
            bf_ch = prompt("Mód (Enter = systematic): ").strip()
            bf_mode = {"1": "systematic", "2": "random", "3": "both"}.get(bf_ch, "systematic")

            sep()
            warn("scrypt KDF je záměrně pomalý — brute-force = ~1–5 pokusů/sec.")
            print(f"  {DIM}Enter = přerušit  |  progress live níže:{RST}\n")

            stop_ev = threading.Event()
            result_box: list = []

            def _crack_thread():
                def _cb(n, pw, speed, phase):
                    print(f"\r  {DIM}[{phase:<22}] [{n:>7}] {pw:<22}  {speed:.2f} p/s{RST}  ",
                          end="", flush=True)
                r = _enc.crack_file(
                    p,
                    wordlist_file=wl,
                    use_bundled_wordlist=True,
                    extra_passwords=extras,
                    bf_mode=bf_mode,
                    charset=charset,
                    min_len=min_l,
                    max_len=max_l,
                    max_random=max_rand,
                    progress_cb=_cb,
                    stop_event=stop_ev,
                )
                result_box.append(r)

            t_crack = threading.Thread(target=_crack_thread, daemon=True)
            t_crack.start()

            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            stop_ev.set()
            t_crack.join(timeout=5)

            print()
            sep("═")
            if result_box:
                r = result_box[0]
                elapsed = r.get("elapsed", 0)
                attempts = r.get("attempts", 0)
                if r["ok"]:
                    ok(f"HESLO NALEZENO!  '{r['password']}'  (algoritmus: {r['algo']})")
                    ok(f"Pokusy: {attempts}   Čas: {elapsed:.1f}s   "
                       f"Speed: {attempts/max(elapsed,0.001):.2f} p/s")
                    print(f"  {DIM}Nyní použij možnost [2] pro dešifrování s tímto heslem.{RST}")
                else:
                    warn(f"Heslo nenalezeno.  Pokusy: {attempts}   Čas: {elapsed:.1f}s")
                    print(f"  {DIM}Tip: zkus delší max délku, jiný charset nebo vlastní wordlist.{RST}")
            else:
                warn("Crack přerušen před prvním výsledkem.")
            pause()

        elif c == "6":
            _algo = _pick_algo()
            ok(f"Algoritmus nastaven na: {_algo}")
            pause()

        elif c == "7":
            # ── Archive crack (7-Zip / WinRAR / ZIP) ─────────────────────
            path = prompt("Archiv k prolomení (.7z / .rar / .zip): ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_file():
                err("Soubor nenalezen."); pause(); continue

            # show available backends
            tools = _arc.check_tools()
            sep()
            print(f"  {B}Dostupné nástroje:{RST}")
            print(f"  {DIM}7z binárka  : {tools['7z_binary'] or '✗ nenalezena'}{RST}")
            print(f"  {DIM}unrar       : {tools['unrar_binary'] or '✗ nenalezena'}{RST}")
            print(f"  {DIM}py7zr       : {tools['py7zr'] or '✗ nenainstalováno'}{RST}")
            print(f"  {DIM}rarfile     : {tools['rarfile'] or '✗ nenainstalováno'}{RST}")

            _wl_size = _enc._bundled_wordlist_size()
            sep("-")
            print(f"  {B}Crack konfigurace — archiv: {p.name}{RST}")
            if _wl_size:
                print(f"  {DIM}Vestavěný wordlist: {_wl_size:,} hesel{RST}")

            wl_path = prompt("Vlastní wordlist soubor (Enter = přeskočit): ").strip().strip('"')
            wl = Path(wl_path) if wl_path and Path(wl_path).is_file() else None
            if wl_path and not wl:
                warn("Wordlist nenalezen — přeskakuji.")

            extra_raw = prompt("Vlastní hesla oddělená čárkou (Enter = přeskočit): ").strip()
            extras = [x.strip() for x in extra_raw.split(",") if x.strip()] if extra_raw else []

            print(f"\n  {DIM}Charset pro brute-force:{RST}")
            cs_opts = list(_enc._CHARSETS.keys())
            for i, cs in enumerate(cs_opts, 1):
                sample = _enc._CHARSETS[cs][:20]
                print(f"    {C}[{i}]{RST} {cs:<14} {DIM}({sample}…){RST}")
            cs_ch = prompt("Charset (Enter = alnum): ").strip()
            charset = cs_opts[int(cs_ch)-1] if cs_ch.isdigit() and 1 <= int(cs_ch) <= len(cs_opts) else "alnum"

            min_l_raw = prompt("Min délka hesla pro BF (Enter = 1): ").strip()
            max_l_raw = prompt("Max délka hesla pro BF (Enter = 4): ").strip()
            min_l = int(min_l_raw) if min_l_raw.isdigit() else 1
            max_l = int(max_l_raw) if max_l_raw.isdigit() else 4

            rand_raw = prompt("Max random pokusů (Enter = 10000): ").strip()
            max_rand = int(rand_raw) if rand_raw.isdigit() else 10_000

            print(f"\n  {DIM}BF mód:{RST}")
            print(f"    {C}[1]{RST} systematic  {DIM}(exhaustivní, zaručený do max délky){RST}")
            print(f"    {C}[2]{RST} random      {DIM}(pokrývá větší délky, náhodný výběr){RST}")
            print(f"    {C}[3]{RST} both        {DIM}(systematic + random){RST}")
            bf_ch = prompt("Mód (Enter = systematic): ").strip()
            bf_mode = {"1": "systematic", "2": "random", "3": "both"}.get(bf_ch, "systematic")

            sep()
            warn(f"Archivní cracking je pomalý (~1–5 pokusů/sec pro .7z/.rar).")
            warn(f"ZIP (ZipCrypto) bývá rychlejší. Enter = přerušit.")
            print()

            stop_ev = threading.Event()
            result_box: list = []

            def _arc_crack_thread():
                def _cb(n, pw, speed, phase):
                    print(f"\r  {DIM}[{phase:<22}] [{n:>7}] {pw:<22}  {speed:.2f} p/s{RST}  ",
                          end="", flush=True)
                r = _arc.crack_archive(
                    p,
                    wordlist_file=wl,
                    use_bundled_wordlist=True,
                    extra_passwords=extras,
                    bf_mode=bf_mode,
                    charset=charset,
                    min_len=min_l,
                    max_len=max_l,
                    max_random=max_rand,
                    progress_cb=_cb,
                    stop_event=stop_ev,
                )
                result_box.append(r)

            t_arc = threading.Thread(target=_arc_crack_thread, daemon=True)
            t_arc.start()

            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            stop_ev.set()
            t_arc.join(timeout=5)

            print()
            sep("═")
            if result_box:
                r = result_box[0]
                elapsed = r.get("elapsed", 0)
                attempts = r.get("attempts", 0)
                backend = r.get("backend") or "?"
                if r["ok"]:
                    ok(f"HESLO NALEZENO!  '{r['password']}'  (formát: {r['archive_type']}  backend: {backend})")
                    ok(f"Pokusy: {attempts}   Čas: {elapsed:.1f}s   "
                       f"Speed: {attempts/max(elapsed,0.001):.2f} p/s")
                elif r.get("error") and "backend" not in r.get("error", "").lower() and "Unsupported" not in r.get("error", ""):
                    warn(f"Heslo nenalezeno.  Pokusy: {attempts}   Čas: {elapsed:.1f}s")
                    print(f"  {DIM}Tip: zkus delší max délku, jiný charset nebo vlastní wordlist.{RST}")
                else:
                    err(r.get("error", "Neznámá chyba"))
                    if p.suffix.lower() == ".7z":
                        print(f"  {DIM}Nainstaluj 7-Zip: brew install sevenzip  nebo: pip install py7zr{RST}")
                    elif p.suffix.lower() == ".rar":
                        print(f"  {DIM}Nainstaluj unrar: brew install rar  nebo: pip install rarfile{RST}")
            else:
                warn("Crack přerušen před prvním výsledkem.")
            pause()

        elif c == "8":
            # ── PDF crack ─────────────────────────────────────────────────
            if not _pdf.backend_available():
                err("Knihovna pypdf není nainstalována.")
                print(f"  {DIM}Spusť: pip install pypdf{RST}")
                pause(); continue

            path = prompt("PDF soubor: ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.is_file():
                err("Soubor nenalezen."); pause(); continue
            if not _pdf.is_encrypted(p):
                warn("Tento PDF není zaheslovaný."); pause(); continue

            sep()
            _wl_size = _enc._bundled_wordlist_size()
            print(f"  {B}PDF crack — {p.name}{RST}")
            if _wl_size:
                print(f"  {DIM}Vestavěný wordlist: {_wl_size:,} hesel{RST}")

            wl_path = prompt("Vlastní wordlist (Enter = přeskočit): ").strip().strip('"')
            wl = Path(wl_path) if wl_path and Path(wl_path).is_file() else None

            extra_raw = prompt("Vlastní hesla oddělená čárkou (Enter = přeskočit): ").strip()
            extras = [x.strip() for x in extra_raw.split(",") if x.strip()] if extra_raw else []

            print(f"\n  {DIM}Charset pro BF:{RST}")
            cs_opts = list(_enc._CHARSETS.keys())
            for i, cs in enumerate(cs_opts, 1):
                print(f"    {C}[{i}]{RST} {cs:<14} {DIM}({_enc._CHARSETS[cs][:20]}…){RST}")
            cs_ch = prompt("Charset (Enter = alnum): ").strip()
            charset = cs_opts[int(cs_ch)-1] if cs_ch.isdigit() and 1 <= int(cs_ch) <= len(cs_opts) else "alnum"

            min_l_raw = prompt("Min délka BF (Enter = 1): ").strip()
            max_l_raw = prompt("Max délka BF (Enter = 4): ").strip()
            min_l = int(min_l_raw) if min_l_raw.isdigit() else 1
            max_l = int(max_l_raw) if max_l_raw.isdigit() else 4

            sep()
            warn("Enter = přerušit  |  progress live níže:")
            print()

            stop_ev = threading.Event()
            result_box: list = []

            def _pdf_crack_thread():
                def _cb(n, pw, speed, phase):
                    print(f"\r  {DIM}[{phase:<22}] [{n:>7}] {pw:<22}  {speed:.2f} p/s{RST}  ",
                          end="", flush=True)
                r = _pdf.crack_pdf(
                    p, wordlist_file=wl, use_bundled_wordlist=True,
                    extra_passwords=extras, charset=charset,
                    min_len=min_l, max_len=max_l,
                    progress_cb=_cb, stop_event=stop_ev,
                )
                result_box.append(r)

            t_pdf = threading.Thread(target=_pdf_crack_thread, daemon=True)
            t_pdf.start()
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            stop_ev.set()
            t_pdf.join(timeout=5)

            print()
            sep("═")
            if result_box:
                r = result_box[0]
                elapsed = r.get("elapsed", 0)
                attempts = r.get("attempts", 0)
                if r["ok"]:
                    ok(f"HESLO NALEZENO!  '{r['password']}'")
                    ok(f"Pokusy: {attempts}   Čas: {elapsed:.1f}s   Speed: {attempts/max(elapsed,0.001):.2f} p/s")
                else:
                    warn(f"Heslo nenalezeno.  Pokusy: {attempts}   Čas: {elapsed:.1f}s")
            else:
                warn("Crack přerušen.")
            pause()

        else:
            err(t("app.unknown_option"))


def _ask_password(confirm: bool = True) -> str | None:
    import getpass
    try:
        pw = getpass.getpass("  Password: ")
        if not pw:
            err("Password cannot be empty.")
            return None
        if confirm:
            pw2 = getpass.getpass("  Confirm password: ")
            if pw != pw2:
                err("Passwords do not match.")
                return None
        return pw
    except (KeyboardInterrupt, EOFError):
        return None


# ── 48. DRIVER MANAGER ───────────────────────────────────────

def menu_drivermgr(logger: CleanerLogger):
    from core import drivermgr as _drv

    while True:
        header(t("menu.driver_mgr"))
        wmi_lbl = f"{G}available{RST}" if _drv.wmi_available() else f"{Y}not installed (pip install wmi){RST}"
        print(f"  WMI: {wmi_lbl}")
        sep()
        print(f"  {C}[1]{RST} List all PnP drivers  {DIM}(WMI){RST}")
        print(f"  {C}[2]{RST} Show unsigned drivers  {DIM}(WMI){RST}")
        print(f"  {C}[3]{RST} List kernel drivers    {DIM}(driverquery){RST}")
        print(f"  {C}[4]{RST} Open Device Manager")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "1":
            if not _drv.wmi_available():
                err("wmi library not installed."); pause(); continue
            info("Loading PnP drivers via WMI… (may take a moment)")
            drivers = _drv.get_pnp_drivers(logger)
            sep()
            if not drivers:
                warn("No PnP drivers found.")
            else:
                print(f"  {'#':>4}  {'Signed':<6}  {'Name':<35}  {'Version':<14}  {'Date':<12}  Class")
                sep("-")

                page_size = 30
                total = len(drivers)
                offset = 0
                while offset < total:
                    chunk = drivers[offset:offset + page_size]
                    for i, d in enumerate(chunk, offset + 1):
                        signed_lbl = f"{G}✓{RST}" if d["signed"] else f"{R}✗{RST}"
                        print(f"  {i:>4}  {signed_lbl}      {d['name'][:35]:<35}  "
                              f"{d['driver_version'][:14]:<14}  {d['driver_date']:<12}  {d['device_class']}")
                    offset += page_size
                    if offset < total:
                        sep()
                        more = prompt(f"  [{offset}/{total}] Press Enter for more, or 0 to stop: ")
                        if more == "0":
                            break
                print(f"\n  Total: {total} drivers")
            pause()

        elif c == "2":
            if not _drv.wmi_available():
                err("wmi library not installed."); pause(); continue
            info("Scanning for unsigned drivers…")
            drivers = _drv.get_unsigned_drivers(logger)
            sep()
            if not drivers:
                ok("No unsigned drivers found.")
            else:
                print(f"  {Y}Found {len(drivers)} unsigned driver(s):{RST}")
                sep("-")
                for d in drivers:
                    print(f"  {R}✗{RST}  {d['name'][:40]:<40}  {d['driver_version']:<14}  {d['inf_name']}")
            pause()

        elif c == "3":
            info("Running driverquery…")
            drivers = _drv.get_kernel_drivers(logger)
            sep()
            if not drivers:
                warn("No kernel drivers returned (driverquery may require elevation).")
            else:
                print(f"  {'#':>4}  {'State':<10}  {'Start':<10}  {'Name'}")
                sep("-")
                page_size = 30
                total = len(drivers)
                offset = 0
                while offset < total:
                    chunk = drivers[offset:offset + page_size]
                    for i, d in enumerate(chunk, offset + 1):
                        state_col = G if d["state"] == "Running" else DIM
                        print(f"  {i:>4}  {state_col}{d['state'][:10]:<10}{RST}  "
                              f"{d['start'][:10]:<10}  {d['name'][:45]}")
                    offset += page_size
                    if offset < total:
                        sep()
                        more = prompt(f"  [{offset}/{total}] Press Enter for more, or 0 to stop: ")
                        if more == "0":
                            break
                print(f"\n  Total: {total}")
            pause()

        elif c == "4":
            if _drv.open_device_manager():
                ok("Device Manager opened.")
            else:
                err("Failed to open Device Manager.")
            pause()

        else:
            err(t("app.unknown_option"))


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


# ── 50. HASH CRACKER ─────────────────────────────────────────

def menu_hashcrack(logger: CleanerLogger):
    from core import hashcrack as _hc
    from core import fileencrypt as _enc

    while True:
        header(t("menu.hash_crack"))
        sep()
        print(f"  {C}[1]{RST} Crack hash                {DIM}(MD5 · SHA1 · SHA256 · SHA512 · bcrypt){RST}")
        print(f"  {C}[2]{RST} Detekovat typ hashe       {DIM}(z délky / formátu){RST}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "2":
            h = prompt("Hash: ").strip()
            if not h:
                continue
            algo = _hc.detect_algo(h)
            if algo:
                ok(f"Detekovaný algoritmus: {B}{algo}{RST}")
            else:
                warn("Algoritmus nerozpoznán (neznámá délka nebo formát).")
            pause()

        elif c == "1":
            h = prompt("Hash k prolomení: ").strip()
            if not h:
                continue

            algo = _hc.detect_algo(h)
            if algo:
                info(f"Auto-detekce: {algo}")
            else:
                print(f"  {DIM}Dostupné: {', '.join(_hc.SUPPORTED)}{RST}")
                algo_in = prompt("Algoritmus (Enter = md5): ").strip().lower()
                algo = algo_in if algo_in in _hc.SUPPORTED else "md5"

            is_bcrypt = (algo == "bcrypt")
            if is_bcrypt:
                warn("bcrypt: ~100 ms / pokus — wordlist pouze, BF přeskočen.")

            sep("-")
            _wl_size = _enc._bundled_wordlist_size()
            if _wl_size:
                print(f"  {DIM}Vestavěný wordlist: {_wl_size:,} hesel{RST}")

            wl_path = prompt("Vlastní wordlist (Enter = přeskočit): ").strip().strip('"')
            wl = Path(wl_path) if wl_path and Path(wl_path).is_file() else None

            extra_raw = prompt("Vlastní hesla oddělená čárkou: ").strip()
            extras = [x.strip() for x in extra_raw.split(",") if x.strip()] if extra_raw else []

            if not is_bcrypt:
                print(f"\n  {DIM}Charset pro BF:{RST}")
                cs_opts = list(_enc._CHARSETS.keys())
                for i, cs in enumerate(cs_opts, 1):
                    print(f"    {C}[{i}]{RST} {cs:<14} {DIM}({_enc._CHARSETS[cs][:20]}…){RST}")
                cs_ch = prompt("Charset (Enter = alnum): ").strip()
                charset = cs_opts[int(cs_ch)-1] if cs_ch.isdigit() and 1 <= int(cs_ch) <= len(cs_opts) else "alnum"

                min_l_raw = prompt("Min délka BF (Enter = 1): ").strip()
                max_l_raw = prompt("Max délka BF (Enter = 6): ").strip()
                min_l = int(min_l_raw) if min_l_raw.isdigit() else 1
                max_l = int(max_l_raw) if max_l_raw.isdigit() else 6

                print(f"\n  {DIM}BF mód:{RST}")
                print(f"    {C}[1]{RST} systematic   {C}[2]{RST} random   {C}[3]{RST} both")
                bf_ch = prompt("Mód (Enter = systematic): ").strip()
                bf_mode = {"1": "systematic", "2": "random", "3": "both"}.get(bf_ch, "systematic")
            else:
                charset, min_l, max_l, bf_mode = "alnum", 1, 4, "none"

            sep()
            warn("MD5/SHA: miliony pokusů/sec.  bcrypt: ~10/sec.  Enter = přerušit.")
            print()

            stop_ev = threading.Event()
            result_box: list = []

            def _hc_thread():
                def _cb(n, pw, speed, phase):
                    print(f"\r  {DIM}[{phase:<22}] [{n:>8}] {pw:<22}  {speed:,.0f} p/s{RST}  ",
                          end="", flush=True)
                r = _hc.crack_hash(
                    h, algo=algo,
                    wordlist_file=wl, use_bundled_wordlist=True,
                    extra_passwords=extras,
                    bf_mode=bf_mode, charset=charset,
                    min_len=min_l, max_len=max_l,
                    progress_cb=_cb, stop_event=stop_ev,
                )
                result_box.append(r)

            t_hc = threading.Thread(target=_hc_thread, daemon=True)
            t_hc.start()
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            stop_ev.set()
            t_hc.join(timeout=3)

            print()
            sep("═")
            if result_box:
                r = result_box[0]
                elapsed = r.get("elapsed", 0)
                attempts = r.get("attempts", 0)
                if r["ok"]:
                    ok(f"HESLO NALEZENO!  '{r['password']}'  (algo: {r['algo']})")
                    ok(f"Pokusy: {attempts:,}   Čas: {elapsed:.1f}s   Speed: {attempts/max(elapsed,0.001):,.0f} p/s")
                else:
                    warn(f"Heslo nenalezeno.  Pokusy: {attempts:,}   Čas: {elapsed:.1f}s")
            else:
                warn("Přerušeno.")
            pause()

        else:
            err(t("app.unknown_option"))


# ── 51. PASSWORD GENERATOR ───────────────────────────────────

def menu_passgen(logger: CleanerLogger):
    from core import passgen as _pg

    while True:
        header(t("menu.pass_gen"))
        sep()
        print(f"  {C}[1]{RST} Generovat hesla")
        print(f"  {C}[2]{RST} Zkontrolovat sílu hesla")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "2":
            pw = prompt("Heslo k analýze: ").strip()
            if not pw:
                continue
            d = _pg.check_strength(pw)
            sep()
            print(f"  Délka        : {d['length']}")
            print(f"  Entropie     : {d['entropy_bits']} bits")
            print(f"  Síla         : {B}{d['strength']}{RST}  {d['bar']}")
            print(f"  Pool         : {d['charset_size']} znaků")
            parts = []
            if d["has_lower"]: parts.append("malá")
            if d["has_upper"]: parts.append("velká")
            if d["has_digit"]: parts.append("číslice")
            if d["has_sym"]:   parts.append("symboly")
            print(f"  Typy znaků   : {', '.join(parts) or '—'}")
            sep()
            pause()

        elif c == "1":
            print(f"\n  {DIM}Typy znaků:{RST}")
            cs_opts = list(_pg.CHARSETS.keys())
            for i, cs in enumerate(cs_opts, 1):
                sample = _pg.CHARSETS[cs][:24]
                print(f"    {C}[{i}]{RST} {cs:<14}  {DIM}{sample}{RST}")

            cs_ch = prompt("Charset (Enter = alnum+syms): ").strip()
            charset = cs_opts[int(cs_ch)-1] if cs_ch.isdigit() and 1 <= int(cs_ch) <= len(cs_opts) else "alnum+syms"

            len_raw  = prompt("Délka hesla (Enter = 16): ").strip()
            cnt_raw  = prompt("Počet hesel  (Enter = 5): ").strip()
            length   = int(len_raw)  if len_raw.isdigit()  else 16
            count    = int(cnt_raw)  if cnt_raw.isdigit()  else 5

            no_rep_ch = prompt("Bez opakování znaků? [y/N]: ").strip().lower()
            no_rep = no_rep_ch in ("y", "yes", "a", "ano")

            pron_ch = prompt("Vyslovitelná hesla? [y/N]: ").strip().lower()
            pron = pron_ch in ("y", "yes", "a", "ano")

            sep()
            try:
                passwords = _pg.generate(length=length, charset=charset,
                                         count=count, no_repeat=no_rep,
                                         pronounceable=pron)
            except ValueError as exc:
                err(str(exc)); pause(); continue

            for pw in passwords:
                d = _pg.check_strength(pw)
                bar = d["bar"]
                print(f"  {G}{pw}{RST}   {DIM}{d['entropy_bits']}b  {d['strength']}  {bar}{RST}")

            save_ch = prompt("\nUložit do souboru? (Enter = přeskočit): ").strip().strip('"')
            if save_ch:
                try:
                    Path(save_ch).write_text("\n".join(passwords) + "\n", encoding="utf-8")
                    ok(f"Uloženo: {save_ch}")
                except Exception as exc:
                    err(str(exc))
            pause()

        else:
            err(t("app.unknown_option"))


# ── 52. FILE INTEGRITY ───────────────────────────────────────

def menu_integrity(logger: CleanerLogger):
    from core import integrity as _intg

    _baseline_file = str(Path.home() / ".syscleaner_baseline.json")

    while True:
        header(t("menu.integrity"))
        meta = _intg.baseline_meta(_baseline_file)
        if meta:
            print(f"  {DIM}Baseline: {meta['file_count']} souborů · {meta['algo']} · {meta['created_at']}{RST}")
            print(f"  {DIM}Adresář : {meta['directory']}{RST}")
        else:
            print(f"  {DIM}Žádný baseline — vytvoř [1].{RST}")
        sep()
        print(f"  {C}[1]{RST} Vytvořit baseline     {DIM}(hashovat adresář){RST}")
        print(f"  {C}[2]{RST} Porovnat s baseline   {DIM}(zobrazit změny){RST}")
        print(f"  {C}[3]{RST} Vlastní cesta baseline")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "3":
            p = prompt(f"Cesta k baseline souboru [{_baseline_file}]: ").strip().strip('"')
            if p:
                _baseline_file = p
                ok(f"Nastaveno: {_baseline_file}")
            pause()

        elif c == "1":
            d = prompt("Adresář ke skenování: ").strip().strip('"')
            if not d or not Path(d).is_dir():
                err("Adresář nenalezen."); pause(); continue

            excl_raw = prompt("Vyloučit vzory (čárkou, Enter = nic): ").strip()
            excl = [x.strip() for x in excl_raw.split(",") if x.strip()]

            print(f"\n  {DIM}Algoritmus: md5 / sha256 / sha512{RST}")
            algo_in = prompt("Algo (Enter = sha256): ").strip().lower()
            algo = algo_in if algo_in in ("md5", "sha256", "sha512") else "sha256"

            sep()
            info(f"Hashování '{d}' pomocí {algo}…")

            cnt = [0]
            def _prog(n, rel):
                cnt[0] = n
                print(f"\r  {DIM}{n} souborů — {rel[-50:]}{RST}  ", end="", flush=True)

            r = _intg.create_baseline(d, _baseline_file, algo=algo,
                                       exclude_patterns=excl, progress_cb=_prog)
            print()
            sep("═")
            ok(f"Baseline uložen: {r['baseline_file']}")
            ok(f"Soubory: {r['hashed']:,}   Chyby: {r['errors']}   Algo: {r['algo']}")
            pause()

        elif c == "2":
            if not Path(_baseline_file).is_file():
                err("Baseline neexistuje. Nejdříve vytvoř [1]."); pause(); continue

            info("Porovnávám s baseline…")
            cnt = [0]
            def _prog2(n, rel):
                print(f"\r  {DIM}{n} souborů zkontrolováno…{RST}  ", end="", flush=True)

            try:
                r = _intg.check_baseline(_baseline_file, progress_cb=_prog2)
            except Exception as exc:
                print()
                err(f"Chyba: {exc}"); pause(); continue

            print()
            sep("═")
            if r["clean"]:
                ok("Žádné změny — integrita OK!")
            else:
                if r["added"]:
                    warn(f"NOVÉ soubory ({len(r['added'])}):")
                    for f in r["added"][:20]:
                        print(f"    {G}+{RST} {f}")
                    if len(r["added"]) > 20:
                        print(f"    {DIM}… a {len(r['added'])-20} dalších{RST}")
                if r["modified"]:
                    warn(f"ZMĚNĚNÉ soubory ({len(r['modified'])}):")
                    for f in r["modified"][:20]:
                        print(f"    {Y}~{RST} {f['path']}")
                    if len(r["modified"]) > 20:
                        print(f"    {DIM}… a {len(r['modified'])-20} dalších{RST}")
                if r["deleted"]:
                    warn(f"SMAZANÉ soubory ({len(r['deleted'])}):")
                    for f in r["deleted"][:20]:
                        print(f"    {R}−{RST} {f}")
                    if len(r["deleted"]) > 20:
                        print(f"    {DIM}… a {len(r['deleted'])-20} dalších{RST}")
            if r["errors"]:
                warn(f"Chyby čtení: {len(r['errors'])}")
            pause()

        else:
            err(t("app.unknown_option"))


# ── 53. NETWORK SCANNER ──────────────────────────────────────

def menu_netscanner(logger: CleanerLogger):
    from core import netscanner as _ns

    while True:
        header(t("menu.net_scan"))
        sep()
        print(f"  {C}[1]{RST} Port scan                {DIM}(top 100 portů){RST}")
        print(f"  {C}[2]{RST} Vlastní port scan        {DIM}(rozsah / seznam){RST}")
        print(f"  {C}[3]{RST} Ping sweep               {DIM}(celá podsíť .1–.254){RST}")
        print(f"  {C}[4]{RST} Banner grab              {DIM}(čtení service banneru){RST}")
        print(f"  {C}[5]{RST} Resolve / reverse DNS")
        print(f"  {C}[6]{RST} Traceroute               {DIM}(hop-by-hop cesta){RST}")
        print(f"  {C}[7]{RST} WHOIS lookup             {DIM}(registrant info){RST}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "1" or c == "2":
            host = prompt("Cíl (hostname / IP): ").strip()
            if not host:
                continue

            ip = _ns.resolve(host)
            if ip:
                info(f"Resolved: {ip}")
            else:
                warn("DNS lookup selhal — zkusím přímo.")

            if c == "1":
                ports = _ns.TOP_100_PORTS
                info(f"Skenuji {len(ports)} portů na {host}…")
            else:
                spec = prompt("Porty (např. 22,80,443,1000-2000): ").strip()
                ports = _ns.parse_port_range(spec)
                if not ports:
                    err("Žádné porty."); pause(); continue
                info(f"Skenuji {len(ports)} portů na {host}…")

            grab_ch = prompt("Banner grab pro otevřené porty? [y/N]: ").strip().lower()
            grab = grab_ch in ("y", "yes", "a", "ano")

            tout_raw = prompt("Timeout v sekundách (Enter = 0.5): ").strip()
            try:
                tout = float(tout_raw) if tout_raw else 0.5
            except ValueError:
                tout = 0.5

            done = [0]
            def _prog(scanned, total, port):
                pct = scanned * 100 // max(total, 1)
                print(f"\r  {DIM}[{pct:>3}%] {scanned}/{total}  port {port}{RST}  ", end="", flush=True)

            stop_ev = threading.Event()
            result_box: list = []

            def _scan_thread():
                result_box.append(
                    _ns.scan_ports(host, ports, timeout=tout,
                                   grab_banners=grab, progress_cb=_prog,
                                   stop_event=stop_ev)
                )

            t_sc = threading.Thread(target=_scan_thread, daemon=True)
            t_sc.start()
            try:
                t_sc.join()
            except KeyboardInterrupt:
                stop_ev.set()

            print()
            sep("═")
            open_ports = result_box[0] if result_box else []
            if not open_ports:
                info("Žádné otevřené porty nalezeny.")
            else:
                ok(f"Otevřené porty: {len(open_ports)}")
                for entry in open_ports:
                    svc  = f"  {DIM}({entry['service']}){RST}" if entry["service"] else ""
                    bnr  = f"  {DIM}{entry['banner'][:60]}{RST}" if entry.get("banner") else ""
                    print(f"    {G}{entry['port']:>5}{RST}{svc}{bnr}")
            logger.log("net_scan", "netscanner", f"host={host} open={len(open_ports)}")
            pause()

        elif c == "3":
            base = prompt("Základ IP (např. 192.168.1): ").strip()
            if not base:
                continue
            start_raw = prompt("Od (Enter = 1): ").strip()
            end_raw   = prompt("Do (Enter = 254): ").strip()
            start_i = int(start_raw) if start_raw.isdigit() else 1
            end_i   = int(end_raw)   if end_raw.isdigit()   else 254

            sep()
            info(f"Ping sweep {base}.{start_i}–{end_i}…")

            done = [0]
            total = end_i - start_i + 1
            def _pprog(scanned, tot, host_):
                pct = scanned * 100 // max(tot, 1)
                print(f"\r  {DIM}[{pct:>3}%] {host_}{RST}  ", end="", flush=True)

            stop_ev = threading.Event()
            result_box: list = []

            def _sweep_thread():
                result_box.append(
                    _ns.ping_sweep(base, start=start_i, end=end_i,
                                   progress_cb=_pprog, stop_event=stop_ev)
                )

            t_sw = threading.Thread(target=_sweep_thread, daemon=True)
            t_sw.start()
            try:
                t_sw.join()
            except KeyboardInterrupt:
                stop_ev.set()

            print()
            sep("═")
            alive = result_box[0] if result_box else []
            if not alive:
                info("Žádné aktivní hosty nalezeny.")
            else:
                ok(f"Aktivní hosty: {len(alive)}")
                for h in alive:
                    rdns = f"  {DIM}{h['rdns']}{RST}" if h.get("rdns") else ""
                    os_g = f"  {DIM}{h['os_guess']}{RST}" if h.get("os_guess") else ""
                    rtt  = f"  {h['rtt_ms']:.0f}ms" if h.get("rtt_ms") else ""
                    print(f"    {G}{h['host']:<18}{RST}{rtt}{rdns}{os_g}")
            pause()

        elif c == "4":
            host = prompt("Cíl: ").strip()
            port_raw = prompt("Port: ").strip()
            if not host or not port_raw.isdigit():
                continue
            port = int(port_raw)
            info(f"Čtu banner {host}:{port}…")
            banner = _ns.grab_banner(host, port)
            sep()
            if banner:
                ok(f"Banner ({len(banner)} znaků):")
                print(f"  {DIM}{banner}{RST}")
            else:
                warn("Žádný banner (spojení odmítnuto nebo timeout).")
            pause()

        elif c == "5":
            host = prompt("Hostname nebo IP: ").strip()
            if not host:
                continue
            sep()
            ip = _ns.resolve(host)
            if ip:
                print(f"  {G}→  IP  :{RST} {ip}")
                rdns = _ns._reverse(ip)
                if rdns:
                    print(f"  {G}→  rDNS:{RST} {rdns}")
            else:
                warn(f"DNS lookup selhal pro '{host}'.")
            pause()

        elif c == "6":
            host = prompt("Cíl (hostname / IP): ").strip()
            if not host:
                continue
            hops_raw = prompt("Max hopů (Enter = 30): ").strip()
            max_hops = int(hops_raw) if hops_raw.isdigit() else 30
            sep()
            info(f"Traceroute → {host}  (max {max_hops} hopů)…")
            hops = _ns.traceroute(host, max_hops=max_hops)
            sep("═")
            if hops and hops[0].get("error"):
                err(hops[0]["error"])
            else:
                for h in hops:
                    ip_str  = h["ip"] or "*"
                    rtt_str = f"{h['rtt_ms']:.1f} ms" if h["rtt_ms"] else "  *  "
                    dns_str = f"  {DIM}{h['rdns']}{RST}" if h.get("rdns") else ""
                    print(f"  {C}{h['hop']:>3}{RST}  {G}{ip_str:<18}{RST}  {rtt_str}{dns_str}")
            pause()

        elif c == "7":
            host = prompt("Doména nebo IP: ").strip()
            if not host:
                continue
            info(f"WHOIS pro {host}…")
            result = _ns.whois(host)
            sep("═")
            for line in result.splitlines()[:60]:
                print(f"  {DIM}{line}{RST}")
            if len(result.splitlines()) > 60:
                print(f"  {DIM}… ({len(result.splitlines())} řádků celkem){RST}")
            pause()

        else:
            err(t("app.unknown_option"))


# ── 54. MEMORY INSPECTOR ─────────────────────────────────────

def menu_memscanner(logger: CleanerLogger):
    from core import memscanner as _mem
    import platform

    while True:
        header(t("menu.mem_scan"))
        sep()
        print(f"  {C}[1]{RST} Zobrazit seznam procesů")
        print(f"  {C}[2]{RST} Inspekce procesu        {DIM}(env, cmdline, soubory, sítě){RST}")
        print(f"  {C}[3]{RST} Scan paměti pro stringy {DIM}(Linux/Windows hloubkový scan){RST}")
        print(f"  {C}[0]{RST} {t('menu.back')}")
        sep()
        c = prompt()

        if c == "0":
            break

        elif c == "1":
            info("Načítám procesy…")
            procs = _mem.list_processes()
            sep()
            print(f"  {'PID':>6}  {'Jméno':<28}  {'Status':<10}  {'Cmdline'}")
            print(f"  {DIM}{'-'*75}{RST}")
            flt = prompt("Filtr (Enter = vše): ").strip().lower()
            shown = [p for p in procs if not flt or flt in p["name"].lower() or flt in p["cmdline"].lower()]
            for p in shown[:60]:
                cmd = p["cmdline"][:35]
                print(f"  {C}{p['pid']:>6}{RST}  {p['name']:<28}  {DIM}{p['status']:<10}{RST}  {DIM}{cmd}{RST}")
            if len(shown) > 60:
                print(f"  {DIM}… a {len(shown)-60} dalších{RST}")
            pause()

        elif c == "2":
            pid_raw = prompt("PID nebo název procesu: ").strip()
            if not pid_raw:
                continue

            pid: int | None = None
            if pid_raw.isdigit():
                pid = int(pid_raw)
            else:
                procs = _mem.list_processes()
                matches = [p for p in procs if pid_raw.lower() in p["name"].lower()]
                if not matches:
                    err(f"Proces '{pid_raw}' nenalezen."); pause(); continue
                if len(matches) > 1:
                    for i, p in enumerate(matches[:10], 1):
                        print(f"  {C}[{i}]{RST} PID {p['pid']}  {p['name']}")
                    sel = prompt("Vyber číslo: ").strip()
                    if sel.isdigit() and 1 <= int(sel) <= len(matches):
                        pid = matches[int(sel)-1]["pid"]
                    else:
                        continue
                else:
                    pid = matches[0]["pid"]

            info(f"Inspekce PID {pid}…")
            d = _mem.inspect_process(pid)
            sep("═")
            print(f"  {B}PID:{RST} {d['pid']}  {B}Jméno:{RST} {d['name']}  {B}Status:{RST} {d['status']}")
            print(f"  {B}EXE:{RST} {d.get('exe','?')}")
            print(f"  {B}CWD:{RST} {d.get('cwd','?')}")
            print(f"  {B}CMD:{RST} {' '.join(d.get('cmdline',[]))[:100]}")
            if d.get("_error"):
                warn(d["_error"])

            if d.get("secrets_found"):
                sep("-")
                warn(f"Potenciální tajemství ({len(d['secrets_found'])}):")
                for s in d["secrets_found"]:
                    print(f"  {R}[{s['source']}]{RST} {Y}{s['key']}{RST} = {s['value'][:80]}")

            sep("-")
            env = d.get("env", {})
            if "_note" in env:
                print(f"  {DIM}ENV: {env['_note']}{RST}")
            else:
                print(f"  {B}ENV:{RST} {len(env)} proměnných")
                show_env = prompt("Zobrazit env proměnné? [y/N]: ").strip().lower()
                if show_env in ("y", "yes", "a", "ano"):
                    for k, v in list(env.items())[:40]:
                        print(f"    {DIM}{k}{RST}={v[:80]}")

            sep("-")
            files = d.get("open_files", [])
            print(f"  {B}Otevřené soubory:{RST} {len(files)}")
            for f in files[:15]:
                print(f"    {DIM}{f}{RST}")

            conns = d.get("connections", [])
            print(f"  {B}Síťová spojení:{RST} {len(conns)}")
            for conn in conns[:10]:
                print(f"    {DIM}{conn['local']}  →  {conn['remote']}  [{conn['status']}]{RST}")

            children = d.get("children", [])
            if children:
                print(f"  {B}Potomci:{RST} {len(children)}")
                for ch in children:
                    print(f"    {DIM}PID {ch['pid']}  {ch['name']}{RST}")

            logger.log("mem_inspect", "memscanner", f"pid={pid} name={d.get('name','?')}")
            pause()

        elif c == "3":
            plat = platform.system()
            if plat not in ("Linux", "Windows"):
                warn(f"Hloubkový scan paměti není podporován na {plat}.")
                info("Použij [2] pro env/cmdline secrets.")
                pause(); continue

            pid_raw = prompt("PID: ").strip()
            if not pid_raw.isdigit():
                continue
            pid = int(pid_raw)

            kw = prompt("Klíčové slovo pro filtrování stringů (Enter = vše): ").strip()
            min_l_raw = prompt("Min délka stringu (Enter = 6): ").strip()
            max_s_raw = prompt("Max počet stringů (Enter = 500): ").strip()
            min_l = int(min_l_raw) if min_l_raw.isdigit() else 6
            max_s = int(max_s_raw) if max_s_raw.isdigit() else 500

            sep()
            info(f"Scanuji paměť PID {pid}…")
            done_box: list = [0]
            def _mprog(regions, strings):
                print(f"\r  {DIM}Regiony: {regions}   Stringy: {strings}{RST}  ", end="", flush=True)

            r = _mem.scan_memory_strings(pid, keyword=kw, min_len=min_l,
                                          max_strings=max_s, progress_cb=_mprog)
            print()
            sep("═")
            if r.get("error"):
                err(r["error"])
            else:
                ok(f"Nalezeno {r['count']} stringů  (metoda: {r['method']})")
                for s in r["strings"][:100]:
                    print(f"  {DIM}{s[:100]}{RST}")
                if r["count"] > 100:
                    print(f"  {DIM}… a {r['count']-100} dalších{RST}")
                save_ch = prompt("\nUložit do souboru? (Enter = přeskočit): ").strip().strip('"')
                if save_ch:
                    try:
                        Path(save_ch).write_text("\n".join(r["strings"]), encoding="utf-8")
                        ok(f"Uloženo: {save_ch}")
                    except Exception as exc:
                        err(str(exc))
            pause()

        else:
            err(t("app.unknown_option"))


# ──────────────────────────────────────────────────────────────
def menu_stego(logger):
    from core import stego as _stego
    while True:
        clr(); hdr(t("menu.stego"))
        print(f"  {C}[1]{RST} Skrýt data v obrázku")
        print(f"  {C}[2]{RST} Extrahovat data z obrázku")
        print(f"  {C}[3]{RST} Zjistit kapacitu obrázku")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            cover = prompt("Zdrojový obrázek (PNG/BMP): ").strip().strip('"')
            if not cover:
                continue
            data_src = prompt("Soubor s daty ke skrytí: ").strip().strip('"')
            if not data_src:
                continue
            out = prompt("Výstupní obrázek [auto]: ").strip().strip('"')
            if not out:
                from pathlib import Path as _P
                out = str(_P(cover).stem) + "_stego.png"
            pw = prompt("Heslo (Enter = bez hesla): ").strip()
            try:
                data_bytes = open(data_src, "rb").read()
                cap = _stego.capacity(cover)
                if len(data_bytes) > cap:
                    err(f"Data příliš velká ({len(data_bytes)} B > kapacita {cap} B)")
                    pause(); continue
                _stego.hide(cover, data_bytes, out, password=pw or None)
                ok(f"Data skryta → {out}")
                logger.log("stego_hide", "stego", f"cover={cover} data={data_src} out={out}")
            except Exception as exc:
                err(str(exc))
            pause()
        elif ch == "2":
            src = prompt("Steganografický obrázek: ").strip().strip('"')
            if not src:
                continue
            pw = prompt("Heslo (Enter = bez hesla): ").strip()
            save_to = prompt("Uložit extrahovaná data do souboru (Enter = zobrazit): ").strip().strip('"')
            try:
                data_bytes = _stego.extract(src, password=pw or None)
                if save_to:
                    open(save_to, "wb").write(data_bytes)
                    ok(f"Extrahováno {len(data_bytes)} B → {save_to}")
                else:
                    try:
                        txt = data_bytes.decode("utf-8")
                        sep()
                        print(txt[:2000])
                        if len(txt) > 2000:
                            print(f"  {DIM}… zkráceno{RST}")
                    except UnicodeDecodeError:
                        ok(f"Extrahováno {len(data_bytes)} B (binární data)")
                logger.log("stego_extract", "stego", f"src={src}")
            except Exception as exc:
                err(str(exc))
            pause()
        elif ch == "3":
            src = prompt("Obrázek: ").strip().strip('"')
            if not src:
                continue
            try:
                cap = _stego.capacity(src)
                ok(f"Kapacita: {cap} B  ({cap/1024:.1f} KB)")
            except Exception as exc:
                err(str(exc))
            pause()


def menu_metastrip(logger):
    from core import metastrip as _meta
    while True:
        clr(); hdr(t("menu.metastrip"))
        print(f"  {C}[1]{RST} Přečíst metadata souboru")
        print(f"  {C}[2]{RST} Odstranit metadata ze souboru")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            src = prompt("Soubor (JPG/PNG/DOCX/PDF): ").strip().strip('"')
            if not src:
                continue
            try:
                meta = _meta.read_meta(src)
                sep()
                if not meta:
                    info("Žádná metadata nenalezena.")
                else:
                    for k, v in meta.items():
                        print(f"  {C}{k}{RST}: {v}")
            except Exception as exc:
                err(str(exc))
            pause()
        elif ch == "2":
            src = prompt("Zdrojový soubor: ").strip().strip('"')
            if not src:
                continue
            dst = prompt("Výstupní soubor [auto]: ").strip().strip('"')
            if not dst:
                from pathlib import Path as _P
                p = _P(src)
                dst = str(p.parent / (p.stem + "_clean" + p.suffix))
            try:
                _meta.strip(src, dst)
                ok(f"Metadata odstraněna → {dst}")
                logger.log("meta_strip", "metastrip", f"src={src} dst={dst}")
            except Exception as exc:
                err(str(exc))
            pause()


def menu_hibp(logger):
    from core import hibp as _hibp
    while True:
        clr(); hdr(t("menu.hibp"))
        print(f"  {C}[1]{RST} Zkontrolovat heslo (k-anonymita, bez API klíče)")
        print(f"  {C}[2]{RST} Zkontrolovat e-mail (vyžaduje HIBP API klíč)")
        print(f"  {C}[3]{RST} Zkontrolovat více hesel najednou")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            pw = prompt("Heslo: ").strip()
            if not pw:
                continue
            info("Kontroluji…")
            r = _hibp.check_password(pw)
            sep()
            if r.get("error"):
                err(r["error"])
            elif r["pwned"]:
                print(f"  {R}KOMPROMITOVÁNO! Nalezeno {r['count']}× v databázi úniků.{RST}")
            else:
                ok("Heslo NEBYLO nalezeno v databázi úniků.")
            logger.log("hibp_pw", "hibp", f"pwned={r.get('pwned')}")
            pause()
        elif ch == "2":
            email = prompt("E-mail: ").strip()
            api_key = prompt("HIBP API klíč: ").strip()
            if not email or not api_key:
                continue
            info("Kontroluji breaches…")
            breaches = _hibp.check_email_breaches(email, api_key)
            sep()
            if isinstance(breaches, dict) and breaches.get("error"):
                err(breaches["error"])
            elif not breaches:
                ok("E-mail nebyl nalezen v žádném úniku.")
            else:
                print(f"  {R}Nalezeno v {len(breaches)} únicích:{RST}")
                for b in breaches:
                    print(f"    {DIM}{b.get('Name','?')} ({b.get('BreachDate','?')}){RST}")
            logger.log("hibp_email", "hibp", f"email={email}")
            pause()
        elif ch == "3":
            raw = prompt("Hesla oddělená čárkou: ").strip()
            if not raw:
                continue
            pws = [p.strip() for p in raw.split(",") if p.strip()]
            info(f"Kontroluji {len(pws)} hesel…")
            results = _hibp.check_multiple_passwords(pws)
            sep()
            for pw2, r in results.items():
                if r.get("error"):
                    print(f"  {Y}{pw2}{RST}: chyba – {r['error']}")
                elif r["pwned"]:
                    print(f"  {R}{pw2}{RST}: KOMPROMITOVÁNO ({r['count']}×)")
                else:
                    print(f"  {G}{pw2}{RST}: OK")
            pause()


def menu_sslcheck(logger):
    from core import sslcheck as _ssl
    while True:
        clr(); hdr(t("menu.sslcheck"))
        print(f"  {C}[1]{RST} Zkontrolovat SSL/TLS certifikát")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            host = prompt("Hostname (např. example.com): ").strip()
            if not host:
                continue
            port_s = prompt("Port [443]: ").strip()
            port = int(port_s) if port_s.isdigit() else 443
            info(f"Kontroluji {host}:{port}…")
            r = _ssl.check(host, port)
            sep()
            for line in _ssl.format_report(r):
                print(f"  {line}")
            logger.log("ssl_check", "sslcheck", f"host={host}:{port} valid={r.get('valid')}")
            pause()


def menu_totp(logger):
    from core import totp as _totp
    vault: _totp.TOTPVault | None = None

    def _ensure_vault():
        nonlocal vault
        if vault and vault._unlocked:
            return True
        vf = prompt("Soubor TOTP trezoru [totp_vault.enc]: ").strip().strip('"') or "totp_vault.enc"
        pw = prompt("Heslo trezoru: ").strip()
        v = _totp.TOTPVault(vf)
        if not v.load(pw):
            v.init(pw)
            ok("Nový trezor vytvořen.")
        vault = v
        return True

    while True:
        clr(); hdr(t("menu.totp"))
        print(f"  {C}[1]{RST} Otevřít / vytvořit trezor")
        print(f"  {C}[2]{RST} Přidat TOTP záznam")
        print(f"  {C}[3]{RST} Zobrazit kódy (live)")
        print(f"  {C}[4]{RST} Smazat záznam")
        print(f"  {C}[5]{RST} Vygenerovat nové tajemství")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            _ensure_vault()
            if vault:
                entries = vault.list_entries()
                ok(f"Trezor odemčen, {len(entries)} záznamů.")
            pause()
        elif ch == "2":
            if not _ensure_vault():
                continue
            name = prompt("Název (např. GitHub): ").strip()
            secret = prompt("Base32 tajemství: ").strip()
            issuer = prompt("Vydavatel (volitelné): ").strip()
            if not name or not secret:
                continue
            try:
                vault.add(name, secret, issuer=issuer or "")
                ok(f"Přidán: {name}")
                logger.log("totp_add", "totp", f"name={name}")
            except Exception as exc:
                err(str(exc))
            pause()
        elif ch == "3":
            if not _ensure_vault():
                continue
            import time as _time
            info("Zobrazuji kódy (Ctrl+C pro ukončení)…")
            sep()
            try:
                while True:
                    codes = vault.get_all_codes()
                    rem = _totp.remaining_seconds()
                    lines = [f"  {C}{e['name']}{RST}  {G}{e['code']}{RST}  [{rem}s]" for e in codes]
                    print("\033[H\033[J", end="")
                    hdr(t("menu.totp"))
                    for l in lines:
                        print(l)
                    print(f"\n  {DIM}Ctrl+C pro ukončení{RST}")
                    _time.sleep(1)
            except KeyboardInterrupt:
                pass
            pause()
        elif ch == "4":
            if not _ensure_vault():
                continue
            entries = vault.list_entries()
            for i, e in enumerate(entries):
                print(f"  {C}[{i}]{RST} {e['name']} ({e.get('issuer','')})")
            idx_s = prompt("Index záznamu ke smazání: ").strip()
            if idx_s.isdigit() and int(idx_s) < len(entries):
                vault.delete(entries[int(idx_s)]["id"])
                ok("Smazáno.")
                logger.log("totp_delete", "totp", f"name={entries[int(idx_s)]['name']}")
            else:
                err("Neplatný index.")
            pause()
        elif ch == "5":
            secret = _totp.generate_secret()
            ok(f"Nové tajemství: {G}{secret}{RST}")
            pause()


def menu_fileanalyze(logger):
    from core import fileanalyzer as _fa
    while True:
        clr(); hdr(t("menu.fileanalyze"))
        print(f"  {C}[1]{RST} Analyzovat soubor")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            src = prompt("Soubor: ").strip().strip('"')
            if not src:
                continue
            info("Analyzuji…")
            try:
                r = _fa.analyze(src)
                sep("═")
                print(f"  Cesta:       {r['path']}")
                print(f"  Velikost:    {r['size_bytes']} B")
                print(f"  Typ (magic): {r['type_magic']}")
                print(f"  Typ (ext):   {r['type_ext']}")
                if r.get("extension_mismatch"):
                    print(f"  {Y}⚠ Neshoda přípony!{RST}")
                print(f"  Entropie:    {r['entropy']:.2f} b/B  ({r['entropy_label']})")
                if r.get("pe"):
                    pe = r["pe"]
                    print(f"  PE arch:     {pe.get('machine','?')} | {pe.get('type','?')}")
                if r.get("elf"):
                    elf = r["elf"]
                    print(f"  ELF:         {elf.get('bits','?')}-bit {elf.get('endian','?')} | {elf.get('type','?')}")
                sep()
                strings = r.get("strings", [])
                if strings:
                    print(f"  Stringy ({len(strings)}):")
                    for s in strings[:30]:
                        print(f"    {DIM}{s[:100]}{RST}")
                    if len(strings) > 30:
                        print(f"    {DIM}… a {len(strings)-30} dalších{RST}")
                logger.log("file_analyze", "fileanalyze", f"src={src} type={r['type_magic']}")
            except Exception as exc:
                err(str(exc))
            pause()


def menu_loganalyze(logger):
    from core import loganalyzer as _log
    while True:
        clr(); hdr(t("menu.loganalyze"))
        print(f"  {C}[1]{RST} Analyzovat systémové logy")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            hours_s = prompt("Kolik hodin zpět [24]: ").strip()
            hours = int(hours_s) if hours_s.isdigit() else 24
            info(f"Sbírám logy za posledních {hours} hodin…")
            try:
                r = _log.analyze(hours=hours)
                sep("═")
                for line in _log.summary_lines(r):
                    print(f"  {line}")
                sep()
                save_ch = prompt("Uložit výsledky? (Enter = přeskočit): ").strip().strip('"')
                if save_ch:
                    import json as _json
                    open(save_ch, "w", encoding="utf-8").write(_json.dumps(r, indent=2, default=str))
                    ok(f"Uloženo: {save_ch}")
                logger.log("log_analyze", "loganalyze", f"hours={hours} events={r.get('total',0)}")
            except Exception as exc:
                err(str(exc))
            pause()


def menu_pwdmgr(logger):
    from core import pwdmgr as _pm
    vault: _pm.PasswordVault | None = None

    def _open_vault():
        nonlocal vault
        vf = prompt("Soubor trezoru [passwords.enc]: ").strip().strip('"') or "passwords.enc"
        pw = prompt("Hlavní heslo: ").strip()
        v = _pm.PasswordVault(vf)
        if not v.load(pw):
            if prompt("Trezor neexistuje. Vytvořit? [a/n]: ").strip().lower() in ("a", "y", "ano", "yes"):
                v.init(pw)
                ok("Trezor vytvořen.")
            else:
                return False
        vault = v
        return True

    while True:
        clr(); hdr(t("menu.pwdmgr"))
        unlocked = vault is not None and vault._unlocked
        if unlocked:
            print(f"  {G}Trezor odemčen{RST}")
        print(f"  {C}[1]{RST} Otevřít trezor")
        print(f"  {C}[2]{RST} Přidat heslo")
        print(f"  {C}[3]{RST} Hledat / zobrazit")
        print(f"  {C}[4]{RST} Upravit záznam")
        print(f"  {C}[5]{RST} Smazat záznam")
        print(f"  {C}[6]{RST} Exportovat (plaintext)")
        print(f"  {C}[7]{RST} Změnit hlavní heslo")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            _open_vault()
            pause()
        elif ch == "2":
            if not unlocked and not _open_vault():
                continue
            name = prompt("Název: ").strip()
            user = prompt("Uživatel: ").strip()
            pw2 = prompt("Heslo: ").strip()
            url = prompt("URL (volitelné): ").strip()
            notes = prompt("Poznámky (volitelné): ").strip()
            if not name:
                continue
            try:
                vault.add(name, user, pw2, url=url, notes=notes)
                ok(f"Přidán: {name}")
                logger.log("pwdmgr_add", "pwdmgr", f"name={name}")
            except Exception as exc:
                err(str(exc))
            pause()
        elif ch == "3":
            if not unlocked and not _open_vault():
                continue
            q = prompt("Hledat (Enter = vše): ").strip()
            entries = vault.search(q) if q else vault.list_entries()
            sep()
            for e in entries:
                print(f"  {C}[{e['id']}]{RST} {e['name']}  {DIM}{e.get('username','')}  {e.get('url','')}{RST}")
            if entries:
                show_id = prompt("ID záznamu k zobrazení (Enter = přeskočit): ").strip()
                if show_id.isdigit():
                    entry = vault.get(int(show_id))
                    if entry:
                        sep()
                        for k, v in entry.items():
                            print(f"  {C}{k}{RST}: {v}")
            pause()
        elif ch == "4":
            if not unlocked and not _open_vault():
                continue
            eid = prompt("ID záznamu: ").strip()
            if not eid.isdigit():
                continue
            entry = vault.get(int(eid))
            if not entry:
                err("Nenalezeno."); pause(); continue
            print(f"  Úprava: {entry['name']} (Enter = ponechat)")
            kw_upd = {}
            for field in ("name", "username", "password", "url", "notes"):
                val = prompt(f"  {field} [{entry.get(field,'')}]: ").strip()
                if val:
                    kw_upd[field] = val
            if kw_upd:
                vault.update(int(eid), **kw_upd)
                ok("Aktualizováno.")
                logger.log("pwdmgr_update", "pwdmgr", f"id={eid}")
            pause()
        elif ch == "5":
            if not unlocked and not _open_vault():
                continue
            eid = prompt("ID záznamu ke smazání: ").strip()
            if eid.isdigit():
                vault.delete(int(eid))
                ok("Smazáno.")
                logger.log("pwdmgr_delete", "pwdmgr", f"id={eid}")
            pause()
        elif ch == "6":
            if not unlocked and not _open_vault():
                continue
            out = prompt("Výstupní soubor: ").strip().strip('"')
            if not out:
                continue
            try:
                vault.export_plaintext(out)
                ok(f"Exportováno → {out}")
                logger.log("pwdmgr_export", "pwdmgr", f"out={out}")
            except Exception as exc:
                err(str(exc))
            pause()
        elif ch == "7":
            if not unlocked and not _open_vault():
                continue
            old_pw = prompt("Stávající heslo: ").strip()
            new_pw = prompt("Nové heslo: ").strip()
            new_pw2 = prompt("Nové heslo (potvrzení): ").strip()
            if new_pw != new_pw2:
                err("Hesla se neshodují."); pause(); continue
            try:
                vault.change_master(old_pw, new_pw)
                ok("Hlavní heslo změněno.")
                logger.log("pwdmgr_chpw", "pwdmgr", "master password changed")
            except Exception as exc:
                err(str(exc))
            pause()


def menu_backup(logger):
    from core import backup as _bk
    while True:
        clr(); hdr(t("menu.backup"))
        print(f"  {C}[1]{RST} Vytvořit zálohu (zašifrovat)")
        print(f"  {C}[2]{RST} Obnovit zálohu (dešifrovat)")
        print(f"  {C}[3]{RST} Zobrazit dostupné zálohy")
        print(f"  {C}[4]{RST} Smazat zálohu")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            srcs_raw = prompt("Zdrojové soubory/složky (oddělené čárkou): ").strip()
            if not srcs_raw:
                continue
            srcs = [s.strip().strip('"') for s in srcs_raw.split(",") if s.strip()]
            dest = prompt("Cílová složka pro zálohy [backups/]: ").strip().strip('"') or "backups/"
            pw = prompt("Heslo zálohy: ").strip()
            if not pw:
                err("Heslo je povinné."); pause(); continue
            algo_ch = prompt("Algoritmus [1=AES-256-GCM, 2=ChaCha20, 3=AES-256-CBC] [1]: ").strip()
            algo_map = {"1": "AES-256-GCM", "2": "ChaCha20-Poly1305", "3": "AES-256-CBC"}
            algo = algo_map.get(algo_ch, "AES-256-GCM")
            info("Zálohování…")
            def _bprog(done, total, name):
                print(f"\r  {DIM}[{done}/{total}] {name[:50]}{RST}  ", end="", flush=True)
            r = _bk.create(srcs, dest, pw, algo=algo, progress_cb=_bprog, logger=logger)
            print()
            sep("═")
            if r["ok"]:
                ok(f"Záloha vytvořena: {r['backup_dir']}")
                print(f"  Zašifrováno: {r['encrypted']} souborů")
                if r["failed"]:
                    print(f"  {Y}Chyby: {r['failed']}{RST}")
            else:
                err("Záloha selhala.")
            pause()
        elif ch == "2":
            bdir = prompt("Složka zálohy: ").strip().strip('"')
            if not bdir:
                continue
            dest = prompt("Cíl obnovy: ").strip().strip('"')
            if not dest:
                continue
            pw = prompt("Heslo zálohy: ").strip()
            verify_ch = prompt("Ověřit integritu SHA-256? [a/n]: ").strip().lower()
            verify = verify_ch in ("a", "y", "ano", "yes", "")
            info("Obnovuji…")
            def _rprog(done, total, name):
                print(f"\r  {DIM}[{done}/{total}] {name[:50]}{RST}  ", end="", flush=True)
            r = _bk.restore(bdir, dest, pw, verify=verify, progress_cb=_rprog, logger=logger)
            print()
            sep("═")
            if r["ok"]:
                ok(f"Obnoveno {r['restored']} souborů → {r['dest']}")
                if r.get("hash_mismatch"):
                    print(f"  {Y}Neshoda hash ({len(r['hash_mismatch'])} souborů):{RST}")
                    for f in r["hash_mismatch"][:5]:
                        print(f"    {DIM}{f}{RST}")
            else:
                err(f"Obnova selhala: {r.get('error','?')}")
                for e in r.get("errors", [])[:5]:
                    print(f"    {DIM}{e}{RST}")
            pause()
        elif ch == "3":
            dest = prompt("Složka se zálohami [backups/]: ").strip().strip('"') or "backups/"
            backups = _bk.list_backups(dest)
            sep()
            if not backups:
                info("Žádné zálohy nenalezeny.")
            else:
                for b in backups:
                    print(f"  {C}{b['ts']}{RST}  {b['files']} souborů  {b['size_mb']} MB  ({b['algo']})")
                    print(f"    {DIM}{b['dir']}{RST}")
            pause()
        elif ch == "4":
            bdir = prompt("Složka zálohy ke smazání: ").strip().strip('"')
            if not bdir:
                continue
            confirm = prompt(f"Opravdu smazat {bdir}? [ano/n]: ").strip().lower()
            if confirm in ("ano", "yes", "a", "y"):
                r = _bk.delete_backup(bdir)
                if r["ok"]:
                    ok("Záloha smazána.")
                    logger.log("backup_delete", "backup", f"dir={bdir}")
                else:
                    err(r.get("error", "?"))
            pause()


def menu_startupaudit(logger):
    from core import startupaudit as _sa
    import threading

    _RISK_COLOR = {0: G, 1: Y, 2: Y, 3: R}
    _RISK_LABEL = {0: 'OK', 1: 'LOW', 2: 'MED', 3: 'HIGH'}

    def _print_entry(e, i: int):
        rc = _RISK_COLOR[e['risk']]
        rl = _RISK_LABEL[e['risk']]
        flags = ', '.join(e['flags']) if e['flags'] else ''
        enabled = '' if e['enabled'] else f'  {DIM}[disabled]{RST}'
        flag_str = f'  {Y}{flags}{RST}' if flags else ''
        print(f"  {DIM}[{i:>3}]{RST} {rc}[{rl}]{RST}  {C}{e['source']}{RST}  {e['name']}")
        print(f"         {DIM}{e['command'][:90]}{RST}{enabled}{flag_str}")

    while True:
        clr(); hdr(t("menu.startupaudit"))
        print(f"  {C}[1]{RST} Spustit scan")
        print(f"  {C}[2]{RST} Spustit scan + zobrazit jen rizikové")
        print(f"  {C}[3]{RST} Export výsledků do souboru")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break

        if ch in ("1", "2", "3"):
            info("Skenuji startup / persistence lokace…")
            entries = _sa.scan()
            sm = _sa.summary(entries)
            sep("═")
            print(f"  Celkem: {sm['total']}  "
                  f"{R}HIGH:{sm['high']}{RST}  "
                  f"{Y}MED:{sm['medium']}  LOW:{sm['low']}{RST}  "
                  f"{G}OK:{sm['ok']}{RST}")
            sep()

            if ch == "2":
                shown = [e for e in entries if e['risk'] >= 2]
                if not shown:
                    ok("Žádné středně ani vysoce rizikové položky nenalezeny.")
                else:
                    for i, e in enumerate(shown):
                        _print_entry(e, i)
            elif ch == "3":
                out = prompt("Výstupní soubor (Enter = startup_report.txt): ").strip().strip('"') or "startup_report.txt"
                lines = []
                for e in entries:
                    rl = _RISK_LABEL[e['risk']]
                    flags = ', '.join(e['flags']) if e['flags'] else 'none'
                    en = 'enabled' if e['enabled'] else 'disabled'
                    lines.append(f"[{rl}] {e['source']} | {e['name']} | {en}")
                    lines.append(f"      CMD: {e['command']}")
                    lines.append(f"      FLAGS: {flags}")
                    lines.append("")
                try:
                    Path(out).write_text("\n".join(lines), encoding="utf-8")
                    ok(f"Export uložen: {out}")
                    logger.log("startup_audit_export", "startupaudit", f"out={out} total={sm['total']}")
                except Exception as exc:
                    err(str(exc))
            else:
                for i, e in enumerate(entries):
                    _print_entry(e, i)

            logger.log("startup_audit", "startupaudit",
                       f"total={sm['total']} high={sm['high']} medium={sm['medium']}")
            pause()


def menu_sys_dashboard(logger):
    from core import sysmonitor as _sm
    import time as _time
    info("Načítám dashboard… (Ctrl+C pro ukončení)")
    try:
        prev_net = None
        while True:
            s = _sm.snapshot()
            clr()
            hdr(t("menu.sys_dashboard"))

            # CPU
            cpu_bar = "█" * int(s["cpu_percent"] / 5) + "░" * (20 - int(s["cpu_percent"] / 5))
            freq = f"  {s['cpu_freq_mhz']} MHz" if s["cpu_freq_mhz"] else ""
            print(f"  {C}CPU{RST}  [{cpu_bar}] {s['cpu_percent']:5.1f}%{freq}  ({s['cpu_count']} jader)")

            # Per-core
            cores = s["cpu_per_core"]
            core_line = "  " + "  ".join(
                f"{G if c < 70 else Y if c < 90 else R}{c:3.0f}%{RST}" for c in cores
            )
            print(core_line)

            # RAM
            mem_bar = "█" * int(s["mem_percent"] / 5) + "░" * (20 - int(s["mem_percent"] / 5))
            print(f"  {C}RAM{RST}  [{mem_bar}] {s['mem_percent']:5.1f}%  "
                  f"{_sm.fmt_bytes(s['mem_used'])} / {_sm.fmt_bytes(s['mem_total'])}")
            if s["swap_percent"] > 0:
                print(f"  {C}SWP{RST}  {s['swap_percent']:.1f}%  {_sm.fmt_bytes(s['swap_used'])}")

            # Disks
            sep()
            for d in s["disks"]:
                disk_bar = "█" * int(d["percent"] / 5) + "░" * (20 - int(d["percent"] / 5))
                col = G if d["percent"] < 70 else Y if d["percent"] < 90 else R
                print(f"  {C}{d['mount']:<12}{RST} [{col}{disk_bar}{RST}] {d['percent']:5.1f}%  "
                      f"{_sm.fmt_bytes(d['free'])} volných")

            # Network
            sep()
            if prev_net:
                sent_s = (s["net_sent"] - prev_net[0])
                recv_s = (s["net_recv"] - prev_net[1])
                print(f"  {C}NET{RST}  ↑ {_sm.fmt_bytes(sent_s)}/s   ↓ {_sm.fmt_bytes(recv_s)}/s")
            else:
                print(f"  {C}NET{RST}  ↑ {_sm.fmt_bytes(s['net_sent'])} sent   ↓ {_sm.fmt_bytes(s['net_recv'])} recv")
            prev_net = (s["net_sent"], s["net_recv"])

            print(f"\n  {DIM}Uptime: {_sm.fmt_uptime(s['uptime_s'])}   Ctrl+C = zpět{RST}")
            _time.sleep(1)
    except KeyboardInterrupt:
        pass


def menu_port_monitor(logger):
    from core import sysmonitor as _sm
    import time as _time

    while True:
        clr(); hdr(t("menu.port_monitor"))
        print(f"  {C}[1]{RST} Zobrazit všechna spojení")
        print(f"  {C}[2]{RST} Pouze LISTEN porty")
        print(f"  {C}[3]{RST} Live refresh (Ctrl+C = stop)")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch in ("1", "2"):
            conns = _sm.list_ports()
            if ch == "2":
                conns = [c for c in conns if c["status"] == "LISTEN"]
            sep()
            if not conns:
                info("Žádná spojení nenalezena.")
            else:
                print(f"  {DIM}{'PROTO':<5} {'LOCAL':<25} {'REMOTE':<25} {'STATUS':<12} {'PID':<6} PROCESS{RST}")
                sep("-")
                for c in conns:
                    sc = G if c["status"] == "LISTEN" else C if c["status"] == "ESTABLISHED" else DIM
                    print(f"  {c['proto']:<5} {c['local']:<25} {c['remote']:<25} "
                          f"{sc}{c['status']:<12}{RST} {c['pid']:<6} {c['process']}")
            pause()
        elif ch == "3":
            info("Live monitor portů… (Ctrl+C = stop)")
            try:
                while True:
                    conns = [c for c in _sm.list_ports() if c["status"] == "LISTEN"]
                    clr(); hdr(t("menu.port_monitor"))
                    print(f"  {DIM}{'PORT':<25} {'PID':<6} PROCESS{RST}")
                    sep("-")
                    for c in conns:
                        print(f"  {G}{c['local']:<25}{RST} {c['pid']:<6} {c['process']}")
                    print(f"\n  {DIM}Ctrl+C = zpět{RST}")
                    _time.sleep(2)
            except KeyboardInterrupt:
                pass


def menu_temp_monitor(logger):
    from core import sysmonitor as _sm
    import time as _time

    while True:
        clr(); hdr(t("menu.temp_monitor"))
        print(f"  {C}[1]{RST} Zobrazit teploty")
        print(f"  {C}[2]{RST} Live monitor (Ctrl+C = stop)")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break

        def _show_temps():
            temps = _sm.temperatures()
            if not temps:
                print(f"  {Y}Teploty nejsou dostupné na tomto systému.{RST}")
                print(f"  {DIM}(macOS vyžaduje root, nebo nainstalujte osx-cpu-temp){RST}")
                return
            for sensor, entries in temps.items():
                print(f"  {C}{sensor}{RST}")
                for e in entries:
                    t_val = e["current"]
                    col = G if t_val < 60 else Y if t_val < 80 else R
                    hi = f"  high={e['high']}°" if e["high"] else ""
                    crit = f"  crit={e['critical']}°" if e["critical"] else ""
                    bar = "█" * int(t_val / 5) + "░" * (20 - min(20, int(t_val / 5)))
                    print(f"    {e['label']:<20} [{col}{bar}{RST}] {col}{t_val:.1f}°C{RST}{hi}{crit}")

        if ch == "1":
            sep()
            _show_temps()
            pause()
        elif ch == "2":
            try:
                while True:
                    clr(); hdr(t("menu.temp_monitor"))
                    sep()
                    _show_temps()
                    print(f"\n  {DIM}Ctrl+C = zpět{RST}")
                    _time.sleep(2)
            except KeyboardInterrupt:
                pass


def menu_battery_info(logger):
    from core import sysmonitor as _sm

    clr(); hdr(t("menu.battery_info"))
    b = _sm.battery()
    sep()
    if b is None:
        info("Baterie nebyla nalezena (desktop nebo nepodporovaný systém).")
    else:
        pct = b["percent"]
        col = G if pct > 50 else Y if pct > 20 else R
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  Nabití:   [{col}{bar}{RST}] {col}{pct}%{RST}")
        status = f"{G}Nabíjí se{RST}" if b["plugged"] else f"{Y}Na baterii{RST}"
        print(f"  Stav:     {status}")
        if b["secs_left"] is not None and not b["plugged"]:
            h, m = divmod(int(b["secs_left"]) // 60, 60)
            print(f"  Zbývá:    {h}h {m:02d}m")
    pause()


def menu_disk_analyzer(logger):
    from core import diskanalyzer as _da

    while True:
        clr(); hdr(t("menu.disk_analyzer"))
        print(f"  {C}[1]{RST} Analyzovat složku")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break
        elif ch == "1":
            root = prompt("Složka [.]: ").strip().strip('"') or "."
            top_s = prompt("Top N položek [20]: ").strip()
            top_n = int(top_s) if top_s.isdigit() else 20
            info(f"Analyzuji {root}…")
            scanned_box = [0]
            def _prog(n, path):
                scanned_box[0] = n
                print(f"\r  {DIM}Prošlo souborů: {n}  {path[-50:]}{RST}  ", end="", flush=True)
            try:
                r = _da.analyze(root, top_n=top_n, progress_cb=_prog)
                print()
                sep("═")
                print(f"  Celkem:  {_da.fmt_size(r['total_bytes'])}  ({r['file_count']} souborů)")

                sep()
                print(f"  {C}TOP SLOŽKY{RST}")
                total = r["total_bytes"] or 1
                for path, sz in r["top_folders"][:top_n]:
                    pct = sz / total * 100
                    bar = _da.bar(pct, 15)
                    print(f"  {bar} {pct:5.1f}%  {_da.fmt_size(sz):>10}  {DIM}{path}{RST}")

                sep()
                print(f"  {C}TOP SOUBORY{RST}")
                for sz, path in r["top_files"][:top_n]:
                    pct = sz / total * 100
                    print(f"  {pct:5.1f}%  {_da.fmt_size(sz):>10}  {DIM}{path}{RST}")

                sep()
                print(f"  {C}PODLE PŘÍPONY{RST}")
                for ext, sz in r["ext_breakdown"][:15]:
                    pct = sz / total * 100
                    bar = _da.bar(pct, 15)
                    print(f"  {bar} {pct:5.1f}%  {_da.fmt_size(sz):>10}  {ext}")

                logger.log("disk_analyze", "diskanalyzer", f"root={root} total={_da.fmt_size(r['total_bytes'])}")
            except Exception as exc:
                err(str(exc))
            pause()


def menu_cam_audit(logger):
    from core import camaudit as _cam

    clr(); hdr(t("menu.cam_audit"))
    info("Kontroluji přístupy ke kameře a mikrofonu…")
    try:
        result = _cam.audit()
        sep("═")

        for device_name, key in [("KAMERA", "camera"), ("MIKROFON", "microphone")]:
            entries = result.get(key, [])
            print(f"\n  {C}{device_name}{RST}  ({len(entries)} záznamů)")
            if not entries:
                print(f"    {DIM}Žádné záznamy nenalezeny.{RST}")
            else:
                for e in entries:
                    col = G if e.get("allowed") else R
                    status = "POVOLEN" if e.get("allowed") else "ZAMÍTNUT"
                    pid_str = f"  PID {e['pid']}" if "pid" in e else ""
                    device_str = f"  {e['device']}" if "device" in e else ""
                    print(f"    {col}[{status}]{RST}  {e['app']}{pid_str}{device_str}")

        import platform as _pl
        if _pl.system() == "Darwin":
            print(f"\n  {DIM}Poznámka: plný přístup k TCC databázi může vyžadovat spuštění jako root.{RST}")

        logger.log("cam_audit", "camaudit", f"camera={len(result.get('camera',[]))} mic={len(result.get('microphone',[]))}")
    except Exception as exc:
        err(str(exc))
    pause()


def menu_code_fmt(logger):
    from core import codeformatter as _cf

    while True:
        clr(); hdr(t("menu.code_fmt"))
        print(f"  {C}[1]{RST} Formátovat soubor (auto-detect)")
        print(f"  {C}[2]{RST} Formátovat JSON")
        print(f"  {C}[3]{RST} Formátovat XML")
        print(f"  {C}[4]{RST} Formátovat YAML")
        print(f"  {C}[5]{RST} Formátovat vstup z klávesnice")
        print(f"  {C}[0]{RST} {t('app.back')}")
        ch = prompt(t("app.choice")).strip()
        if ch == "0":
            break

        def _do_fmt(text: str, mode: str = "auto", src_name: str = ""):
            if mode == "auto":
                out, detected, errs = _cf.fmt_auto(text)
            elif mode == "json":
                out, errs = _cf.fmt_json(text)
                detected = "json"
            elif mode == "xml":
                out, errs = _cf.fmt_xml(text)
                detected = "xml"
            else:
                out, errs = _cf.fmt_yaml(text)
                detected = "yaml"
            sep()
            if errs:
                for e2 in errs:
                    err(e2)
            else:
                ok(f"Formát: {detected.upper()}")
                save_to = prompt("Uložit do souboru (Enter = zobrazit): ").strip().strip('"')
                if save_to:
                    try:
                        open(save_to, "w", encoding="utf-8").write(out)
                        ok(f"Uloženo → {save_to}")
                    except Exception as exc2:
                        err(str(exc2))
                else:
                    print()
                    for line in out.splitlines()[:80]:
                        print(f"  {line}")
                    if out.count("\n") > 80:
                        print(f"  {DIM}… zkráceno{RST}")
            logger.log("code_fmt", "codeformatter", f"fmt={detected} src={src_name}")
            pause()

        mode_map = {"1": "auto", "2": "json", "3": "xml", "4": "yaml"}

        if ch in ("1", "2", "3", "4"):
            src = prompt("Soubor: ").strip().strip('"')
            if not src:
                continue
            try:
                text = open(src, encoding="utf-8", errors="replace").read()
                _do_fmt(text, mode_map[ch], src)
            except Exception as exc:
                err(str(exc)); pause()
        elif ch == "5":
            print(f"  {DIM}Vlož text, ukonči prázdným řádkem:{RST}")
            lines = []
            while True:
                try:
                    ln = input()
                    if ln == "":
                        break
                    lines.append(ln)
                except (EOFError, KeyboardInterrupt):
                    break
            if lines:
                _do_fmt("\n".join(lines), "auto", "<stdin>")


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
