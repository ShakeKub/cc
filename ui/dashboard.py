"""Main dashboard view composing all UI sections."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Static, Header, Footer, Label, ListView, ListItem
from textual.widget import Widget
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

from ui.widgets import (
    HeaderBanner, SystemStatsBar, StatusLine, InfoPanel, DataTable, MenuButton,
)


# Sidebar menu items with icons
MENU_ITEMS = [
    ("dashboard", "📊", "Dashboard"),
    ("cleaner", "🧹", "System Cleaner"),
    ("browser", "🌐", "Browser Cleaner"),
    ("uninstaller", "📦", "Uninstaller"),
    ("startup", "🚀", "Startup Manager"),
    ("disk", "💾", "Disk Tools"),
    ("registry", "🗝️", "Registry Cleaner"),
    ("optimizer", "⚡", "Optimizer"),
    ("privacy", "🔒", "Privacy & Security"),
    ("process", "📋", "Process Manager"),
    ("network", "🌍", "Network Tools"),
    ("scheduler", "⏰", "Scheduler"),
    ("tracer", "🔍", "App Tracer"),
    ("logs", "📝", "Logs & Reports"),
]


class Sidebar(Vertical):
    """Navigation sidebar with menu items."""

    CSS = """
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
    .menu-item.--selected {
        background: #1a1a2e;
        color: #00ff41;
        text-style: bold;
    }
    .sidebar-separator {
        margin: 1 1;
        height: 1;
        background: #30363d;
    }
    .sidebar-footer {
        dock: bottom;
        height: 3;
        padding: 0 1;
        color: #666;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Static("┌─ NAVIGATION ─┐", classes="sidebar-title")
        for i, (action_id, icon, label) in enumerate(MENU_ITEMS):
            btn = MenuButton(label, icon=icon, action_id=action_id,
                           id=f"menu-{action_id}", classes="menu-item")
            if i == 0:
                btn.selected = True
            yield btn
        yield Static("", classes="sidebar-separator")
        yield Static(" [Q]uit [/]Search\n [P]alette [T]heme", classes="sidebar-footer")

    def select_item(self, index: int):
        """Select a menu item by index."""
        if 0 <= index < len(MENU_ITEMS):
            # Deselect old
            old_btn = self.query_one(f"#menu-{MENU_ITEMS[self.selected_index][0]}", MenuButton)
            old_btn.set_selected(False)
            old_btn.remove_class("--selected")
            # Select new
            self.selected_index = index
            new_btn = self.query_one(f"#menu-{MENU_ITEMS[index][0]}", MenuButton)
            new_btn.set_selected(True)
            new_btn.add_class("--selected")
            return MENU_ITEMS[index][0]
        return None

    def get_selected_action(self) -> str:
        return MENU_ITEMS[self.selected_index][0]


class MainContent(ScrollableContainer):
    """Main content area that changes based on selected section."""

    CSS = """
    MainContent {
        background: #0d0d0d;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(id="content-area")

    def update_view(self, view_name: str, content):
        """Update the content area with new content."""
        area = self.query_one("#content-area", Static)
        area.update(content)


class DashboardLayout(Vertical):
    """Top-level dashboard layout."""

    CSS = """
    DashboardLayout {
        height: 100%;
    }
    #stats-bar {
        height: 1;
        background: #161b22;
        dock: top;
    }
    #main-area {
        height: 1fr;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        background: #161b22;
    }
    """

    def compose(self) -> ComposeResult:
        yield SystemStatsBar(id="stats-bar")
        with Horizontal(id="main-area"):
            yield Sidebar(id="sidebar")
            yield MainContent(id="main-content")
        yield StatusLine(id="status-bar")


def render_dashboard_view(stats: dict) -> str:
    """Render the main dashboard overview."""
    from rich.console import Console
    from rich.columns import Columns
    from io import StringIO

    console = Console(file=StringIO(), force_terminal=True, width=100)

    # System overview panel
    cpu = stats.get("cpu_percent", 0)
    ram = stats.get("ram_percent", 0)
    disk = stats.get("disk_percent", 0)

    cpu_bar = _make_bar(cpu, "green" if cpu < 60 else "yellow" if cpu < 85 else "red")
    ram_bar = _make_bar(ram, "green" if ram < 60 else "yellow" if ram < 85 else "red")
    disk_bar = _make_bar(disk, "green" if disk < 75 else "yellow" if disk < 90 else "red")

    overview = Table(show_header=False, box=None, padding=(0, 1))
    overview.add_column("metric", style="bold white", width=12)
    overview.add_column("bar", width=30)
    overview.add_column("value", style="bold", width=10)
    overview.add_row("CPU Usage", cpu_bar, f"{cpu:.1f}%")
    overview.add_row("RAM Usage", ram_bar, f"{ram:.1f}%")
    overview.add_row("Disk Usage", disk_bar, f"{disk:.1f}%")

    ram_total = stats.get("ram_total", 0) / (1024**3)
    ram_used = stats.get("ram_used", 0) / (1024**3)
    disk_free = stats.get("disk_free", 0) / (1024**3)

    overview.add_row("RAM", "", f"{ram_used:.1f}/{ram_total:.1f} GB")
    overview.add_row("Disk Free", "", f"{disk_free:.1f} GB")
    overview.add_row("Processes", "", str(stats.get("process_count", 0)))

    console.print(Panel(overview, title="[bold cyan]System Overview[/]",
                        border_style="cyan", padding=(1, 2)))

    # Quick actions panel
    actions = Text()
    actions.append("\n  [1] ", style="bold yellow")
    actions.append("Quick Clean           ", style="white")
    actions.append("[2] ", style="bold yellow")
    actions.append("Standard Clean\n", style="white")
    actions.append("  [3] ", style="bold yellow")
    actions.append("Deep Clean            ", style="white")
    actions.append("[4] ", style="bold yellow")
    actions.append("Scan Only\n", style="white")
    actions.append("  [5] ", style="bold yellow")
    actions.append("Browser Clean         ", style="white")
    actions.append("[6] ", style="bold yellow")
    actions.append("Registry Scan\n", style="white")
    actions.append("  [7] ", style="bold yellow")
    actions.append("Optimize RAM          ", style="white")
    actions.append("[8] ", style="bold yellow")
    actions.append("Network Diagnostics\n", style="white")

    console.print(Panel(actions, title="[bold cyan]Quick Actions[/]",
                        border_style="green", padding=(0, 1)))

    # Keyboard shortcuts
    shortcuts = Text()
    shortcuts.append("\n  ↑/↓  ", style="bold yellow")
    shortcuts.append("Navigate menu     ", style="white")
    shortcuts.append("Enter  ", style="bold yellow")
    shortcuts.append("Select/Execute\n", style="white")
    shortcuts.append("  /    ", style="bold yellow")
    shortcuts.append("Search            ", style="white")
    shortcuts.append("Ctrl+P ", style="bold yellow")
    shortcuts.append("Command Palette\n", style="white")
    shortcuts.append("  R    ", style="bold yellow")
    shortcuts.append("Refresh           ", style="white")
    shortcuts.append("T      ", style="bold yellow")
    shortcuts.append("Cycle Theme\n", style="white")
    shortcuts.append("  Q    ", style="bold yellow")
    shortcuts.append("Quit              ", style="white")
    shortcuts.append("?      ", style="bold yellow")
    shortcuts.append("Help\n", style="white")

    console.print(Panel(shortcuts, title="[bold cyan]Keyboard Shortcuts[/]",
                        border_style="magenta", padding=(0, 1)))

    return console.file.getvalue()


def render_cleaner_view(scan_results: dict | None = None) -> str:
    """Render the system cleaner view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    console.print(Panel(
        "[bold]System Cleaning Module[/]\n\n"
        "  Clean temporary files, caches, and system junk.\n"
        "  Safe mode enabled - critical files are protected.\n",
        title="[bold cyan]🧹 System Cleaner[/]",
        border_style="cyan",
    ))

    if scan_results:
        table = Table(title="Scan Results", border_style="green", expand=True)
        table.add_column("Category", style="cyan")
        table.add_column("Items", style="white", justify="right")
        table.add_column("Size", style="yellow", justify="right")
        table.add_column("Status", style="green")

        for cat, info in scan_results.get("categories", {}).items():
            size_str = _format_bytes(info.get("size", 0))
            table.add_row(cat, str(info.get("count", 0)), size_str, "● Ready")

        console.print(table)
        total = _format_bytes(scan_results.get("temp_size", 0))
        console.print(f"\n  [bold green]Total cleanable: {total}[/]")
    else:
        console.print("  [dim]Press [S] to scan or select a cleaning profile[/]")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [S] Scan  [C] Clean All  [1] Quick  [2] Standard  [3] Deep")

    return console.file.getvalue()


