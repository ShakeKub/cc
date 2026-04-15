"""Custom Textual widgets for the System Cleaner UI."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, ProgressBar, Label
from textual.widget import Widget
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import Group


ASCII_HEADER = r"""
 ███████╗██╗   ██╗███████╗     ██████╗██╗     ███████╗ █████╗ ███╗   ██╗███████╗██████╗
 ██╔════╝╚██╗ ██╔╝██╔════╝    ██╔════╝██║     ██╔════╝██╔══██╗████╗  ██║██╔════╝██╔══██╗
 ███████╗ ╚████╔╝ ███████╗    ██║     ██║     █████╗  ███████║██╔██╗ ██║█████╗  ██████╔╝
 ╚════██║  ╚██╔╝  ╚════██║    ██║     ██║     ██╔══╝  ██╔══██║██║╚██╗██║██╔══╝  ██╔══██╗
 ███████║   ██║   ███████║    ╚██████╗███████╗███████╗██║  ██║██║ ╚████║███████╗██║  ██║
 ╚══════╝   ╚═╝   ╚══════╝     ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝
"""


class HeaderBanner(Static):
    """ASCII art header banner."""

    def render(self):
        text = Text(ASCII_HEADER, style="bold green")
        subtitle = Text("  System Cleaner & Optimization Tool v1.0", style="cyan")
        return Group(text, subtitle)


class SystemStatsBar(Static):
    """Live system stats display bar."""

    cpu_percent: reactive[float] = reactive(0.0)
    ram_percent: reactive[float] = reactive(0.0)
    disk_percent: reactive[float] = reactive(0.0)

    def render(self):
        # Color coding based on usage levels
        cpu_color = "green" if self.cpu_percent < 60 else "yellow" if self.cpu_percent < 85 else "red"
        ram_color = "green" if self.ram_percent < 60 else "yellow" if self.ram_percent < 85 else "red"
        disk_color = "green" if self.disk_percent < 75 else "yellow" if self.disk_percent < 90 else "red"

        text = Text()
        text.append(" CPU: ", style="bold white")
        text.append(f"{self.cpu_percent:5.1f}%", style=f"bold {cpu_color}")
        text.append(f" {'█' * int(self.cpu_percent / 5)}{'░' * (20 - int(self.cpu_percent / 5))} ",
                    style=cpu_color)
        text.append("│ RAM: ", style="bold white")
        text.append(f"{self.ram_percent:5.1f}%", style=f"bold {ram_color}")
        text.append(f" {'█' * int(self.ram_percent / 5)}{'░' * (20 - int(self.ram_percent / 5))} ",
                    style=ram_color)
        text.append("│ DISK: ", style="bold white")
        text.append(f"{self.disk_percent:5.1f}%", style=f"bold {disk_color}")
        text.append(f" {'█' * int(self.disk_percent / 5)}{'░' * (20 - int(self.disk_percent / 5))} ",
                    style=disk_color)
        return text


class RiskIndicator(Static):
    """Color-coded risk level indicator."""

    level: reactive[str] = reactive("safe")

    RISK_STYLES = {
        "safe": ("green", "SAFE"),
        "low": ("green", "LOW"),
        "medium": ("yellow", "MEDIUM"),
        "high": ("red", "HIGH"),
        "critical": ("red bold", "CRITICAL"),
    }

    def render(self):
        style, label = self.RISK_STYLES.get(self.level, ("white", "UNKNOWN"))
        return Text(f" ● {label} ", style=style)


class StatusLine(Static):
    """Status line with colored indicators."""

    message: reactive[str] = reactive("")
    status_type: reactive[str] = reactive("info")

    STATUS_STYLES = {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "working": "magenta",
    }

    def render(self):
        style = self.STATUS_STYLES.get(self.status_type, "white")
        prefix_map = {
            "info": "[i]",
            "success": "[+]",
            "warning": "[!]",
            "error": "[x]",
            "working": "[~]",
        }
        prefix = prefix_map.get(self.status_type, "[?]")
        return Text(f" {prefix} {self.message}", style=style)


class MenuButton(Static):
    """Styled sidebar menu button."""

    def __init__(self, label: str, icon: str = ">", action_id: str = "", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.icon = icon
        self.action_id = action_id
        self.selected = False

    def render(self):
        style = "bold cyan on #1a1a2e" if self.selected else "white"
        prefix = "▶ " if self.selected else "  "
        return Text(f"{prefix}{self.icon} {self.label_text}", style=style)

    def set_selected(self, selected: bool):
        self.selected = selected
        self.refresh()


class InfoPanel(Static):
    """Information panel with title and content."""

    def __init__(self, title: str = "", content: str = "", panel_style: str = "cyan", **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.content_text = content
        self.panel_style = panel_style

    def render(self):
        return Panel(
            Text(self.content_text),
            title=self.title_text,
            border_style=self.panel_style,
        )

    def update_content(self, content: str, title: str | None = None):
        self.content_text = content
        if title is not None:
            self.title_text = title
        self.refresh()


class DataTable(Static):
    """Rich data table display."""

    def __init__(self, title: str = "", **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.columns: list[tuple[str, str]] = []
        self.rows: list[list[str]] = []

    def set_data(self, columns: list[tuple[str, str]], rows: list[list[str]]):
        """Set table data. columns: list of (name, style) tuples."""
        self.columns = columns
        self.rows = rows
        self.refresh()

    def render(self):
        table = Table(title=self.title_text, border_style="cyan",
                      show_header=True, header_style="bold magenta",
                      expand=True)
        for col_name, col_style in self.columns:
            table.add_column(col_name, style=col_style)
        for row in self.rows:
            table.add_row(*row)
        return table


class TreeView(Static):
    """Tree structure display for directory/registry visualization."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tree_data: list[dict] = []

    def set_data(self, data: list[dict]):
        """Set tree data. Each item: {name, size, depth, type}."""
        self.tree_data = data
        self.refresh()

    def render(self):
        lines = []
        for item in self.tree_data[:50]:  # Limit display
            depth = item.get("depth", 0)
            indent = "  " * depth
            connector = "├── " if depth > 0 else ""
            icon = "📁" if item.get("type") == "directory" else "📄"
            name = item.get("name", "unknown")
            size = item.get("size", 0)
            size_str = _format_size(size) if size > 0 else ""

            line = f"{indent}{connector}{icon} {name}"
            if size_str:
                line += f"  ({size_str})"
            lines.append(line)

        if len(self.tree_data) > 50:
            lines.append(f"\n  ... and {len(self.tree_data) - 50} more items")

        return Text("\n".join(lines) if lines else "No data", style="white")


def _format_size(size_bytes: int) -> str:
    """Format bytes to human readable."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
