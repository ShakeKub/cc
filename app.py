"""System Cleaner - pure terminal interface."""

import os
import queue as _queue
import sys
import threading
from pathlib import Path

from core.logger import CleanerLogger

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
        input(f"\n  {DIM}Press Enter to continue...{RST}")
    except (KeyboardInterrupt, EOFError):
        pass


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

MENU = [
    ("1",  "System Scan"),
    ("2",  "Quick Clean"),
    ("3",  "Standard Clean"),
    ("4",  "Deep Clean"),
    ("5",  "Browser Tools"),
    ("6",  "Process Manager"),
    ("7",  "Network Tools"),
    ("8",  "Startup Manager"),
    ("9",  "Disk Tools"),
    ("10", "Registry Cleaner"),
    ("11", "Optimizer"),
    ("12", "Privacy & Security"),
    ("13", "App Tracer"),
    ("14", "Uninstaller"),
    ("15", "Scheduler"),
    ("16", "Logs & Reports"),
    ("0",  "Exit"),
]


def main_menu(logger: CleanerLogger):
    import psutil
    while True:
        header()

        # quick stats line
        try:
            cpu = psutil.cpu_percent(interval=0)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
            print(f"  CPU {cpu:.0f}%  |  RAM {ram.percent:.0f}% ({fmt_bytes(ram.used)}/{fmt_bytes(ram.total)})  |  Disk free {fmt_bytes(disk.free)}")
        except Exception:
            pass

        admin_tag = f"{G}[ADMIN]{RST}" if is_admin() else f"{Y}[no admin]{RST}"
        print(f"  {admin_tag}")
        sep()

        # two-column menu
        left  = MENU[:len(MENU)//2 + 1]
        right = MENU[len(MENU)//2 + 1:]
        for i in range(max(len(left), len(right))):
            l = f"  [{left[i][0]:>2}] {left[i][1]:<22}" if i < len(left) else " " * 32
            r = f"[{right[i][0]:>2}] {right[i][1]}" if i < len(right) else ""
            print(f"{C}{l}{RST}{C}{r}{RST}")

        sep()
        choice = prompt()

        if choice == "0" or choice in ("q", "exit", "quit"):
            clr()
            print(f"\n  {G}Bye.{RST}\n")
            logger.export_json()
            sys.exit(0)
        elif choice == "1":  menu_scan(logger)
        elif choice == "2":  menu_clean(logger, "quick")
        elif choice == "3":  menu_clean(logger, "standard")
        elif choice == "4":  menu_clean(logger, "deep")
        elif choice == "5":  menu_browser(logger)
        elif choice == "6":  menu_process(logger)
        elif choice == "7":  menu_network(logger)
        elif choice == "8":  menu_startup(logger)
        elif choice == "9":  menu_disk(logger)
        elif choice == "10": menu_registry(logger)
        elif choice == "11": menu_optimizer(logger)
        elif choice == "12": menu_privacy(logger)
        elif choice == "13": menu_tracer(logger)
        elif choice == "14": menu_uninstaller(logger)
        elif choice == "15": menu_scheduler(logger)
        elif choice == "16": menu_logs(logger)
        else:
            err("Unknown option.")
            pause()


# ── 1. SCAN ─────────────────────────────────────────────────

def menu_scan(logger: CleanerLogger):
    header("System Scan")
    info("Scanning system, please wait...")
    try:
        from core.cleaner import scan_all
        results = scan_all(logger)
        sep()
        ok(f"Temp files : {results.get('temp_files', 0)}  ({fmt_bytes(results.get('temp_size', 0))})")
        for cat, d in results.get("categories", {}).items():
            print(f"    {cat:<30} {d.get('count',0):>5} items   {fmt_bytes(d.get('size',0)):>10}")
        sep()
        ok(f"Total cleanable: {fmt_bytes(results.get('temp_size', 0))}")
    except Exception as e:
        err(f"Scan failed: {e}")
    pause()


# ── 2/3/4. CLEAN ────────────────────────────────────────────

def menu_clean(logger: CleanerLogger, profile: str):
    header(f"{profile.capitalize()} Clean")
    warn(f"This will remove junk files using the '{profile}' profile.")
    confirm = prompt("Type YES to confirm: ")
    if confirm.upper() != "YES":
        info("Cancelled.")
        pause()
        return
    info("Cleaning...")
    try:
        from core.cleaner import clean_all
        import json
        cfg_path = Path(__file__).parent / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        p = cfg.get("cleaning_profiles", {}).get(profile)
        results = clean_all(logger, p)
        freed = results.get("total_freed", 0)
        sep()
        ok(f"Done! Freed: {fmt_bytes(freed)}")
        for name, size in results.get("actions", []):
            display = fmt_bytes(size) if size else "done"
            print(f"    {name:<35} {display}")
    except Exception as e:
        err(f"Clean failed: {e}")
    pause()


# ── 5. BROWSER ──────────────────────────────────────────────

def menu_browser(logger: CleanerLogger):
    while True:
        header("Browser Tools")
        print(f"  {C}[1]{RST} Detect browsers")
        print(f"  {C}[2]{RST} Clean cache")
        print(f"  {C}[3]{RST} Clean cookies")
        print(f"  {C}[4]{RST} Clean all")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            try:
                from core.browser import detect_installed_browsers
                browsers = detect_installed_browsers()
                sep()
                if not browsers:
                    warn("No browsers detected.")
                for b in browsers:
                    ok(f"{b['display_name']:<20} profiles: {b['profiles']}  cache: {fmt_bytes(b['cache_size'])}")
            except Exception as e:
                err(str(e))
            pause()
        elif c in ("2", "3", "4"):
            mode = {"2": "cache", "3": "cookies", "4": "all"}[c]
            warn(f"Will clean {mode} for all browsers.")
            if prompt("Type YES: ").upper() == "YES":
                try:
                    from core.browser import clean_all_browsers
                    kwargs = {mode: True} if mode != "all" else {"cache": True, "cookies": True, "history": True}
                    results = clean_all_browsers(logger, **kwargs)
                    total = sum(sum(v.values()) for v in results.values())
                    ok(f"Freed: {fmt_bytes(total)}")
                except Exception as e:
                    err(str(e))
            else:
                info("Cancelled.")
            pause()


# ── 6. PROCESS ──────────────────────────────────────────────

def menu_process(logger: CleanerLogger):
    while True:
        header("Process Manager")
        info("Loading processes...")
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
            print(f"  Total: {len(procs)} processes")
        except Exception as e:
            err(str(e))
            pause()
            break

        print(f"\n  {C}[k]{RST} Kill PID   {C}[r]{RST} Refresh   {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "r": continue
        elif c == "k":
            pid_str = prompt("Enter PID to kill: ")
            try:
                from core.process import kill_process
                pid = int(pid_str)
                warn(f"Kill PID {pid}?")
                if prompt("Type YES: ").upper() == "YES":
                    success = kill_process(pid, logger)
                    ok(f"Process {pid} terminated.") if success else err("Failed.")
            except ValueError:
                err("Invalid PID.")
            pause()


# ── 7. NETWORK ──────────────────────────────────────────────

def menu_network(logger: CleanerLogger):
    while True:
        header("Network Tools")
        print(f"  {C}[1]{RST} Show connections & IP info")
        print(f"  {C}[2]{RST} Flush DNS")
        print(f"  {C}[3]{RST} Ping a host")
        print(f"  {C}[4]{RST} Run diagnostics")
        print(f"  {C}[0]{RST} Back")
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
                ok("DNS cache flushed.") if success else err("Flush failed.")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "3":
            host = prompt("Host to ping: ")
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
                for t in results:
                    sym = f"{G}PASS{RST}" if t["status"] == "pass" else f"{R}FAIL{RST}"
                    print(f"  [{sym}] {t['test']:<30} {t.get('detail','')}")
            except Exception as e:
                err(str(e))
            pause()


# ── 8. STARTUP ──────────────────────────────────────────────

def menu_startup(logger: CleanerLogger):
    while True:
        header("Startup Manager")
        info("Loading startup entries...")
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
            status = f"{G}Enabled{RST}" if e.get("enabled") else f"{R}Disabled{RST}"
            impact = e.get("impact", "medium")
            icolor = G if impact == "low" else Y if impact == "medium" else R
            flag = f" {R}[SUS]{RST}" if e.get("suspicious") else ""
            print(f"  {i+1:>3}  {e['name']:<30}  {status:<10}  {icolor}{impact:<8}{RST}  {e.get('type','')}{flag}")
        sep()
        print(f"  Total: {len(entries)}")
        print(f"\n  {C}[e #]{RST} Enable   {C}[d #]{RST} Disable   {C}[x #]{RST} Remove   {C}[0]{RST} Back")
        sep()
        cmd = prompt()
        if cmd == "0": break
        parts = cmd.split()
        if len(parts) == 2 and parts[0] in ("e","d","x"):
            try:
                idx = int(parts[1]) - 1
                entry = entries[idx]
                if parts[0] == "e":
                    from core.startup import enable_startup_entry
                    ok(f"Enabled: {entry['name']}") if enable_startup_entry(entry, logger) else err("Failed.")
                elif parts[0] == "d":
                    from core.startup import disable_startup_entry
                    ok(f"Disabled: {entry['name']}") if disable_startup_entry(entry, logger) else err("Failed.")
                elif parts[0] == "x":
                    warn(f"Remove '{entry['name']}'?")
                    if prompt("Type YES: ").upper() == "YES":
                        from core.startup import remove_startup_entry
                        ok("Removed.") if remove_startup_entry(entry, logger) else err("Failed.")
            except (ValueError, IndexError):
                err("Invalid number.")
            pause()


# ── 9. DISK ─────────────────────────────────────────────────

def menu_disk(logger: CleanerLogger):
    while True:
        header("Disk Tools")
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
        print(f"  {C}[1]{RST} Find large files (>100MB)")
        print(f"  {C}[2]{RST} Find duplicate files")
        print(f"  {C}[3]{RST} Find empty folders")
        print(f"  {C}[4]{RST} Analyze directory")
        print(f"  {C}[5]{RST} Secure shred a file")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            info("Searching for large files...")
            try:
                from core.disk import find_large_files
                files = find_large_files(root, min_size_mb=100, logger=logger)
                sep()
                for i, f in enumerate(files[:20]):
                    print(f"  {i+1:>3}. {f['name']:<35} {fmt_bytes(f['size']):>10}  {str(Path(f['path']).parent)[:40]}")
                ok(f"Found {len(files)} files > 100 MB")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            path = prompt(f"Directory to scan [{root}]: ") or root
            info("Scanning for duplicates (may take a while)...")
            try:
                from core.disk import find_duplicate_files
                dupes = find_duplicate_files(path, logger=logger)
                sep()
                ok(f"Found {len(dupes)} duplicate groups")
                for i, group in enumerate(dupes[:10]):
                    print(f"  Group {i+1}:")
                    for f in group:
                        print(f"    {f}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "3":
            path = prompt(f"Directory [{root}]: ") or root
            try:
                from core.disk import find_empty_folders
                empties = find_empty_folders(path, logger)
                sep()
                for f in empties[:20]:
                    print(f"  {f}")
                ok(f"Found {len(empties)} empty folders")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "4":
            path = prompt(f"Directory [{root}]: ") or root
            info("Analyzing...")
            try:
                from core.disk import analyze_directory
                results = analyze_directory(path, max_depth=2, logger=logger)
                sep()
                for entry in results[:20]:
                    print(f"  {fmt_bytes(entry.get('size',0)):>10}  {entry.get('path','')}")
                ok(f"{len(results)} directories analyzed")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "5":
            path = prompt("File path to shred: ")
            if path:
                warn(f"PERMANENTLY destroy '{path}'? This cannot be undone!")
                if prompt("Type YES: ").upper() == "YES":
                    try:
                        from core.disk import secure_shred
                        ok("File shredded.") if secure_shred(path, passes=3, logger=logger) else err("Failed.")
                    except Exception as e:
                        err(str(e))
                else:
                    info("Cancelled.")
            pause()


# ── 10. REGISTRY ────────────────────────────────────────────

def menu_registry(logger: CleanerLogger):
    while True:
        header("Registry Cleaner")
        print(f"  {C}[1]{RST} Scan for invalid entries")
        print(f"  {C}[2]{RST} Fix all invalid entries")
        print(f"  {C}[3]{RST} Backup registry")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            info("Scanning registry...")
            try:
                from core.registry import scan_invalid_entries
                entries = scan_invalid_entries(logger)
                sep()
                print(f"  {'#':>3}  {'Category':<20}  {'Entry':<30}  {'Issue':<30}  Risk")
                sep("-")
                for i, e in enumerate(entries[:30]):
                    risk = e.get("risk","low")
                    rc = G if risk=="low" else Y if risk=="medium" else R
                    print(f"  {i+1:>3}  {e.get('category',''):<20}  {e.get('value_name','')[:30]:<30}  {e.get('issue','')[:30]:<30}  {rc}{risk}{RST}")
                ok(f"Found {len(entries)} invalid entries")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            warn("Fix all invalid registry entries?")
            if prompt("Type YES: ").upper() == "YES":
                try:
                    from core.registry import scan_invalid_entries, fix_invalid_entries
                    entries = scan_invalid_entries(logger)
                    fixed = fix_invalid_entries(entries, logger)
                    ok(f"Fixed {fixed} entries.")
                except Exception as e:
                    err(str(e))
            pause()
        elif c == "3":
            try:
                from core.registry import backup_registry
                path = backup_registry(logger)
                ok(f"Backup saved: {path}")
            except Exception as e:
                err(str(e))
            pause()


# ── 11. OPTIMIZER ───────────────────────────────────────────

def menu_optimizer(logger: CleanerLogger):
    while True:
        header("Optimizer")
        print(f"  {C}[1]{RST} Optimize RAM")
        print(f"  {C}[2]{RST} Show optimizable services")
        print(f"  {C}[3]{RST} Disable a service")
        print(f"  {C}[4]{RST} Enable a service")
        print(f"  {C}[5]{RST} Show power plans")
        print(f"  {C}[6]{RST} Switch power plan")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()
        if c == "0": break
        elif c == "1":
            info("Optimizing RAM...")
            try:
                from core.optimizer import optimize_ram
                result = optimize_ram(logger)
                ok(f"Freed: {fmt_bytes(result.get('freed',0))}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            try:
                from core.optimizer import get_optimizable_services
                svcs = get_optimizable_services(logger)
                sep()
                print(f"  {'#':>3}  {'Service':<35}  {'Status':<10}  {'Impact':<8}  Category")
                sep("-")
                for i, s in enumerate(svcs):
                    sc = G if s["status"]=="running" else R
                    ic = G if s["impact"]=="low" else Y if s["impact"]=="medium" else R
                    print(f"  {i+1:>3}  {s['display_name'][:35]:<35}  {sc}{s['status']:<10}{RST}  {ic}{s['impact']:<8}{RST}  {s.get('category','')}")
                ok(f"Found {len(svcs)} services")
            except Exception as e:
                err(str(e))
            pause()
        elif c in ("3","4"):
            action = "disable" if c=="3" else "enable"
            name = prompt(f"Service name to {action}: ")
            if name:
                try:
                    from core.optimizer import disable_service, enable_service
                    fn = disable_service if c=="3" else enable_service
                    ok(f"Service {action}d.") if fn(name, logger) else err("Failed.")
                except Exception as e:
                    err(str(e))
            pause()
        elif c == "5":
            try:
                from core.optimizer import get_power_plans
                plans = get_power_plans(logger)
                sep()
                for p in plans:
                    active = f" {G}<-- ACTIVE{RST}" if p.get("active") else ""
                    print(f"  {p.get('name','Unknown')}{active}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "6":
            plan = prompt("Plan name (Balanced / High performance / Power saver): ")
            if plan:
                try:
                    from core.optimizer import switch_power_plan
                    ok("Switched.") if switch_power_plan(plan, logger) else err("Failed.")
                except Exception as e:
                    err(str(e))
            pause()


# ── 12. PRIVACY ─────────────────────────────────────────────

def menu_privacy(logger: CleanerLogger):
    while True:
        header("Privacy & Security")
        print(f"  {C}[1]{RST} Scan telemetry settings")
        print(f"  {C}[2]{RST} Toggle telemetry")
        print(f"  {C}[3]{RST} Scan tracking files")
        print(f"  {C}[4]{RST} Clean tracking files")
        print(f"  {C}[0]{RST} Back")
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
                for t in telemetry:
                    s = f"{R}ON{RST}" if t["enabled"] else f"{G}OFF{RST}"
                    print(f"  {t['name']:<35}  {s:<10}  {t['description']}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "2":
            warn("Toggle telemetry settings?")
            if prompt("Type YES: ").upper() == "YES":
                try:
                    from core.privacy import disable_telemetry
                    disable_telemetry(logger)
                    ok("Telemetry settings changed.")
                except Exception as e:
                    err(str(e))
            pause()
        elif c == "3":
            try:
                from core.privacy import scan_tracking_files
                tracking = scan_tracking_files(logger)
                sep()
                for t in tracking:
                    print(f"  {t['category']:<25} {t['files']:>5} files  {fmt_bytes(t['size'])}")
            except Exception as e:
                err(str(e))
            pause()
        elif c == "4":
            warn("Delete all tracking files?")
            if prompt("Type YES: ").upper() == "YES":
                try:
                    from core.privacy import clean_tracking_files
                    freed = clean_tracking_files(logger)
                    ok(f"Freed: {fmt_bytes(freed)}")
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
        header("App Tracer")
        sessions = TracerSession.load_sessions(str(profile_path))
        if current_session and current_session.is_running:
            print(f"  {G}[LIVE]{RST} Tracing {B}'{current_session.app_name}'{RST}  "
                  f"in  {current_session.watch_path}")
            print(f"  Created:{G}{len(current_session.created_files)}{RST}  "
                  f"Modified:{Y}{len(current_session.modified_files)}{RST}  "
                  f"Deleted:{R}{len(current_session.deleted_files)}{RST}")
        sep()
        print(f"  {C}[1]{RST} Start tracing  (live feed until Enter)")
        print(f"  {C}[2]{RST} Stop active session")
        print(f"  {C}[3]{RST} List saved sessions")
        print(f"  {C}[4]{RST} View files in a session")
        print(f"  {C}[5]{RST} Clean files in a session")
        print(f"  {C}[6]{RST} Delete a session")
        print(f"  {C}[7]{RST} Deep app trace analysis")
        print(f"  {C}[0]{RST} Back")
        sep()
        c = prompt()

        if c == "0":
            if current_session and current_session.is_running:
                current_session.stop()
            break

        elif c == "1":
            if current_session and current_session.is_running:
                warn("Already tracing. Stop first [2].")
                pause()
                continue

            clr()
            sep()
            print(f"  {C}{B}App Tracer — setup{RST}")
            sep()
            print(f"  {DIM}Label    — libovolný název session (např. 'loader', 'cheat').{RST}")
            print(f"  {DIM}Watch    — složka k monitorování souborů (rekurzivně).{RST}")
            print(f"  {DIM}Target   — exe název procesu pro DLL injection monitoring{RST}")
            print(f"  {DIM}           (např. 'game.exe'). Nechej prázdné pro skip.{RST}")
            sep()

            app_name = prompt("Label session: ").strip()
            if not app_name:
                continue

            default_path = os.path.expanduser("~")
            watch_path = prompt(f"Watch path [{default_path}]: ").strip() or default_path
            if not os.path.isdir(watch_path):
                err(f"Složka neexistuje: {watch_path}")
                pause()
                continue

            target_proc = prompt("Target process (např. game.exe) [Enter = skip]: ").strip() or None

            current_session = TracerSession(app_name, str(profile_path), logger)
            current_session.start(watch_path=watch_path, target_process=target_proc)

            # ── live feed ────────────────────────────────────
            clr()
            sep("═")
            print(f"  {G}{B}LIVE TRACE{RST}  {B}{app_name}{RST}")
            print(f"  watch : {watch_path}")
            if target_proc:
                print(f"  target: {Y}{target_proc}{RST}  (DLL injection monitoring ON)")
            sep("═")
            print(f"  {DIM}Legenda:{RST}  "
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
                    # DLL injection — zvýrazni celý řádek
                    if etype == "DLL  ":
                        print(f"  {DIM}{event['time']}{RST}  {R}{B}{etype}{RST}  {R}{event['path']}{RST}")
                    else:
                        print(f"  {DIM}{event['time']}{RST}  {col}{etype}{RST}  {event['path']}")
                except _queue.Empty:
                    pass

            current_session.stop()
            sep("═")
            ok(f"Uloženo  |  "
               f"files: {G}+{len(current_session.created_files)} ~{len(current_session.modified_files)} -{len(current_session.deleted_files)}{RST}  "
               f"procs: {G}+{len(current_session.new_processes)}{RST}  "
               f"DLLs: {R}{len(current_session.injected_dlls)}{RST}  "
               f"net: {C}{len(current_session.new_connections)}{RST}")
            current_session = None
            pause()

        elif c == "2":
            if current_session and current_session.is_running:
                current_session.stop()
                ok(f"Stopped '{current_session.app_name}'.")
                current_session = None
            else:
                warn("No active session.")
            pause()

        elif c == "3":
            sep()
            if not sessions:
                warn("Žádné sessions.")
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
            sid = prompt("Session ID: ")
            session = next((s for s in sessions if s.get("session_id") == sid), None)
            if session:
                sep()
                # DLL injection — nejdůležitější, ukaž první
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
                            print(f"    {DIM}... a {len(files)-30} dalších{RST}")
            else:
                err("Session nenalezena.")
            pause()

        elif c == "5":
            sid = prompt("Session ID: ")
            session = next((s for s in sessions if s.get("session_id") == sid), None)
            if session:
                files = session.get("created_files", [])
                warn(f"Delete {len(files)} created files from session '{sid}'?")
                if prompt("Type YES: ").upper() == "YES":
                    try:
                        from core.uninstaller import remove_traced_files
                        freed = remove_traced_files(files, logger)
                        ok(f"Freed: {fmt_bytes(freed)}")
                    except Exception as e:
                        err(str(e))
            else:
                err("Session not found.")
            pause()

        elif c == "6":
            sid = prompt("Session ID: ")
            f = profile_path / f"trace_{sid}.json"
            if f.exists():
                warn(f"Delete session '{sid}'?")
                if prompt("Type YES: ").upper() == "YES":
                    f.unlink()
                    ok("Deleted.")
            else:
                err("Session not found.")
            pause()

        elif c == "7":
            app_name = prompt("App name to analyze: ")
            if app_name:
                info(f"Analyzing traces for '{app_name}'...")
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
    header("Uninstaller")
    info("Loading installed programs...")
    try:
        from core.uninstaller import list_programs
        programs = list_programs(logger)
    except Exception as e:
        err(str(e))
        pause()
        return

    while True:
        header("Uninstaller")
        print(f"  {'#':>4}  {'Name':<35}  {'Version':<15}  {'Publisher'}")
        sep("-")
        for i, p in enumerate(programs[:40]):
            print(f"  {i+1:>4}  {p['name'][:35]:<35}  {p.get('version','')[:15]:<15}  {p.get('publisher','')[:25]}")
        if len(programs) > 40:
            print(f"  {DIM}... and {len(programs)-40} more{RST}")
        sep()
        print(f"  {C}[u #]{RST} Uninstall #   {C}[s word]{RST} Search   {C}[0]{RST} Back")
        sep()
        cmd = prompt()
        if cmd == "0": break
        parts = cmd.split(None, 1)
        if not parts: continue
        if parts[0] == "s" and len(parts) > 1:
            query = parts[1].lower()
            programs = [p for p in programs if query in p["name"].lower()]
            info(f"Showing {len(programs)} matches for '{parts[1]}'")
        elif parts[0] == "u" and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                prog = programs[idx]
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
                from core.scheduler import list_tasks
                tasks = list_tasks(logger)
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
                    from core.scheduler import create_task
                    create_task(name, schedule, profile or "standard", logger)
                    ok("Task created.")
                except Exception as e:
                    err(str(e))
            pause()
        elif c in ("3","4"):
            name = prompt("Task name: ")
            if name:
                try:
                    if c == "3":
                        from core.scheduler import toggle_task
                        toggle_task(name, logger)
                        ok("Toggled.")
                    else:
                        warn(f"Delete task '{name}'?")
                        if prompt("Type YES: ").upper() == "YES":
                            from core.scheduler import delete_task
                            delete_task(name, logger)
                            ok("Deleted.")
                except Exception as e:
                    err(str(e))
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