def render_process_view(processes: list[dict]) -> str:
    """Render the process manager view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    table = Table(title="Running Processes", border_style="cyan", expand=True)
    table.add_column("PID", style="white", width=8, justify="right")
    table.add_column("Name", style="cyan", width=25)
    table.add_column("CPU %", style="yellow", width=8, justify="right")
    table.add_column("Memory", style="green", width=12, justify="right")
    table.add_column("Mem %", style="green", width=8, justify="right")
    table.add_column("Status", width=10)
    table.add_column("Flags", width=10)

    for proc in processes[:40]:  # Show top 40
        flags = []
        if proc.get("is_system"):
            flags.append("[blue]SYS[/]")
        if proc.get("suspicious"):
            flags.append("[red]SUS[/]")
        if proc.get("is_heavy"):
            flags.append("[yellow]HVY[/]")

        mem_str = _format_bytes(proc.get("memory_bytes", 0))
        status_style = "green" if proc["status"] == "running" else "yellow"

        table.add_row(
            str(proc["pid"]),
            proc["name"][:25],
            f"{proc['cpu_percent']:.1f}",
            mem_str,
            f"{proc['memory_percent']:.1f}",
            f"[{status_style}]{proc['status']}[/]",
            " ".join(flags),
        )

    console.print(table)
    console.print(f"\n  Total: {len(processes)} processes")
    console.print("  [bold yellow]Actions:[/] [K] Kill  [R] Refresh  [S] Sort  [/] Search")

    return console.file.getvalue()


def render_network_view(connections: list[dict] | None = None,
                        ip_info: dict | None = None) -> str:
    """Render the network tools view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if ip_info:
        info_text = f"  Hostname: {ip_info.get('hostname', 'N/A')}\n"
        for iface in ip_info.get("interfaces", [])[:5]:
            if iface.get("is_up"):
                for addr in iface.get("addresses", []):
                    if addr.get("type") == "IPv4" and not addr["address"].startswith("127."):
                        info_text += f"  {iface['name']}: {addr['address']}\n"
        if "default_gateway" in ip_info:
            info_text += f"  Gateway: {ip_info['default_gateway']}\n"
        console.print(Panel(info_text, title="[bold cyan]🌍 Network Info[/]",
                           border_style="cyan"))

    if connections:
        table = Table(title="Active Connections", border_style="green", expand=True)
        table.add_column("PID", width=7, justify="right")
        table.add_column("Process", width=18)
        table.add_column("Local Address", width=22)
        table.add_column("Remote Address", width=22)
        table.add_column("Status", width=12)
        table.add_column("Type", width=5)

        for conn in connections[:30]:
            status_style = "green" if conn["status"] == "ESTABLISHED" else "yellow"
            table.add_row(
                str(conn["pid"]),
                conn["process"][:18],
                conn["local_address"],
                conn["remote_address"],
                f"[{status_style}]{conn['status']}[/]",
                conn["type"],
            )
        console.print(table)

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [F] Flush DNS  [D] Diagnostics  [P] Ping  [R] Refresh")

    return console.file.getvalue()


