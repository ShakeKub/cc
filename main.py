#!/usr/bin/env python3
"""System Cleaner & Optimization Tool - Entry Point.

Usage:
    python main.py                    Launch the TUI application
    python main.py --silent           Run cleaning silently (no UI)
    python main.py --profile quick    Use specific cleaning profile
    python main.py --cli scan         Run a CLI command
    python main.py --cli clean        Run cleaning via CLI
    python main.py --cli report       Generate a cleaning report

Requires: Windows 10/11, Python 3.10+
Install:  pip install -r requirements.txt
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Keep cc/ first on sys.path so local "core" imports resolve reliably.
app_dir = Path(__file__).resolve().parent
project_root = app_dir.parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))


def check_platform():
    """Warn if not running on Windows (core features need Windows APIs)."""
    if os.name != "nt":
        print("\n  [!] WARNING: This tool is designed for Windows.")
        print("  [!] Some features will not work on this platform.")
        print("  [!] The TUI interface will still launch for demonstration.\n")


def check_admin():
    """Check and display admin status."""
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False
    return is_admin


def run_silent(profile_name: str = "standard"):
    """Run cleaning in silent mode (no UI)."""
    from core.logger import CleanerLogger
    from core.cleaner import clean_all

    logger = CleanerLogger()
    config_path = Path(__file__).parent / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))

    profile = config.get("cleaning_profiles", {}).get(profile_name)
    print(f"[*] Running {profile_name} clean in silent mode...")

    results = clean_all(logger, profile)
    freed = results.get("total_freed", 0)
    freed_str = logger._format_bytes(freed)

    print(f"[+] Cleaning complete!")
    print(f"[+] Total freed: {freed_str}")
    print(f"[+] Actions performed: {len(results.get('actions', []))}")
    for action_name, action_freed in results.get("actions", []):
        freed_display = logger._format_bytes(action_freed) if action_freed else "done"
        print(f"    - {action_name}: {freed_display}")

    # Export report
    report_path = logger.export_json()
    print(f"[+] Report saved: {report_path}")


def run_cli(command: str):
    """Run a CLI command."""
    from core.logger import CleanerLogger
    logger = CleanerLogger()

    if command == "scan":
        from core.cleaner import scan_all
        print("[*] Scanning system...")
        results = scan_all(logger)
        total = logger._format_bytes(results.get("temp_size", 0))
        print(f"[+] Found {results.get('temp_files', 0)} temporary files ({total})")
        for cat, info in results.get("categories", {}).items():
            size = logger._format_bytes(info.get("size", 0))
            print(f"    {cat}: {info.get('count', 0)} items ({size})")

    elif command == "clean":
        run_silent("standard")

    elif command == "report":
        stats = logger.get_session_stats()
        print(f"[*] Session report:")
        print(f"    Duration: {stats.get('duration_seconds', 0):.1f}s")
        print(f"    Freed: {stats.get('total_freed_readable', '0 B')}")
        print(f"    Actions: {stats.get('actions_taken', 0)}")
        txt_path = logger.export_txt()
        json_path = logger.export_json()
        print(f"[+] TXT report: {txt_path}")
        print(f"[+] JSON report: {json_path}")

    elif command == "browsers":
        try:
            from core.browser import detect_installed_browsers
            browsers = detect_installed_browsers()
            print(f"[*] Detected {len(browsers)} browsers:")
            for b in browsers:
                size = logger._format_bytes(b["cache_size"])
                print(f"    {b['display_name']}: {b['profiles']} profiles, cache: {size}")
        except Exception as e:
            print(f"[!] Error: {e}")

    elif command == "processes":
        from core.process import list_processes
        procs = list_processes(sort_by="memory")
        print(f"[*] Top 20 processes by memory:")
        print(f"    {'PID':>8}  {'Name':<25}  {'CPU%':>6}  {'Memory':>12}")
        print(f"    {'─'*8}  {'─'*25}  {'─'*6}  {'─'*12}")
        for p in procs[:20]:
            mem = logger._format_bytes(p["memory_bytes"])
            print(f"    {p['pid']:>8}  {p['name']:<25}  {p['cpu_percent']:>5.1f}%  {mem:>12}")

    elif command == "network":
        from core.network import get_ip_info
        info = get_ip_info()
        print(f"[*] Hostname: {info.get('hostname', 'N/A')}")
        for iface in info.get("interfaces", []):
            if iface.get("is_up"):
                for addr in iface.get("addresses", []):
                    if addr.get("type") == "IPv4":
                        print(f"    {iface['name']}: {addr['address']}")

    else:
        print(f"[!] Unknown command: {command}")
        print("[*] Available commands: scan, clean, report, browsers, processes, network")


def main():
    parser = argparse.ArgumentParser(
        description="System Cleaner & Optimization Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python main.py                    Launch TUI\n"
               "  python main.py --silent            Silent clean\n"
               "  python main.py --profile deep      Deep clean\n"
               "  python main.py --cli scan          CLI scan\n"
               "  python main.py --cli processes     List processes\n",
    )
    parser.add_argument("--silent", action="store_true",
                        help="Run cleaning silently without UI")
    parser.add_argument("--profile", default="standard",
                        help="Cleaning profile: quick, standard, deep")
    parser.add_argument("--cli", metavar="COMMAND",
                        help="Run a CLI command (scan, clean, report, browsers, processes, network)")

    args = parser.parse_args()
    check_platform()

    if args.cli:
        run_cli(args.cli)
    elif args.silent:
        run_silent(args.profile)
    else:
        # Launch the TUI
        from app import SystemCleanerApp
        app = SystemCleanerApp()
        app.run()


if __name__ == "__main__":
    main()
