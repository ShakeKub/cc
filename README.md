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

The main menu is organized into five categories across 43 options.

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
| 6 | Duplicate Files | Two-pass SHA-1 scan — groups duplicates, shows wasted space, delete individually or in bulk |
| 7 | Large Files | Find files above a configurable threshold, sorted largest first, arrow-key pagination |
| 8 | Empty Folders | Detect and remove empty directories recursively |
| 9 | Secure Wipe | Multi-pass overwrite (zeros → 0xFF → random) before deletion — unrecoverable |
| 10 | File Recovery | Restore files from Recycle Bin or VSS shadow copies |
| 35 | Font Manager | List all installed fonts, view file sizes, delete unused ones |
| 36 | Shortcut Fixer | Scan Desktop and Start Menu for broken .lnk files, delete them |
| 37 | MSI Cache Cleaner | Find orphaned installer files in `C:\Windows\Installer` and reclaim disk space |

### Tools
| # | Feature | Description |
|---|---------|-------------|
| 11 | Browser Tools | Clean cache, cookies, and history for Chrome, Edge, and Firefox |
| 12 | Process Manager | List running processes with CPU/RAM stats, kill processes, detect name-mimicry |
| 13 | Network Tools | Active connections, DNS flush, IP info, ping, connectivity diagnostics |
| 14 | Startup Manager | View, enable, disable, or remove startup entries with impact levels |
| 15 | Disk Tools | Disk usage breakdown by folder, largest directories |
| 16 | Registry Cleaner | Scan SharedDLLs, AppPaths, file associations, and uninstall entries; backup/restore |
| 17 | Optimizer | Trim RAM across all running processes, manage optional services, switch power plans |
| 18 | Privacy & Security | Toggle Windows telemetry, scan and remove tracking files |
| 19 | Uninstaller | Uninstall programs or built-in Windows apps (Teams, Xbox, Cortana…); bulk bloatware removal |
| 20 | Autoruns | Full autorun view: Run keys, Winlogon, shell extensions, scheduled tasks — enable/disable |
| 21 | Context Menu | Inspect, disable, or delete right-click context menu entries from the registry |
| 32 | Performance Boost | One-click speed-up: kill bloat apps, trim RAM, High Performance power plan, disable animations, stop heavy services |
| 33 | Environment Variables | View and edit user and system environment variables; broadcasts changes live |
| 34 | Firewall Rules | List, toggle, and delete Windows Firewall rules filtered by direction and state |

### Monitoring
| # | Feature | Description |
|---|---------|-------------|
| 22 | App Tracer | Track file, registry, and process activity of any app in real-time; save sessions |
| 23 | Scout Mode | Deep monitoring: file I/O, downloads, network connections, registry changes, spawned processes |
| 24 | System Health | Composite health score (0–100, A–F) across CPU, RAM, disk, startup load, and uptime |
| 25 | Crash Logs | Read critical/error events from Windows Event Log, BSOD history, and minidump files |
| 26 | Disk Health | Physical disk info, SMART counters (temperature, wear, errors), partition usage bars |
| 38 | System Info | Full hardware snapshot — CPU, RAM sticks, GPU, disks, network adapters — with file export |
| 39 | Network Speed Test | Ping latency (3 servers), DNS resolution timing, 10 MB download speed test |

### System
| # | Feature | Description |
|---|---------|-------------|
| 27 | History Manager | View and delete network connection history, USB device history, and app launch history (last 3 days) |
| 28 | Restore Points | List, create, and delete Windows System Restore points |
| 29 | Scheduler | Create scheduled cleaning tasks (daily/weekly/hourly) |
| 30 | Logs & Reports | Session stats, export to TXT or JSON |
| 31 | Language | Switch between English and Czech; setting saved to `config.json` |
| 40 | Windows Update | List installed updates, check for pending, pause (7/14/35 days), resume, trigger scan |
| 41 | DNS & Hosts Editor | Flush DNS cache, view/add/delete hosts file entries, view cached DNS records |
| 42 | Ad Blocker | Hosts-based ad and tracker blocking — 80+ domains, toggle on/off, no external downloads |
| 43 | Wake-on-LAN | Send magic packets to saved or ad-hoc MAC addresses via UDP broadcast |