def render_startup_view(entries: list[dict]) -> str:
    """Render the startup manager view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    table = Table(title="Startup Programs", border_style="cyan", expand=True)
    table.add_column("#", width=4, justify="right")
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Status", width=10)
    table.add_column("Impact", width=10)
    table.add_column("Type", width=10)
    table.add_column("Flags", width=8)

    for i, entry in enumerate(entries):
        status = "[green]Enabled[/]" if entry.get("enabled") else "[red]Disabled[/]"
        impact_colors = {"low": "green", "medium": "yellow", "high": "red"}
        impact = entry.get("impact", "medium")
        impact_styled = f"[{impact_colors.get(impact, 'white')}]{impact.upper()}[/]"
        flags = "[red]⚠ SUS[/]" if entry.get("suspicious") else ""

        table.add_row(
            str(i + 1),
            entry["name"][:25],
            status,
            impact_styled,
            entry.get("type", ""),
            flags,
        )

    console.print(table)
    console.print(f"\n  Total: {len(entries)} startup entries")
    console.print("  [bold yellow]Actions:[/] [E] Enable  [D] Disable  [X] Remove  [R] Refresh")

    return console.file.getvalue()


def render_disk_view(disk_usage: dict | None = None,
                     large_files: list[dict] | None = None) -> str:
    """Render disk tools view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if disk_usage and "error" not in disk_usage:
        pct = disk_usage.get("percent_used", 0)
        bar = _make_bar(pct, "green" if pct < 75 else "yellow" if pct < 90 else "red")
        info = (
            f"  Total: {_format_bytes(disk_usage['total'])}  "
            f"Used: {_format_bytes(disk_usage['used'])}  "
            f"Free: {_format_bytes(disk_usage['free'])}"
        )
        console.print(Panel(f"{info}\n  {bar} {pct:.1f}%",
                           title="[bold cyan]💾 Disk Usage[/]", border_style="cyan"))

    if large_files:
        table = Table(title="Large Files", border_style="yellow", expand=True)
        table.add_column("#", width=4, justify="right")
        table.add_column("Name", style="cyan", width=35)
        table.add_column("Size", style="yellow", width=12, justify="right")
        table.add_column("Extension", width=8)
        table.add_column("Path", width=35)

        for i, f in enumerate(large_files[:20]):
            table.add_row(
                str(i + 1),
                f["name"][:35],
                _format_bytes(f["size"]),
                f.get("extension", ""),
                str(Path(f["path"]).parent)[:35] if "path" in f else "",
            )
        console.print(table)

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [A] Analyze Dir  [L] Large Files  [D] Duplicates  [E] Empty Folders  [X] Shred File")

    return console.file.getvalue()


