# System Cleaner

A Windows system maintenance tool with a pure ANSI terminal interface. Cleans junk files, manages processes and startup entries, monitors applications, analyzes disk usage, and more — all from a keyboard-driven menu.

## Requirements

- Windows 10 / 11
- Python 3.10+
- Admin rights recommended (required for some features)

## Installation

```bash
pip install -r requirements.txt
python main.py
```

## Menu

The main menu is organized into five categories:

### Cleaning
| # | Feature | Description |
|---|---------|-------------|
| 1 | System Scan | Scan for temp files, WU cache, DNS cache, thumbnails, and more — shows sizes before cleaning |
| 2 | Quick Clean | Removes temporary files and empties the recycle bin |
| 3 | Standard Clean | Quick + browser caches, prefetch, DNS flush |
| 4 | Deep Clean | Standard + Windows Update cache, log files, thumbnail cache |
| 5 | Team Clean | All-in-one: deep system + all browsers + privacy tracking files |

### File Tools
| # | Feature | Description |
|---|---------|-------------|
| 6 | Duplicate Files | Two-pass SHA-1 scan — groups duplicates, shows wasted space, delete individually or all at once |
| 7 | Large Files | Find files above a configurable size threshold, sorted largest first |
| 8 | Empty Folders | Detect and remove empty directories recursively |
| 9 | Secure Wipe | Multi-pass overwrite (zeros → 0xFF → random) before deletion — files cannot be recovered |

### Tools
| # | Feature | Description |
|---|---------|-------------|
| 10 | Browser Tools | Clean cache, cookies, and history for Chrome, Edge, and Firefox |
| 11 | Process Manager | List running processes with CPU/RAM stats, kill processes, detect name-mimicry |
| 12 | Network Tools | Active connections, DNS flush, IP info, ping, connectivity diagnostics |
| 13 | Startup Manager | View, enable, disable, or remove startup entries with impact levels |
| 14 | Disk Tools | Disk usage breakdown by folder, largest directories |
| 15 | Registry Cleaner | Scan SharedDLLs, AppPaths, file associations, and uninstall entries; backup/restore |
| 16 | Optimizer | Trim RAM across all running processes, manage optional services, switch power plans |
| 17 | Privacy & Security | Toggle Windows telemetry, scan and remove tracking files |
| 18 | Uninstaller | Uninstall programs or built-in Windows apps (Teams, Xbox, Cortana…) |
| 19 | Autoruns | Full autorun view: Run keys, Winlogon, shell extensions, scheduled tasks — enable/disable |
| 20 | Context Menu | Inspect, disable, or delete right-click context menu entries from the registry |

### Monitoring
| # | Feature | Description |
|---|---------|-------------|
| 21 | App Tracer | Track file, registry, and process activity of any app in real-time; save sessions |
| 22 | Scout Mode | Deep monitoring: file I/O, downloads, network connections, registry changes, spawned processes |
| 23 | System Health | Composite health score (0–100, A–F) across CPU, RAM, disk, startup load, and uptime |
| 24 | Crash Logs | Read critical/error events from Windows Event Log, BSOD history, and minidump files |

### System
| # | Feature | Description |
|---|---------|-------------|
| 25 | History Manager | View and selectively delete network connection history, USB device history, and app launch history |
| 26 | Restore Points | List, create, and delete Windows System Restore points |
| 27 | Scheduler | Create scheduled cleaning tasks (daily/weekly/hourly) |
| 28 | Logs & Reports | Session stats, export to TXT or JSON |
| 29 | Language | Switch between English and Czech; setting saved to `config.json` |

## Project Structure

```
cc/
├── main.py             # Entry point
├── app.py              # All menus and UI logic (pure ANSI terminal)
├── config.json         # Cleaning profiles and language setting
├── requirements.txt
├── locales/
│   ├── en.json         # English strings
│   └── cs.json         # Czech strings
├── core/
│   ├── i18n.py         # Translation layer (t(), set_language(), available_languages())
│   ├── logger.py       # Session logger with TXT/JSON export
│   ├── cleaner.py      # System cleaning (temp, WU cache, DNS, prefetch, recycle bin)
│   ├── browser.py      # Browser cleaning (Chrome, Edge, Firefox)
│   ├── process.py      # Process listing, kill, suspicious detection
│   ├── network.py      # Network connections, DNS, ping, diagnostics
│   ├── startup.py      # Startup entry manager
│   ├── disk.py         # Disk usage analysis
│   ├── registry.py     # Registry scan, backup, restore
│   ├── optimizer.py    # RAM optimization, services, power plans
│   ├── privacy.py      # Telemetry toggles, tracking file removal
│   ├── uninstaller.py  # Program and built-in app uninstaller
│   ├── scheduler.py    # Task scheduler integration
│   ├── tracer.py       # Static app trace scanner
│   ├── tracer_session.py # Live app tracing (watchdog-based)
│   ├── scout.py        # Scout Mode — deep real-time monitoring
│   ├── health.py       # System health scoring
│   ├── history.py      # Network, USB, and app launch history
│   ├── restore.py      # System Restore point manager
│   ├── crashlog.py     # Windows Event Log and minidump reader
│   ├── autoruns.py     # Comprehensive autorun entry manager
│   ├── contextmenu.py  # Context menu entry manager
│   ├── duplicates.py   # Duplicate file finder (SHA-1, two-pass)
│   ├── largefile.py    # Large file finder
│   ├── emptyfolders.py # Empty folder finder and cleaner
│   └── securewipe.py   # Multi-pass secure file wipe
├── profiles/           # Saved tracer and scout session files (JSON)
└── logs/               # Exported session logs
```

## Notes

- **Admin rights** are required for RAM optimization (trims all process working sets), service management, system restore point creation, and registry writes outside HKCU.
- **Secure Wipe** overwrites file content before deletion. It cannot recover files deleted through normal means.
- **Scout Mode** uses `watchdog` for filesystem monitoring and `psutil` for process/network polling. It saves sessions to `profiles/scout_*.json`.
- **Language** defaults to English. Switch to Czech via option 29; the setting persists in `config.json`.

## License

Unlicensed.