## Multi-select

Every list-based menu accepts comma-separated item numbers: `d 1,3,5` deletes items 1, 3, and 5. Use `all` where available to act on everything at once.

## Project Structure

```
cc/
├── main.py               # Entry point
├── app.py                # All menus and UI logic (pure ANSI terminal)
├── config.json           # Cleaning profiles and language setting
├── requirements.txt
├── wol_devices.json      # Saved Wake-on-LAN devices (auto-created)
├── locales/
│   ├── en.json           # English strings
│   └── cs.json           # Czech strings
├── core/
│   ├── i18n.py           # Translation layer (t(), set_language(), available_languages())
│   ├── logger.py         # Session logger with TXT/JSON export
│   ├── cleaner.py        # System cleaning (temp, WU cache, DNS, prefetch, recycle bin)
│   ├── browser.py        # Browser cleaning (Chrome, Edge, Firefox)
│   ├── process.py        # Process listing, kill, suspicious detection
│   ├── network.py        # Network connections, DNS, ping, diagnostics
│   ├── startup.py        # Startup entry manager
│   ├── disk.py           # Disk usage analysis
│   ├── registry.py       # Registry scan, backup, restore
│   ├── optimizer.py      # RAM optimization, services, power plans
│   ├── privacy.py        # Telemetry toggles, tracking file removal
│   ├── uninstaller.py    # Program and built-in app uninstaller
│   ├── scheduler.py      # Task scheduler integration
│   ├── tracer.py         # Static app trace scanner
│   ├── tracer_session.py # Live app tracing (watchdog-based)
│   ├── scout.py          # Scout Mode — deep real-time monitoring
│   ├── health.py         # System health scoring
│   ├── history.py        # Network, USB, and app launch history
│   ├── restore.py        # System Restore point manager
│   ├── crashlog.py       # Windows Event Log and minidump reader
│   ├── autoruns.py       # Comprehensive autorun entry manager
│   ├── contextmenu.py    # Context menu entry manager
│   ├── duplicates.py     # Duplicate file finder (SHA-1, two-pass)
│   ├── largefile.py      # Large file finder
│   ├── emptyfolders.py   # Empty folder finder and cleaner
│   ├── securewipe.py     # Multi-pass secure file wipe
│   ├── recovery.py       # Recycle Bin and VSS shadow copy recovery
│   ├── diskhealth.py     # Physical disk SMART data reader
│   ├── perfboost.py      # One-click performance optimization
│   ├── dnstools.py       # DNS flush and hosts file editor
│   ├── winupdate.py      # Windows Update manager
│   ├── envvars.py        # Environment variables editor
│   ├── fontmgr.py        # Font manager
│   ├── shortcutfix.py    # Broken shortcut scanner and fixer
│   ├── msicache.py       # MSI installer cache orphan finder
│   ├── firewall.py       # Windows Firewall rule manager
│   ├── sysinfo.py        # Full system info snapshot and export
│   ├── wol.py            # Wake-on-LAN magic packet sender
│   ├── adblocker.py      # Hosts-based ad and tracker blocker
│   └── netspeed.py       # Network speed test (ping, DNS, download)
├── profiles/             # Saved tracer and scout session files (JSON)
└── logs/                 # Exported session logs
```

## Notes

- **Admin rights** are required for RAM optimization, service management, system restore points, registry writes outside HKCU, editing the hosts file, and firewall rule changes.
- **Ad Blocker** writes entries to `C:\Windows\System32\drivers\etc\hosts` between clearly marked section markers — disabling removes only those lines.
- **Secure Wipe** overwrites file content before deletion. It cannot recover files deleted through normal means.
- **Scout Mode** uses `watchdog` for filesystem monitoring and `psutil` for process/network polling. It saves sessions to `profiles/scout_*.json`.
- **Wake-on-LAN** devices are saved to `wol_devices.json` in the project directory.
- **Language** defaults to English. Switch to Czech via option 31; the setting persists in `config.json`.

## License

Unlicensed.