def render_registry_view(invalid: list[dict] | None = None) -> str:
    """Render registry cleaner view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    console.print(Panel(
        "[bold]Registry Cleaner[/]\n\n"
        "  Scan and fix invalid registry entries.\n"
        "  Registry is backed up before any modifications.\n",
        title="[bold cyan]🗝️ Registry Cleaner[/]",
        border_style="cyan",
    ))

    if invalid:
        table = Table(title=f"Invalid Entries ({len(invalid)} found)",
                     border_style="yellow", expand=True)
        table.add_column("#", width=4, justify="right")
        table.add_column("Category", style="cyan", width=20)
        table.add_column("Entry", width=30)
        table.add_column("Issue", width=30)
        table.add_column("Risk", width=8)

        for i, entry in enumerate(invalid[:30]):
            risk = entry.get("risk", "low")
            risk_colors = {"low": "green", "medium": "yellow", "high": "red"}
            table.add_row(
                str(i + 1),
                entry.get("category", ""),
                entry.get("value_name", "")[:30],
                entry.get("issue", "")[:30],
                f"[{risk_colors.get(risk, 'white')}]{risk.upper()}[/]",
            )
        console.print(table)
    else:
        console.print("  [dim]Press [S] to scan the registry[/]")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [S] Scan  [F] Fix All  [B] Backup  [R] Restore")

    return console.file.getvalue()


def render_optimizer_view(services: list[dict] | None = None,
                          power_plans: list[dict] | None = None) -> str:
    """Render optimizer view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if services:
        table = Table(title="Optimizable Services", border_style="cyan", expand=True)
        table.add_column("#", width=4, justify="right")
        table.add_column("Service", style="cyan", width=35)
        table.add_column("Status", width=10)
        table.add_column("Start Type", width=12)
        table.add_column("Impact", width=8)
        table.add_column("Category", width=12)

        for i, svc in enumerate(services):
            status_style = "green" if svc["status"] == "running" else "red"
            impact_colors = {"low": "green", "medium": "yellow", "high": "red"}
            table.add_row(
                str(i + 1),
                svc["display_name"][:35],
                f"[{status_style}]{svc['status']}[/]",
                svc.get("start_type", ""),
                f"[{impact_colors.get(svc['impact'], 'white')}]{svc['impact'].upper()}[/]",
                svc.get("category", ""),
            )
        console.print(table)

    if power_plans:
        console.print("\n  [bold cyan]Power Plans:[/]")
        for plan in power_plans:
            active = " [green]◄ ACTIVE[/]" if plan.get("active") else ""
            console.print(f"    {plan.get('name', 'Unknown')}{active}")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [D] Disable Service  [E] Enable Service  [O] Optimize RAM  [P] Power Plan")

    return console.file.getvalue()


