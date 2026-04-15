# System Cleaner

System Cleaner is a comprehensive and powerful tool for cleaning, optimizing, and managing your system. It provides a feature-rich Textual User Interface (TUI) for interactive use, a command-line interface (CLI) for scripting, and a silent mode for automated tasks.

## Features

- **Comprehensive Cleaning:** Cleans temporary files, browser data, system caches, and more.
- **Advanced Tools:** Includes an uninstaller, startup manager, disk analyzer, and registry cleaner.
- **Optimization:** Provides tools to optimize system services, RAM usage, and power settings.
- **Privacy and Security:** Helps manage telemetry, remove tracking files, and identify suspicious processes.
- **Extensible:** Supports custom plugins and themes.
- **Multiple Interfaces:** Can be run with a full TUI, via CLI, or silently in the background.

## Project Structure

```
system_cleaner/
├── main.py                     # Entry point (TUI, CLI, silent mode)
├── app.py                      # Main Textual application (keyboard nav, views)
├── config.json                 # Configuration & cleaning profiles
├── requirements.txt            # Python dependencies
├── core/                       # Core logic layer
│   ├── cleaner.py              # System cleaning (temp, DNS, recycle bin, etc.)
│   ├── browser.py              # Browser cleaning (Chrome, Edge, Firefox)
│   ├── uninstaller.py          # Advanced uninstaller (silent, deep, batch)
│   ├── startup.py              # Startup manager (enable/disable/detect)
│   ├── disk.py                 # Disk tools (analyze, duplicates, shredder)
│   ├── registry.py             # Registry cleaner (scan, fix, backup/restore)
│   ├── optimizer.py            # System optimization (services, RAM, power)
│   ├── privacy.py              # Privacy & security (telemetry, tracking)
│   ├── process.py              # Process manager (list, kill, suspicious)
│   ├── network.py              # Network tools (connections, ping, diag)
│   ├── scheduler.py            # Task scheduler & cleaning profiles
│   ├── tracer.py               # Deep application trace analyzer
│   └── logger.py               # Logging system (TXT/JSON export, reports)
├── ui/                         # UI layer
│   ├── dashboard.py            # View renderers for all 14 sections
│   ├── dialogs.py              # Modal dialogs (confirm, search, command palette)
│   └── widgets.py              # Custom widgets (stats bar, risk indicator, etc.)
├── plugins/                    # Plugin system
│   ├── __init__.py             # Plugin manager (discover, load, register)
│   └── example_plugin.py       # Example plugin template
└── themes/                     # Theme system
    └── __init__.py             # 5 themes (cyberpunk, matrix, midnight, blood, arctic)
```

## Installation

1.  Navigate to the project directory:
    ```bash
    cd system_cleaner
    ```

2.  Install the required Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

The application can be launched in several modes from the `system_cleaner` directory.

### TUI Mode

To launch the full Textual User Interface:
```bash
python main.py
```

### CLI Mode

Use the `--cli` flag for command-line operations.

- **Scan system:**
  ```bash
  python main.py --cli scan
  ```
- **Run standard clean:**
  ```bash
  python main.py --cli clean
  ```
- **List top processes:**
  ```bash
  python main.py --cli processes
  ```
- **Show network info:**
  ```bash
  python main.py --cli network
  ```
- **Detect browsers:**
  ```bash
  python main.py --cli browsers
  ```
- **Generate report:**
  ```bash
  python main.py --cli report
  ```

### Silent Mode

Silent mode runs tasks without any UI, which is ideal for scheduled cleaning.

- **Run default silent clean:**
  ```bash
  python main.py --silent
  ```
- **Run a specific cleaning profile (e.g., 'deep'):**
  ```bash
  python main.py --silent --profile deep
  ```

## Modules in Detail

| #  | Module            | Features                                                                          |
|----|-------------------|-----------------------------------------------------------------------------------|
| 1  | System Cleaner    | %TEMP%, Prefetch, WU cache, DNS, thumbnails, clipboard, recycle bin.              |
| 2  | Browser Cleaner   | Chrome/Edge/Firefox - cache, cookies, history, sessions per profile.              |
| 3  | Uninstaller       | List/search programs, silent uninstall, deep clean leftovers, orphan detection, batch. |
| 4  | Startup Manager   | View/enable/disable/remove entries, impact levels, suspicious detection.          |
| 5  | Disk Tools        | Usage analyzer, large files, SHA-256 duplicate finder, empty folders, DoD shredder. |
| 6  | Registry Cleaner  | Scan SharedDLLs/AppPaths/associations/uninstall, backup/restore, risk levels.     |
| 7  | Optimizer         | 12 optional services, power plan switcher, RAM optimization, live CPU/RAM stats.    |
| 8  | Privacy           | 5 telemetry toggles, tracking file removal, suspicious file heuristic scanner.    |
| 9  | Process Manager   | List/kill processes, CPU/RAM stats, suspicious process detection (name mimicry).  |
| 10 | Network Tools     | Active connections, DNS flush, IP info, ping, 4-step diagnostics.                 |
| 11 | Scheduler         | Windows Task Scheduler integration, custom cleaning profiles.                     |
| 12 | Logs & Reports    | Structured logging, TXT/JSON export, session statistics.                          |
| 13 | App Tracer        | Deep scan (files/registry/services/tasks/startup/processes), heuristic matching, deep clean. |

## Configuration

The application's behavior and cleaning profiles can be configured in the `config.json` file. This includes settings for each module, theme selection, and custom cleaning jobs.

## Plugins and Theming

The `plugins/` directory contains the plugin system, allowing for the extension of core functionality. An example plugin is provided in `example_plugin.py`.

The `themes/` directory manages the visual appearance of the TUI. The application includes several built-in themes.

## License

This project is unlicensed.
