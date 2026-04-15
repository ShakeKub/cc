"""Dialog screens for confirmations, search, command palette."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Center
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, Label
from rich.text import Text
from rich.panel import Panel


class ConfirmDialog(ModalScreen[bool]):
    """Confirmation dialog for dangerous operations."""

    CSS = """
    ConfirmDialog {
        align: center middle;
    }
    #confirm-dialog {
        width: 60;
        height: auto;
        max-height: 20;
        background: $surface;
        border: thick $error;
        padding: 1 2;
    }
    #confirm-title {
        text-align: center;
        color: $error;
        text-style: bold;
        margin-bottom: 1;
    }
    #confirm-message {
        margin-bottom: 1;
    }
    #confirm-risk {
        text-align: center;
        margin-bottom: 1;
    }
    #confirm-buttons {
        align: center middle;
        height: 3;
    }
    #confirm-buttons Button {
        margin: 0 2;
    }
    """

    def __init__(self, title: str, message: str, risk_level: str = "medium"):
        super().__init__()
        self.title_text = title
        self.message_text = message
        self.risk_level = risk_level

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(f"⚠ {self.title_text}", id="confirm-title")
            yield Static(self.message_text, id="confirm-message")
            risk_colors = {"low": "green", "medium": "yellow", "high": "red"}
            color = risk_colors.get(self.risk_level, "white")
            yield Static(
                Text(f"Risk Level: {self.risk_level.upper()}", style=f"bold {color}"),
                id="confirm-risk",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirm", variant="error", id="btn-confirm")
                yield Button("Cancel", variant="primary", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "btn-confirm")


class SearchDialog(ModalScreen[str]):
    """Search input dialog."""

    CSS = """
    SearchDialog {
        align: center middle;
    }
    #search-dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #search-title {
        text-align: center;
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    #search-input {
        margin-bottom: 1;
    }
    """

    def __init__(self, title: str = "Search", placeholder: str = "Type to search..."):
        super().__init__()
        self.title_text = title
        self.placeholder_text = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Static(f"🔍 {self.title_text}", id="search-title")
            yield Input(placeholder=self.placeholder_text, id="search-input")

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)

    def key_escape(self):
        self.dismiss("")


class InputDialog(ModalScreen[str]):
    """Generic text input dialog."""

    CSS = """
    InputDialog {
        align: center middle;
    }
    #input-dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #input-title {
        text-align: center;
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    #input-field {
        margin-bottom: 1;
    }
    #input-buttons {
        align: center middle;
        height: 3;
    }
    """

    def __init__(self, title: str, prompt: str, default: str = ""):
        super().__init__()
        self.title_text = title
        self.prompt_text = prompt
        self.default_value = default

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Static(self.title_text, id="input-title")
            yield Static(self.prompt_text)
            yield Input(value=self.default_value, id="input-field")
            with Horizontal(id="input-buttons"):
                yield Button("OK", variant="primary", id="btn-ok")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-ok":
            input_widget = self.query_one("#input-field", Input)
            self.dismiss(input_widget.value)
        else:
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)

    def key_escape(self):
        self.dismiss("")


class TracerDialog(ModalScreen[tuple[str, str]]):
    """Dialog to start/stop tracing an application."""

    CSS = """
    TracerDialog {
        align: center middle;
    }
    #tracer-dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $secondary;
        padding: 1 2;
    }
    #tracer-title {
        text-align: center;
        color: $secondary;
        text-style: bold;
        margin-bottom: 1;
    }
    #tracer-input {
        margin-bottom: 1;
    }
    #tracer-buttons {
        align: center middle;
        height: 3;
    }
    """

    def __init__(self, is_tracing: bool = False, app_name: str = ""):
        super().__init__()
        self.is_tracing = is_tracing
        self.app_name = app_name

    def compose(self) -> ComposeResult:
        with Vertical(id="tracer-dialog"):
            yield Static("🔍 Application Tracer", id="tracer-title")
            if self.is_tracing:
                yield Static(f"Currently tracing: [bold]{self.app_name}[/bold]")
                with Horizontal(id="tracer-buttons"):
                    yield Button("Stop Tracing", variant="error", id="btn-stop")
                    yield Button("Cancel", variant="primary", id="btn-cancel")
            else:
                yield Input(placeholder="Enter application name to trace...", id="tracer-input")
                with Horizontal(id="tracer-buttons"):
                    yield Button("Start Tracing", variant="success", id="btn-start")
                    yield Button("Cancel", variant="primary", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-start":
            app_name = self.query_one("#tracer-input", Input).value
            if app_name:
                self.dismiss(("start", app_name))
        elif event.button.id == "btn-stop":
            self.dismiss(("stop", self.app_name))
        else:
            self.dismiss(("", ""))

    def on_input_submitted(self, event: Input.Submitted):
        if event.value:
            self.dismiss(("start", event.value))

    def key_escape(self):
        self.dismiss(("", ""))


class CommandPalette(ModalScreen[str]):
    """VS Code-style command palette."""

    CSS = """
    CommandPalette {
        align: center top;
        padding-top: 3;
    }
    #palette {
        width: 70;
        height: auto;
        max-height: 25;
        background: $surface;
        border: thick $accent;
        padding: 1;
    }
    #palette-input {
        margin-bottom: 1;
    }
    #palette-results {
        height: auto;
        max-height: 18;
        overflow-y: auto;
    }
    .palette-item {
        padding: 0 1;
        height: 1;
    }
    .palette-item:hover {
        background: $primary 20%;
    }
    """

    COMMANDS = [
        ("clean:quick", "Run quick clean"),
        ("clean:standard", "Run standard clean"),
        ("clean:deep", "Run deep clean"),
        ("scan:system", "Scan system for issues"),
        ("scan:browser", "Scan browser data"),
        ("scan:registry", "Scan registry for invalid entries"),
        ("scan:disk", "Analyze disk usage"),
        ("scan:duplicates", "Find duplicate files"),
        ("process:list", "List running processes"),
        ("network:connections", "Show active connections"),
        ("network:diagnostics", "Run network diagnostics"),
        ("network:ping", "Ping a host"),
        ("startup:list", "List startup programs"),
        ("optimizer:services", "Show optimizable services"),
        ("optimizer:ram", "Optimize RAM usage"),
        ("privacy:telemetry", "View telemetry settings"),
        ("privacy:tracking", "Scan tracking files"),
        ("trace:analyze", "Deep application trace analysis"),
        ("export:txt", "Export log as TXT"),
        ("export:json", "Export log as JSON"),
        ("theme:cycle", "Cycle through themes"),
        ("about", "About System Cleaner"),
        ("quit", "Exit application"),
    ]

    def __init__(self):
        super().__init__()
        self.filtered_commands = list(self.COMMANDS)

    def compose(self) -> ComposeResult:
        with Vertical(id="palette"):
            yield Input(placeholder="Type a command...", id="palette-input")
            with Vertical(id="palette-results"):
                for cmd_id, description in self.COMMANDS[:15]:
                    yield Static(
                        f"  {cmd_id:<30} {description}",
                        classes="palette-item",
                    )

    def on_input_changed(self, event: Input.Changed):
        query = event.value.lower()
        results_container = self.query_one("#palette-results")
        results_container.remove_children()
        self.filtered_commands = [
            (cid, desc) for cid, desc in self.COMMANDS
            if query in cid.lower() or query in desc.lower()
        ]
        for cmd_id, description in self.filtered_commands[:15]:
            results_container.mount(
                Static(f"  {cmd_id:<30} {description}", classes="palette-item")
            )

    def on_input_submitted(self, event: Input.Submitted):
        if self.filtered_commands:
            self.dismiss(self.filtered_commands[0][0])
        else:
            self.dismiss("")

    def key_escape(self):
        self.dismiss("")