def render_privacy_view(telemetry: list[dict] | None = None,
                        tracking: list[dict] | None = None) -> str:
    """Render privacy & security view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if telemetry:
        table = Table(title="Telemetry Settings", border_style="cyan", expand=True)
        table.add_column("Setting", style="cyan", width=35)
        table.add_column("Status", width=12)
        table.add_column("Description", width=40)

        for t in telemetry:
            status = "[green]Disabled[/]" if not t["enabled"] else "[red]Enabled[/]"
            table.add_row(t["name"], status, t["description"])
        console.print(table)

    if tracking:
        console.print("\n  [bold cyan]Tracking Data Found:[/]")
        for loc in tracking:
            console.print(f"    {loc['category']}: {loc['files']} files "
                         f"({_format_bytes(loc['size'])})")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [T] Toggle Telemetry  [C] Clean Tracking  [S] Scan Suspicious  [X] Secure Delete")

    return console.file.getvalue()


def render_browser_view(browsers: list[dict] | None = None,
                        scan_result: dict | None = None) -> str:
    """Render browser cleaner view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if browsers:
        table = Table(title="Detected Browsers", border_style="cyan", expand=True)
        table.add_column("Browser", style="cyan", width=15)
        table.add_column("Profiles", width=10, justify="right")
        table.add_column("Cache Size", width=15, justify="right")
        table.add_column("Status", width=12)

        for b in browsers:
            table.add_row(
                b["display_name"],
                str(b["profiles"]),
                _format_bytes(b["cache_size"]),
                "[green]Installed[/]",
            )
        console.print(table)

    if scan_result:
        console.print(f"\n  [bold cyan]Scan: {scan_result['browser']}[/]")
        for cat in ["cache", "cookies", "history", "sessions"]:
            data = scan_result.get(cat, {})
            console.print(f"    {cat.capitalize()}: {data.get('count', 0)} items "
                         f"({_format_bytes(data.get('size', 0))})")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [S] Scan  [C] Clean Cache  [K] Clean Cookies  [H] Clean History  [A] Clean All")

    return console.file.getvalue()


def render_uninstaller_view(programs: list[dict] | None = None) -> str:
    """Render uninstaller view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if programs:
        table = Table(title=f"Installed Programs ({len(programs)})",
                     border_style="cyan", expand=True)
        table.add_column("#", width=5, justify="right")
        table.add_column("Name", style="cyan", width=30)
        table.add_column("Version", width=12)
        table.add_column("Publisher", width=20)
        table.add_column("Size", width=10, justify="right")

        for i, prog in enumerate(programs[:40]):
            size = _format_bytes(prog.get("size", 0) * 1024) if prog.get("size") else ""
            table.add_row(
                str(i + 1),
                prog["name"][:30],
                prog.get("version", "")[:12],
                prog.get("publisher", "")[:20],
                size,
            )
        if len(programs) > 40:
            console.print(f"  [dim]... and {len(programs) - 40} more (use search to filter)[/]")
        console.print(table)
    else:
        console.print("  [dim]Loading installed programs...[/]")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [U] Uninstall  [D] Deep Uninstall  [O] Orphaned  [B] Batch  [/] Search")

    return console.file.getvalue()


def render_scheduler_view(tasks: list[dict] | None = None,
                          profiles: dict | None = None) -> str:
    """Render scheduler view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if profiles:
        console.print(Panel(
            "\n".join(f"  {name}: {', '.join(k for k, v in p.items() if v)}"
                     for name, p in profiles.items()),
            title="[bold cyan]Cleaning Profiles[/]",
            border_style="cyan",
        ))

    if tasks:
        table = Table(title="Scheduled Tasks", border_style="green", expand=True)
        table.add_column("Name", style="cyan", width=20)
        table.add_column("Schedule", width=12)
        table.add_column("Profile", width=12)
        table.add_column("Status", width=12)
        table.add_column("Created", width=20)

        for task in tasks:
            status = "[green]Active[/]" if task.get("enabled") else "[red]Disabled[/]"
            table.add_row(
                task.get("name", ""),
                task.get("schedule", ""),
                task.get("profile", ""),
                status,
                task.get("created", "")[:19],
            )
        console.print(table)
    else:
        console.print("  [dim]No scheduled tasks configured[/]")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [N] New Task  [D] Delete Task  [T] Toggle  [P] New Profile")

    return console.file.getvalue()


