"""Main Textual application for System Cleaner & Optimization Tool."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import psutil
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static
from textual.timer import Timer
from textual import work

from core.logger import CleanerLogger
from themes import get_theme, list_themes, THEMES
from ui.dashboard import (
    Sidebar, MainContent, DashboardLayout, MENU_ITEMS,
    render_dashboard_view, render_cleaner_view, render_process_view,
    render_network_view, render_startup_view, render_disk_view,
    render_registry_view, render_optimizer_view, render_privacy_view,
    render_browser_view, render_uninstaller_view, render_scheduler_view,
    render_tracer_view, render_logs_view,
)
from ui.widgets import SystemStatsBar, StatusLine, HeaderBanner
from ui.dialogs import ConfirmDialog, SearchDialog, InputDialog, CommandPalette


def load_config() -> dict:
    """Load application config."""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


class SystemCleanerApp(App):
    """System Cleaner & Optimization Tool - Main Application."""

    TITLE = "System Cleaner v1.0"

    CSS = """
    Screen {
        background: #0d0d0d;
    }
    #app-header {
        dock: top;
        height: 8;
        background: #0d0d0d;
        padding: 0 1;
    }
    #stats-bar {
        dock: top;
        height: 1;
        background: #161b22;
        padding: 0 1;
    }
    #main-area {
        height: 1fr;
    }
    Sidebar {
        width: 28;
        background: #0d1117;
        border-right: thick #30363d;
        padding: 1 0;
    }
    .sidebar-title {
        text-align: center;
        color: #00ff41;
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    .menu-item {
        padding: 0 1;
        height: 1;
    }
    .menu-item:hover {
        background: #1a1a2e;
    }
    .sidebar-footer {
        dock: bottom;
        height: 3;
        padding: 0 1;
        color: #666666;
    }
    MainContent {
        background: #0d0d0d;
        padding: 1 2;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: #161b22;
        padding: 0 1;
    }
    #admin-warning {
        dock: bottom;
        height: 1;
        background: #ff880030;
        color: #ff8800;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("slash", "search", "Search"),
        ("ctrl+p", "command_palette", "Commands"),
        ("r", "refresh", "Refresh"),
        ("t", "cycle_theme", "Theme"),
        ("up", "menu_up", "Up"),
        ("down", "menu_down", "Down"),
        ("enter", "menu_select", "Select"),
        ("1", "quick_action_1", "Quick Clean"),
        ("2", "quick_action_2", "Standard Clean"),
        ("3", "quick_action_3", "Deep Clean"),
        ("4", "quick_action_4", "Scan"),
        ("5", "quick_action_5", "Browser Clean"),
        ("6", "quick_action_6", "Registry Scan"),
        ("7", "quick_action_7", "Optimize RAM"),
        ("8", "quick_action_8", "Network Diag"),
        ("s", "scan", "Scan"),
        ("c", "clean", "Clean"),
        ("k", "kill_process", "Kill"),
        ("f", "flush_dns", "Flush DNS"),
        ("d", "action_d", "Action D"),
        ("e", "action_e", "Action E"),
        ("x", "action_x", "Action X"),
        ("a", "action_a", "Action A"),
        ("b", "action_b", "Action B"),
        ("l", "action_l", "Action L"),
        ("o", "action_o", "Action O"),
        ("p", "action_p", "Action P"),
        ("n", "action_n", "Action N"),
        ("u", "action_u", "Action U"),
        ("h", "action_h", "Action H"),
        ("question_mark", "show_help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.logger = CleanerLogger(
            log_dir=self.config.get("log_dir", "logs"),
            log_format=self.config.get("log_format", "json"),
            max_files=self.config.get("max_log_files", 50),
        )
        self.current_view = "dashboard"
        self.theme_index = 0
        self.theme_names = list_themes()
        self.is_admin = self._check_admin()

        # Cached data for views
        self._processes: list[dict] = []
        self._connections: list[dict] = []
        self._ip_info: dict = {}
        self._startup_entries: list[dict] = []
        self._programs: list[dict] = []
        self._scan_results: dict | None = None
        self._registry_invalid: list[dict] | None = None
        self._services: list[dict] | None = None
        self._power_plans: list[dict] | None = None
        self._telemetry: list[dict] | None = None
        self._tracking: list[dict] | None = None
        self._browsers: list[dict] | None = None
        self._browser_scan: dict | None = None
        self._disk_usage: dict | None = None
        self._large_files: list[dict] | None = None
        self._scheduled_tasks: list[dict] | None = None
        self._cleaning_profiles: dict | None = None
        self._tracer_traces: dict | None = None
        self._tracer_summary: dict | None = None

        self._stats_timer: Timer | None = None

    def _check_admin(self) -> bool:
        """Check if running with administrator privileges."""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def compose(self) -> ComposeResult:
        yield HeaderBanner(id="app-header")
        yield SystemStatsBar(id="stats-bar")
        if not self.is_admin:
            yield Static(
                " ⚠ Running without admin privileges - some features may be limited",
                id="admin-warning",
            )
        with Horizontal(id="main-area"):
            yield Sidebar(id="sidebar")
            yield MainContent(id="main-content")
        yield StatusLine(id="status-bar")

    def on_mount(self):
        """Initialize the app after mounting."""
        self._set_status("System Cleaner initialized. Use ↑/↓ to navigate, Enter to select.", "info")
        self._refresh_view()
        # Start stats timer
        self._stats_timer = self.set_interval(2.0, self._update_stats)
        self._update_stats()

    def _update_stats(self):
        """Update the system stats bar."""
        try:
            stats_bar = self.query_one("#stats-bar", SystemStatsBar)
            stats_bar.cpu_percent = psutil.cpu_percent(interval=0)
            stats_bar.ram_percent = psutil.virtual_memory().percent
            try:
                stats_bar.disk_percent = psutil.disk_usage(
                    "C:\\" if os.name == "nt" else "/"
                ).percent
            except Exception:
                stats_bar.disk_percent = 0
        except Exception:
            pass

    def _set_status(self, message: str, status_type: str = "info"):
        """Update the status bar."""
        try:
            status = self.query_one("#status-bar", StatusLine)
            status.message = message
            status.status_type = status_type
        except Exception:
            pass

    def _refresh_view(self):
        """Refresh the current view."""
        content = self.query_one("#main-content", MainContent)
        view_name = self.current_view

        if view_name == "dashboard":
            stats = self._get_quick_stats()
            content.update_view(view_name, render_dashboard_view(stats))
        elif view_name == "cleaner":
            content.update_view(view_name, render_cleaner_view(self._scan_results))
        elif view_name == "process":
            self._load_processes()
        elif view_name == "network":
            self._load_network()
        elif view_name == "startup":
            self._load_startup()
        elif view_name == "disk":
            self._load_disk()
        elif view_name == "registry":
            content.update_view(view_name, render_registry_view(self._registry_invalid))
        elif view_name == "optimizer":
            content.update_view(view_name, render_optimizer_view(
                self._services, self._power_plans))
        elif view_name == "privacy":
            content.update_view(view_name, render_privacy_view(
                self._telemetry, self._tracking))
        elif view_name == "browser":
            content.update_view(view_name, render_browser_view(
                self._browsers, self._browser_scan))
        elif view_name == "uninstaller":
            content.update_view(view_name, render_uninstaller_view(self._programs))
        elif view_name == "scheduler":
            content.update_view(view_name, render_scheduler_view(
                self._scheduled_tasks, self._cleaning_profiles))
        elif view_name == "tracer":
            content.update_view(view_name, render_tracer_view(
                self._tracer_traces, self._tracer_summary))
        elif view_name == "logs":
            stats = self.logger.get_session_stats()
            content.update_view(view_name, render_logs_view(
                stats, self.logger.session_log))

    def _get_quick_stats(self) -> dict:
        """Get quick system stats for dashboard."""
        mem = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
        except Exception:
            disk = type("D", (), {"total": 0, "used": 0, "free": 0, "percent": 0})()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0),
            "ram_percent": mem.percent,
            "ram_total": mem.total,
            "ram_used": mem.used,
            "disk_percent": disk.percent,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_free": disk.free,
            "process_count": len(psutil.pids()),
        }

    # ── Navigation ──────────────────────────────────────────

    def action_menu_up(self):
        sidebar = self.query_one("#sidebar", Sidebar)
        new_index = max(0, sidebar.selected_index - 1)
        action = sidebar.select_item(new_index)
        if action:
            self.current_view = action
            self._refresh_view()

    def action_menu_down(self):
        sidebar = self.query_one("#sidebar", Sidebar)
        new_index = min(len(MENU_ITEMS) - 1, sidebar.selected_index + 1)
        action = sidebar.select_item(new_index)
        if action:
            self.current_view = action
            self._refresh_view()

    def action_menu_select(self):
        self._refresh_view()

    # ── Quick Actions (Dashboard numbers) ───────────────────

    def action_quick_action_1(self):
        if self.current_view == "dashboard":
            self._run_clean("quick")

    def action_quick_action_2(self):
        if self.current_view == "dashboard":
            self._run_clean("standard")

    def action_quick_action_3(self):
        if self.current_view == "dashboard":
            self._run_clean("deep")

    def action_quick_action_4(self):
        if self.current_view == "dashboard":
            self.action_scan()

    def action_quick_action_5(self):
        if self.current_view == "dashboard":
            self.current_view = "browser"
            sidebar = self.query_one("#sidebar", Sidebar)
            for i, (action_id, _, _) in enumerate(MENU_ITEMS):
                if action_id == "browser":
                    sidebar.select_item(i)
                    break
            self._refresh_view()

    def action_quick_action_6(self):
        if self.current_view == "dashboard":
            self.current_view = "registry"
            sidebar = self.query_one("#sidebar", Sidebar)
            for i, (action_id, _, _) in enumerate(MENU_ITEMS):
                if action_id == "registry":
                    sidebar.select_item(i)
                    break
            self._refresh_view()

    def action_quick_action_7(self):
        if self.current_view == "dashboard":
            self._optimize_ram()

    def action_quick_action_8(self):
        if self.current_view == "dashboard":
            self.current_view = "network"
            sidebar = self.query_one("#sidebar", Sidebar)
            for i, (action_id, _, _) in enumerate(MENU_ITEMS):
                if action_id == "network":
                    sidebar.select_item(i)
                    break
            self._refresh_view()

    # ── Core Actions ────────────────────────────────────────

    def action_scan(self):
        """Handle scan action based on current view."""
        if self.current_view == "cleaner":
            self._scan_system()
        elif self.current_view == "browser":
            self._scan_browsers()
        elif self.current_view == "registry":
            self._scan_registry()
        elif self.current_view == "privacy":
            self._scan_privacy()
        elif self.current_view == "startup":
            self._load_startup()

    def action_clean(self):
        """Handle clean action based on current view."""
        if self.current_view == "cleaner":
            self._confirm_and_clean()
        elif self.current_view == "browser":
            self._confirm_and_clean_browser()

    @work(thread=True)
    def _scan_system(self):
        """Scan system in background thread."""
        self._set_status("Scanning system...", "working")
        from core.cleaner import scan_all
        self._scan_results = scan_all(self.logger)
        self.call_from_thread(self._post_scan)

    def _post_scan(self):
        self._set_status("Scan complete!", "success")
        self._refresh_view()

    def _confirm_and_clean(self):
        """Show confirmation before cleaning."""
        def on_confirm(confirmed: bool):
            if confirmed:
                self._run_clean("standard")

        self.push_screen(
            ConfirmDialog(
                "Confirm System Clean",
                "This will remove temporary files, clear caches, and clean system junk.\n"
                "Protected system files will not be affected.",
                risk_level="medium",
            ),
            on_confirm,
        )

    @work(thread=True)
    def _run_clean(self, profile_name: str):
        """Run cleaning with specified profile."""
        self._set_status(f"Running {profile_name} clean...", "working")
        from core.cleaner import clean_all
        profiles = self.config.get("cleaning_profiles", {})
        profile = profiles.get(profile_name)
        results = clean_all(self.logger, profile)
        freed = results.get("total_freed", 0)
        self.call_from_thread(self._post_clean, freed)

    def _post_clean(self, freed: int):
        from core.logger import CleanerLogger
        freed_str = CleanerLogger._format_bytes(freed)
        self._set_status(f"Cleaning complete! Freed {freed_str}", "success")
        self._refresh_view()

    # ── Process Manager ─────────────────────────────────────

    @work(thread=True)
    def _load_processes(self):
        """Load process list in background."""
        from core.process import list_processes
        self._processes = list_processes(sort_by="memory", logger=self.logger)
        self.call_from_thread(self._render_processes)

    def _render_processes(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("process", render_process_view(self._processes))

    def action_kill_process(self):
        """Kill a process (prompts for PID)."""
        if self.current_view != "process":
            return

        def on_input(pid_str: str):
            if pid_str:
                try:
                    pid = int(pid_str)
                    self._confirm_kill(pid)
                except ValueError:
                    self._set_status("Invalid PID", "error")

        self.push_screen(
            InputDialog("Kill Process", "Enter PID to kill:", ""),
            on_input,
        )

    def _confirm_kill(self, pid: int):
        def on_confirm(confirmed: bool):
            if confirmed:
                from core.process import kill_process
                success = kill_process(pid, self.logger)
                if success:
                    self._set_status(f"Process {pid} terminated", "success")
                else:
                    self._set_status(f"Failed to kill process {pid}", "error")
                self._load_processes()

        self.push_screen(
            ConfirmDialog(
                "Kill Process",
                f"Terminate process with PID {pid}?",
                risk_level="medium",
            ),
            on_confirm,
        )

    # ── Network Tools ───────────────────────────────────────

    @work(thread=True)
    def _load_network(self):
        """Load network info in background."""
        from core.network import get_active_connections, get_ip_info
        self._connections = get_active_connections(self.logger)
        self._ip_info = get_ip_info(self.logger)
        self.call_from_thread(self._render_network)

    def _render_network(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("network", render_network_view(
            self._connections, self._ip_info))

    def action_flush_dns(self):
        if self.current_view == "network":
            from core.network import flush_dns
            success = flush_dns(self.logger)
            self._set_status(
                "DNS cache flushed" if success else "DNS flush failed",
                "success" if success else "error",
            )

    # ── Startup Manager ─────────────────────────────────────

    @work(thread=True)
    def _load_startup(self):
        """Load startup entries."""
        self._set_status("Loading startup entries...", "working")
        try:
            from core.startup import get_startup_entries
            self._startup_entries = get_startup_entries(self.logger)
        except Exception as e:
            self._startup_entries = []
            self.logger.error(f"Failed to load startup: {e}")
        self.call_from_thread(self._render_startup)

    def _render_startup(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("startup", render_startup_view(self._startup_entries))
        self._set_status(f"Found {len(self._startup_entries)} startup entries", "info")

    # ── Disk Tools ──────────────────────────────────────────

    @work(thread=True)
    def _load_disk(self):
        """Load disk usage info."""
        from core.disk import get_disk_usage
        root = "C:\\" if os.name == "nt" else "/"
        self._disk_usage = get_disk_usage(root, self.logger)
        self.call_from_thread(self._render_disk)

    def _render_disk(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("disk", render_disk_view(
            self._disk_usage, self._large_files))

    # ── Browser ─────────────────────────────────────────────

    @work(thread=True)
    def _scan_browsers(self):
        """Scan browser data."""
        self._set_status("Scanning browsers...", "working")
        from core.browser import detect_installed_browsers
        self._browsers = detect_installed_browsers()
        self.call_from_thread(self._render_browsers)

    def _render_browsers(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("browser", render_browser_view(
            self._browsers, self._browser_scan))
        self._set_status(f"Found {len(self._browsers or [])} browsers", "info")

    def _confirm_and_clean_browser(self):
        def on_confirm(confirmed: bool):
            if confirmed:
                self._clean_browser_cache()

        self.push_screen(
            ConfirmDialog(
                "Clean Browser Cache",
                "This will clear browser cache files.\nCookies and history will NOT be affected.",
                risk_level="low",
            ),
            on_confirm,
        )

    @work(thread=True)
    def _clean_browser_cache(self):
        from core.browser import clean_all_browsers
        results = clean_all_browsers(self.logger, cache=True)
        total = sum(sum(v.values()) for v in results.values())
        from core.logger import CleanerLogger
        freed_str = CleanerLogger._format_bytes(total)
        self.call_from_thread(
            lambda: self._set_status(f"Browser cache cleaned: {freed_str}", "success")
        )

    # ── Registry ────────────────────────────────────────────

    @work(thread=True)
    def _scan_registry(self):
        """Scan registry for invalid entries."""
        self._set_status("Scanning registry...", "working")
        try:
            from core.registry import scan_invalid_entries
            self._registry_invalid = scan_invalid_entries(self.logger)
        except Exception as e:
            self._registry_invalid = []
            self.logger.error(f"Registry scan failed: {e}")
        self.call_from_thread(self._render_registry)

    def _render_registry(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("registry", render_registry_view(self._registry_invalid))
        count = len(self._registry_invalid or [])
        self._set_status(f"Registry scan complete: {count} invalid entries", "info")

    # ── Privacy ─────────────────────────────────────────────

    @work(thread=True)
    def _scan_privacy(self):
        """Scan privacy settings."""
        self._set_status("Scanning privacy settings...", "working")
        try:
            from core.privacy import get_telemetry_status, scan_tracking_files
            self._telemetry = get_telemetry_status(self.logger)
            self._tracking = scan_tracking_files(self.logger)
        except Exception as e:
            self.logger.error(f"Privacy scan failed: {e}")
        self.call_from_thread(self._render_privacy)

    def _render_privacy(self):
        content = self.query_one("#main-content", MainContent)
        content.update_view("privacy", render_privacy_view(
            self._telemetry, self._tracking))
        self._set_status("Privacy scan complete", "info")

    # ── Optimizer ───────────────────────────────────────────

    @work(thread=True)
    def _optimize_ram(self):
        """Optimize RAM usage."""
        self._set_status("Optimizing RAM...", "working")
        try:
            from core.optimizer import optimize_ram
            result = optimize_ram(self.logger)
            from core.logger import CleanerLogger
            freed_str = CleanerLogger._format_bytes(result.get("freed", 0))
            self.call_from_thread(
                lambda: self._set_status(f"RAM optimized: freed {freed_str}", "success")
            )
        except Exception as e:
            self.call_from_thread(
                lambda: self._set_status(f"RAM optimization failed: {e}", "error")
            )

    # ── Dialogs & Search ────────────────────────────────────

    def action_search(self):
        """Open search dialog."""
        def on_search(query: str):
            if query:
                self._handle_search(query)

        self.push_screen(SearchDialog("Search", "Search programs, files, settings..."), on_search)

    def _handle_search(self, query: str):
        """Handle search query based on current view."""
        self._set_status(f"Searching: {query}", "working")
        if self.current_view == "uninstaller" and self._programs:
            from core.uninstaller import search_programs
            filtered = search_programs(self._programs, query)
            content = self.query_one("#main-content", MainContent)
            content.update_view("uninstaller", render_uninstaller_view(filtered))
            self._set_status(f"Found {len(filtered)} matching programs", "info")
        elif self.current_view == "process" and self._processes:
            filtered = [p for p in self._processes if query.lower() in p["name"].lower()]
            content = self.query_one("#main-content", MainContent)
            content.update_view("process", render_process_view(filtered))
            self._set_status(f"Found {len(filtered)} matching processes", "info")

    def action_command_palette(self):
        """Open command palette."""
        def on_command(cmd: str):
            if cmd:
                self._execute_command(cmd)

        self.push_screen(CommandPalette(), on_command)

    def _execute_command(self, cmd: str):
        """Execute a command from the palette."""
        parts = cmd.split(":")
        category = parts[0]
        action = parts[1] if len(parts) > 1 else ""

        if cmd == "quit":
            self.exit()
        elif cmd == "about":
            self._set_status(
                "System Cleaner v1.0 - Advanced System Optimization Tool", "info"
            )
        elif cmd == "theme:cycle":
            self.action_cycle_theme()
        elif category == "clean":
            self._run_clean(action or "standard")
        elif category == "scan":
            if action == "system":
                self._scan_system()
            elif action == "browser":
                self._scan_browsers()
            elif action == "registry":
                self._scan_registry()
        elif category == "process":
            self.current_view = "process"
            self._refresh_view()
        elif category == "network":
            self.current_view = "network"
            self._refresh_view()
            if action == "diagnostics":
                self._run_diagnostics()
        elif category == "optimizer":
            if action == "ram":
                self._optimize_ram()
        elif category == "export":
            self._export_log(action)
        elif category == "trace":
            self._start_trace_analysis()
        elif category == "privacy":
            self.current_view = "privacy"
            self._scan_privacy()

    @work(thread=True)
    def _run_diagnostics(self):
        """Run network diagnostics."""
        self._set_status("Running network diagnostics...", "working")
        from core.network import run_diagnostics
        results = run_diagnostics(self.logger)
        passed = sum(1 for t in results if t["status"] == "pass")
        self.call_from_thread(
            lambda: self._set_status(
                f"Diagnostics: {passed}/{len(results)} tests passed",
                "success" if passed == len(results) else "warning",
            )
        )

    def _export_log(self, fmt: str):
        """Export session log."""
        if fmt == "txt":
            path = self.logger.export_txt()
            self._set_status(f"Log exported to: {path}", "success")
        elif fmt == "json":
            path = self.logger.export_json()
            self._set_status(f"Log exported to: {path}", "success")

    # ── App Tracer ──────────────────────────────────────────

    def _start_trace_analysis(self):
        """Start deep app trace analysis."""
        def on_input(app_name: str):
            if app_name:
                self._run_trace(app_name)

        self.push_screen(
            InputDialog(
                "Deep App Trace Analysis",
                "Enter application name or executable (e.g., 'support.exe'):",
            ),
            on_input,
        )

    @work(thread=True)
    def _run_trace(self, app_name: str):
        """Run trace analysis in background."""
        self._set_status(f"Analyzing traces for '{app_name}'...", "working")
        from core.tracer import AppTracer
        tracer = AppTracer(app_name, logger=self.logger)
        self._tracer_traces = tracer.scan_all()
        self._tracer_summary = tracer.get_summary()
        self.call_from_thread(self._render_tracer)

    def _render_tracer(self):
        self.current_view = "tracer"
        content = self.query_one("#main-content", MainContent)
        content.update_view("tracer", render_tracer_view(
            self._tracer_traces, self._tracer_summary))
        total = self._tracer_summary.get("total_traces", 0) if self._tracer_summary else 0
        self._set_status(f"Trace analysis complete: {total} traces found", "info")

    # ── Context-sensitive key actions ───────────────────────

    def action_action_d(self):
        """Context-sensitive 'D' action."""
        if self.current_view == "startup":
            self._disable_startup_entry()
        elif self.current_view == "network":
            self._run_diagnostics()
        elif self.current_view == "disk":
            self._find_duplicates()
        elif self.current_view == "uninstaller":
            self._deep_uninstall()
        elif self.current_view == "optimizer":
            self._disable_service()
        elif self.current_view == "scheduler":
            self._delete_task()

    def action_action_e(self):
        if self.current_view == "startup":
            self._enable_startup_entry()
        elif self.current_view == "disk":
            self._find_empty_folders()
        elif self.current_view == "optimizer":
            self._enable_service()

    def action_action_x(self):
        if self.current_view == "startup":
            self._remove_startup_entry()
        elif self.current_view == "disk":
            self._shred_file()
        elif self.current_view == "privacy":
            self._secure_delete()
        elif self.current_view == "tracer":
            self._deep_clean_app()

    def action_action_a(self):
        if self.current_view == "disk":
            self._analyze_directory()
        elif self.current_view == "browser":
            self._clean_all_browser_data()
        elif self.current_view == "tracer":
            self._start_trace_analysis()

    def action_action_b(self):
        if self.current_view == "registry":
            self._backup_registry()
        elif self.current_view == "tracer":
            self._backup_registry()

    def action_action_l(self):
        if self.current_view == "disk":
            self._find_large_files()

    def action_action_o(self):
        if self.current_view == "uninstaller":
            self._find_orphaned()
        elif self.current_view == "optimizer":
            self._optimize_ram()

    def action_action_p(self):
        if self.current_view == "network":
            self._ping_host()
        elif self.current_view == "optimizer":
            self._switch_power_plan()
        elif self.current_view == "scheduler":
            self._create_profile()

    def action_action_n(self):
        if self.current_view == "scheduler":
            self._create_task()

    def action_action_u(self):
        if self.current_view == "uninstaller":
            self._uninstall_program()

    def action_action_h(self):
        if self.current_view == "browser":
            self._clean_browser_history()

    def action_action_t(self):
        """Handle T key - context sensitive."""
        if self.current_view == "privacy":
            self._toggle_telemetry()
        elif self.current_view == "logs":
            self._export_log("txt")
        elif self.current_view == "scheduler":
            self._toggle_task()

    # ── Stub actions (prompt for input then execute) ────────

    def _disable_startup_entry(self):
        def on_input(idx_str: str):
            if idx_str:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._startup_entries):
                        from core.startup import disable_startup_entry
                        entry = self._startup_entries[idx]
                        success = disable_startup_entry(entry, self.logger)
                        self._set_status(
                            f"Disabled: {entry['name']}" if success else "Failed",
                            "success" if success else "error",
                        )
                        self._load_startup()
                except ValueError:
                    self._set_status("Invalid entry number", "error")
        self.push_screen(InputDialog("Disable Startup", "Enter entry number:"), on_input)

    def _enable_startup_entry(self):
        def on_input(idx_str: str):
            if idx_str:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._startup_entries):
                        from core.startup import enable_startup_entry
                        entry = self._startup_entries[idx]
                        success = enable_startup_entry(entry, self.logger)
                        self._set_status(
                            f"Enabled: {entry['name']}" if success else "Failed",
                            "success" if success else "error",
                        )
                        self._load_startup()
                except ValueError:
                    self._set_status("Invalid entry number", "error")
        self.push_screen(InputDialog("Enable Startup", "Enter entry number:"), on_input)

    def _remove_startup_entry(self):
        def on_input(idx_str: str):
            if idx_str:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._startup_entries):
                        entry = self._startup_entries[idx]
                        def on_confirm(confirmed: bool):
                            if confirmed:
                                from core.startup import remove_startup_entry
                                success = remove_startup_entry(entry, self.logger)
                                self._set_status(
                                    f"Removed: {entry['name']}" if success else "Failed",
                                    "success" if success else "error",
                                )
                                self._load_startup()
                        self.push_screen(
                            ConfirmDialog("Remove Startup Entry",
                                         f"Remove '{entry['name']}'?", "high"),
                            on_confirm,
                        )
                except ValueError:
                    self._set_status("Invalid entry number", "error")
        self.push_screen(InputDialog("Remove Startup", "Enter entry number:"), on_input)

    @work(thread=True)
    def _find_large_files(self):
        self._set_status("Searching for large files...", "working")
        from core.disk import find_large_files
        root = "C:\\" if os.name == "nt" else "/"
        self._large_files = find_large_files(root, min_size_mb=100, logger=self.logger)
        self.call_from_thread(self._render_disk)
        count = len(self._large_files)
        self.call_from_thread(
            lambda: self._set_status(f"Found {count} large files (>100MB)", "info")
        )

    @work(thread=True)
    def _find_duplicates(self):
        self._set_status("Scanning for duplicate files (this may take a while)...", "working")

        def on_input(path: str):
            if path:
                from core.disk import find_duplicate_files
                dupes = find_duplicate_files(path, logger=self.logger)
                self._set_status(f"Found {len(dupes)} duplicate groups", "info")

        self.call_from_thread(lambda: self.push_screen(
            InputDialog("Find Duplicates", "Enter directory to scan:", "C:\\Users"),
            on_input,
        ))

    def _find_empty_folders(self):
        def on_input(path: str):
            if path:
                from core.disk import find_empty_folders
                empties = find_empty_folders(path, self.logger)
                self._set_status(f"Found {len(empties)} empty folders", "info")
        self.push_screen(
            InputDialog("Find Empty Folders", "Enter directory:", "C:\\Users"),
            on_input,
        )

    def _analyze_directory(self):
        def on_input(path: str):
            if path:
                self._do_analyze(path)
        self.push_screen(
            InputDialog("Analyze Directory", "Enter directory path:", "C:\\"),
            on_input,
        )

    @work(thread=True)
    def _do_analyze(self, path: str):
        self._set_status(f"Analyzing {path}...", "working")
        from core.disk import analyze_directory
        results = analyze_directory(path, max_depth=2, logger=self.logger)
        self.call_from_thread(
            lambda: self._set_status(f"Analysis complete: {len(results)} directories", "info")
        )

    def _shred_file(self):
        def on_input(filepath: str):
            if filepath:
                def on_confirm(confirmed: bool):
                    if confirmed:
                        from core.disk import secure_shred
                        success = secure_shred(filepath, passes=3, logger=self.logger)
                        self._set_status(
                            f"File shredded: {filepath}" if success else "Shred failed",
                            "success" if success else "error",
                        )
                self.push_screen(
                    ConfirmDialog("Secure Shred",
                                 f"Permanently destroy '{filepath}'?\nThis cannot be undone!",
                                 "high"),
                    on_confirm,
                )
        self.push_screen(
            InputDialog("Secure Shred", "Enter file path to shred:"),
            on_input,
        )

    def _backup_registry(self):
        self._set_status("Creating registry backup...", "working")
        from core.registry import backup_registry
        path = backup_registry(logger=self.logger)
        if path:
            self._set_status(f"Registry backed up: {path}", "success")
        else:
            self._set_status("Registry backup failed", "error")

    def _uninstall_program(self):
        def on_input(idx_str: str):
            if idx_str and self._programs:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._programs):
                        prog = self._programs[idx]
                        def on_confirm(confirmed: bool):
                            if confirmed:
                                self._do_uninstall(prog)
                        self.push_screen(
                            ConfirmDialog("Uninstall Program",
                                         f"Uninstall '{prog['name']}'?", "medium"),
                            on_confirm,
                        )
                except ValueError:
                    self._set_status("Invalid program number", "error")
        self.push_screen(InputDialog("Uninstall", "Enter program number:"), on_input)

    @work(thread=True)
    def _do_uninstall(self, prog: dict):
        self._set_status(f"Uninstalling {prog['name']}...", "working")
        from core.uninstaller import uninstall_program
        success = uninstall_program(prog, self.logger, silent=True)
        self.call_from_thread(lambda: self._set_status(
            f"Uninstalled: {prog['name']}" if success else f"Uninstall failed: {prog['name']}",
            "success" if success else "error",
        ))

    def _deep_uninstall(self):
        def on_input(idx_str: str):
            if idx_str and self._programs:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._programs):
                        prog = self._programs[idx]
                        def on_confirm(confirmed: bool):
                            if confirmed:
                                self._do_deep_uninstall(prog)
                        self.push_screen(
                            ConfirmDialog("Deep Uninstall",
                                         f"Deep uninstall '{prog['name']}'?\n"
                                         "This will also remove leftover files and registry entries.",
                                         "high"),
                            on_confirm,
                        )
                except ValueError:
                    pass
        self.push_screen(InputDialog("Deep Uninstall", "Enter program number:"), on_input)

    @work(thread=True)
    def _do_deep_uninstall(self, prog: dict):
        self._set_status(f"Deep uninstalling {prog['name']}...", "working")
        from core.uninstaller import uninstall_program, find_leftovers, remove_leftovers
        uninstall_program(prog, self.logger, silent=True)
        leftovers = find_leftovers(prog, self.logger)
        freed = remove_leftovers(leftovers, self.logger)
        from core.logger import CleanerLogger
        freed_str = CleanerLogger._format_bytes(freed)
        self.call_from_thread(lambda: self._set_status(
            f"Deep uninstall complete: freed {freed_str}", "success"
        ))

    @work(thread=True)
    def _find_orphaned(self):
        self._set_status("Scanning for orphaned entries...", "working")
        from core.uninstaller import detect_orphaned_entries
        orphaned = detect_orphaned_entries(self.logger)
        self.call_from_thread(lambda: self._set_status(
            f"Found {len(orphaned)} orphaned entries", "info"
        ))

    def _disable_service(self):
        def on_input(idx_str: str):
            if idx_str and self._services:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._services):
                        svc = self._services[idx]
                        from core.optimizer import disable_service
                        success = disable_service(svc["name"], self.logger)
                        self._set_status(
                            f"Disabled: {svc['display_name']}" if success else "Failed",
                            "success" if success else "error",
                        )
                except ValueError:
                    pass
        self.push_screen(InputDialog("Disable Service", "Enter service number:"), on_input)

    def _enable_service(self):
        def on_input(idx_str: str):
            if idx_str and self._services:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._services):
                        svc = self._services[idx]
                        from core.optimizer import enable_service
                        success = enable_service(svc["name"], self.logger)
                        self._set_status(
                            f"Enabled: {svc['display_name']}" if success else "Failed",
                            "success" if success else "error",
                        )
                except ValueError:
                    pass
        self.push_screen(InputDialog("Enable Service", "Enter service number:"), on_input)

    def _switch_power_plan(self):
        def on_input(guid: str):
            if guid:
                from core.optimizer import set_power_plan
                success = set_power_plan(guid, self.logger)
                self._set_status(
                    "Power plan switched" if success else "Failed",
                    "success" if success else "error",
                )
        self.push_screen(InputDialog("Power Plan", "Enter power plan GUID:"), on_input)

    def _ping_host(self):
        def on_input(host: str):
            if host:
                self._do_ping(host)
        self.push_screen(InputDialog("Ping", "Enter hostname or IP:", "8.8.8.8"), on_input)

    @work(thread=True)
    def _do_ping(self, host: str):
        self._set_status(f"Pinging {host}...", "working")
        from core.network import ping
        result = ping(host, count=4, logger=self.logger)
        status = "success" if result["success"] else "error"
        avg = result.get("avg_latency_ms", "N/A")
        self.call_from_thread(lambda: self._set_status(
            f"Ping {host}: {'OK' if result['success'] else 'FAIL'} (avg: {avg}ms)",
            status,
        ))

    def _toggle_telemetry(self):
        def on_input(idx_str: str):
            if idx_str and self._telemetry:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self._telemetry):
                        setting = self._telemetry[idx]
                        from core.privacy import disable_telemetry, enable_telemetry
                        if setting["enabled"]:
                            success = disable_telemetry(setting["name"], self.logger)
                        else:
                            success = enable_telemetry(setting["name"], self.logger)
                        self._set_status(
                            f"Toggled: {setting['name']}" if success else "Failed",
                            "success" if success else "error",
                        )
                        self._scan_privacy()
                except ValueError:
                    pass
        self.push_screen(InputDialog("Toggle Telemetry", "Enter setting number:"), on_input)

    def _secure_delete(self):
        self._shred_file()  # Same as shred

    def _clean_all_browser_data(self):
        def on_confirm(confirmed: bool):
            if confirmed:
                self._do_clean_all_browsers()
        self.push_screen(
            ConfirmDialog("Clean All Browser Data",
                         "Clear ALL browser data (cache, cookies, history, sessions)?",
                         "high"),
            on_confirm,
        )

    @work(thread=True)
    def _do_clean_all_browsers(self):
        from core.browser import clean_all_browsers
        results = clean_all_browsers(self.logger, cache=True, cookies=True,
                                      history=True, sessions=True)
        total = sum(sum(v.values()) for v in results.values())
        from core.logger import CleanerLogger
        freed_str = CleanerLogger._format_bytes(total)
        self.call_from_thread(lambda: self._set_status(
            f"All browser data cleaned: {freed_str}", "success"
        ))

    def _clean_browser_history(self):
        def on_confirm(confirmed: bool):
            if confirmed:
                self._do_clean_browser_history()
        self.push_screen(
            ConfirmDialog("Clean Browser History",
                         "Clear browser history for all browsers?", "medium"),
            on_confirm,
        )

    @work(thread=True)
    def _do_clean_browser_history(self):
        from core.browser import clean_all_browsers
        results = clean_all_browsers(self.logger, history=True)
        self.call_from_thread(lambda: self._set_status("Browser history cleaned", "success"))

    def _deep_clean_app(self):
        if not self._tracer_traces:
            self._set_status("No trace analysis loaded. Press [A] first.", "warning")
            return

        def on_confirm(confirmed: bool):
            if confirmed:
                self._do_deep_clean_app()

        self.push_screen(
            ConfirmDialog("Deep Clean Application",
                         "Remove ALL detected traces?\n"
                         "Registry will be backed up first.",
                         "high"),
            on_confirm,
        )

    @work(thread=True)
    def _do_deep_clean_app(self):
        self._set_status("Deep cleaning application traces...", "working")
        from core.tracer import AppTracer
        tracer = AppTracer(
            self._tracer_summary["app_name"] if self._tracer_summary else "",
            logger=self.logger,
        )
        tracer.traces = self._tracer_traces
        results = tracer.deep_clean(backup_registry=True)
        self.call_from_thread(lambda: self._set_status(
            f"Deep clean: {results['removed']} removed, "
            f"{results['failed']} failed, {results['skipped']} skipped",
            "success" if results["failed"] == 0 else "warning",
        ))

    def _create_task(self):
        def on_input(name: str):
            if name:
                from core.scheduler import create_scheduled_task
                success = create_scheduled_task(name, "daily", "standard", self.logger)
                self._set_status(
                    f"Task created: {name}" if success else "Failed",
                    "success" if success else "error",
                )
        self.push_screen(InputDialog("New Task", "Enter task name:"), on_input)

    def _delete_task(self):
        def on_input(name: str):
            if name:
                from core.scheduler import delete_scheduled_task
                success = delete_scheduled_task(name, self.logger)
                self._set_status(
                    f"Task deleted: {name}" if success else "Failed",
                    "success" if success else "error",
                )
        self.push_screen(InputDialog("Delete Task", "Enter task name:"), on_input)

    def _toggle_task(self):
        def on_input(name: str):
            if name:
                from core.scheduler import toggle_scheduled_task
                success = toggle_scheduled_task(name, True, self.logger)
                self._set_status(
                    f"Task toggled: {name}" if success else "Failed",
                    "success" if success else "error",
                )
        self.push_screen(InputDialog("Toggle Task", "Enter task name:"), on_input)

    def _create_profile(self):
        def on_input(name: str):
            if name:
                from core.scheduler import save_cleaning_profile
                profile = {"temp_files": True, "dns_cache": True, "thumbnail_cache": True}
                save_cleaning_profile(name, profile, self.logger)
                self._set_status(f"Profile created: {name}", "success")
        self.push_screen(InputDialog("New Profile", "Enter profile name:"), on_input)

    # ── Theme & Misc ────────────────────────────────────────

    def action_cycle_theme(self):
        """Cycle through available themes."""
        self.theme_index = (self.theme_index + 1) % len(self.theme_names)
        theme_name = self.theme_names[self.theme_index]
        self._set_status(f"Theme: {theme_name}", "info")

    def action_refresh(self):
        """Refresh current view."""
        self._refresh_view()
        self._set_status("View refreshed", "info")

    def action_quit_app(self):
        """Quit with confirmation."""
        def on_confirm(confirmed: bool):
            if confirmed:
                # Export final log
                self.logger.export_json()
                self.exit()

        self.push_screen(
            ConfirmDialog("Quit", "Exit System Cleaner?", "low"),
            on_confirm,
        )

    def action_show_help(self):
        """Show help info."""
        self._set_status(
            "↑/↓:Navigate  Enter:Select  /:Search  Ctrl+P:Commands  "
            "S:Scan  C:Clean  R:Refresh  T:Theme  Q:Quit",
            "info",
        )