def render_tracer_view(traces: dict | None = None,
                       summary: dict | None = None) -> str:
    """Render deep app tracer view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    console.print(Panel(
        "[bold]Deep Application Trace Analyzer[/]\n\n"
        "  Scan and remove all traces of a specific application.\n"
        "  Includes files, registry, services, tasks, and more.\n",
        title="[bold cyan]🔍 App Tracer[/]",
        border_style="cyan",
    ))

    if summary:
        console.print(f"\n  [bold green]Application: {summary['app_name']}[/]")
        console.print(f"  Total traces found: {summary['total_traces']}")
        console.print(f"    Files:           {summary['files']}")
        console.print(f"    Registry:        {summary['registry']}")
        console.print(f"    Services:        {summary['services']}")
        console.print(f"    Scheduled Tasks: {summary['scheduled_tasks']}")
        console.print(f"    Startup Entries: {summary['startup']}")
        console.print(f"    Processes:       {summary['processes']}")
        console.print(f"  Total size: {_format_bytes(summary['total_size'])}")

    if traces:
        for category, items in traces.items():
            if items:
                console.print(f"\n  [bold cyan]{category.upper()}:[/]")
                for i, item in enumerate(items[:10]):
                    path = item.get("path", item.get("name", "unknown"))
                    risk = item.get("risk", "low")
                    risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(risk, "white")
                    console.print(f"    [{risk_color}]●[/] {path}")
                if len(items) > 10:
                    console.print(f"    [dim]... and {len(items) - 10} more[/]")

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [A] Analyze App  [R] Remove Selected  [X] Deep Clean  [B] Backup First")

    return console.file.getvalue()


def render_logs_view(stats: dict | None = None,
                     recent_entries: list[dict] | None = None) -> str:
    """Render logs & reports view."""
    from rich.console import Console
    from io import StringIO
    console = Console(file=StringIO(), force_terminal=True, width=100)

    if stats:
        console.print(Panel(
            f"  Session Start:  {stats.get('session_start', 'N/A')}\n"
            f"  Duration:       {stats.get('duration_seconds', 0):.0f} seconds\n"
            f"  Total Freed:    {stats.get('total_freed_readable', '0 B')}\n"
            f"  Actions Taken:  {stats.get('actions_taken', 0)}\n"
            f"  Errors:         {stats.get('errors', 0)}",
            title="[bold cyan]📝 Session Statistics[/]",
            border_style="cyan",
        ))

    if recent_entries:
        table = Table(title="Recent Log Entries", border_style="green", expand=True)
        table.add_column("Time", width=12)
        table.add_column("Category", style="cyan", width=12)
        table.add_column("Action", width=20)
        table.add_column("Details", width=40)
        table.add_column("OK", width=4)

        for entry in recent_entries[-20:]:
            ts = entry.get("timestamp", "")[-8:]  # HH:MM:SS
            ok = "[green]✓[/]" if entry.get("success") else "[red]✗[/]"
            table.add_row(
                ts,
                entry.get("category", ""),
                entry.get("action", ""),
                entry.get("details", "")[:40],
                ok,
            )
        console.print(table)

    console.print("\n  [bold yellow]Actions:[/]")
    console.print("  [T] Export TXT  [J] Export JSON  [C] Clear Log  [R] Refresh")

    return console.file.getvalue()


def _make_bar(percent: float, color: str, width: int = 25) -> str:
    """Create a text-based progress bar."""
    filled = int(percent / 100 * width)
    empty = width - filled
    return f"[{color}]{'█' * filled}{'░' * empty}[/]"


def _format_bytes(b: int) -> str:
    """Format bytes to human readable."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


# Need Path for disk view
from pathlib import Path
