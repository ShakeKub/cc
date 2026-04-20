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

The main menu is organized into six categories across 45 options.

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
| 47 | File Encryption | AES-256-GCM encrypt/decrypt files and folders; scrypt key derivation; `.scenc` extension |

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
| 46 | Package Manager | Install, uninstall, upgrade packages via winget and Chocolatey; show upgradable list |
| 49 | App Manager | List running user apps with CPU/RAM/connections; kill or block/unblock internet per process |

### Monitoring
| # | Feature | Description |
|---|---------|-------------|
| 22 | App Tracer | Real-time file/process/network tracing; **Pre-launch scan** (static trace before launch); **Protected Run** (snapshot + optional net block + added/modified/deleted diff on exit) |
| 23 | Scout Mode | Deep monitoring — file I/O, registry changes, downloads, network, spawned processes; file diff breakdown (added/modified/deleted/unchanged); **Pre-launch scan**; **Protected/Sandboxed Run** with live feed + diff |
| 24 | System Health | Composite health score (0–100, A–F) across CPU, RAM, disk, startup load, and uptime |
| 25 | Crash Logs | Read critical/error events from Windows Event Log, BSOD history, and minidump files |
| 26 | Disk Health | Physical disk info, SMART counters (temperature, wear, errors), partition usage bars |
| 38 | System Info | Full hardware snapshot — CPU, RAM sticks, GPU, disks, network adapters — with file export |
| 39 | Network Speed Test | Ping latency (3 servers), DNS resolution timing, 10 MB download speed test |
| 48 | Driver Manager | List PnP drivers (WMI), highlight unsigned drivers, list kernel drivers (driverquery), open Device Manager |

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

### Gaming
| # | Feature | Description |
|---|---------|-------------|
| 44 | Gaming Hub | MTA San Andreas serial spoofer (hardware ID) and FiveM identity wipe |
| 45 | MTA Lua Executor | Write, edit, save, and deploy Lua scripts as in-game resources on an MTA server |

---

## Tutorial: MTA Serial Spoofer

### How it works

MTA San Andreas does not store your serial anywhere — it **computes it on every launch** from two Windows hardware identifiers:

| Registry key | Value name |
|---|---|
| `HKLM\SOFTWARE\Microsoft\Cryptography` | `MachineGuid` |
| `HKLM\SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001` | `HwProfileGuid` |

Spoofing your serial means replacing those two GUIDs with random values before launching MTA. Your original values are backed up automatically so you can restore them at any time.

### Step-by-step

1. **Run System Cleaner as Administrator** (required for HKLM registry writes).
2. From the main menu press **`44`** → Gaming Hub.
3. The screen shows your current hardware IDs and whether a backup exists.
4. Press **`m1`** → **Spoof** — two new random GUIDs are written. A backup is saved to `mta_hwid_backup.json`.
5. **Launch MTA San Andreas.** It will compute a new serial from the spoofed GUIDs.
6. When you want your original serial back, press **`m2`** → **Restore** — the backup values are written back.

> **Note:** The spoof persists through reboots until you restore. Use `[m2]` whenever you want to revert.

### FiveM

FiveM stores identity tokens in cached files rather than computing them from hardware. Use:

- **`f1`** → Clear identity tokens (`ros_id.dat`, game-storage DB) — gives you a new FiveM identity.
- **`f2`** → Full cache wipe — removes all cached FiveM data.

---

## Tutorial: MTA Lua Executor

The Executor lets you write Lua scripts and deploy them as a resource on an MTA San Andreas **server**. Once deployed you start the resource from the MTA F8 console — no server restart needed.

### Requirements

- Access to the MTA server's `resources` directory (local or network path).
- The MTA server must be running.

### Step-by-step

1. From the main menu press **`45`** → MTA Lua Executor.
2. If the tool detects your resources directory automatically it shows the path at the top. If not, press **`5`** and paste the path manually (e.g. `C:\MTA\server\mods\deathmatch\resources`).
3. Press **`1`** → **Write / paste Lua code** — the editor window opens.

#### Using the code editor

The editor shows your script with line numbers inside a framed window:

```
  ┌─ Lua Editor ──────────────────────────────────┐
  │   1  outputChatBox("Hello!", root, 255, 255, 0)
  │   2  
  └────────────────────────────────────────────────┘
  lua> _
```

| Command | Action |
|---|---|
| Type any text + Enter | Append a new line |
| `.e 2 new content` | Replace line 2 with `new content` |
| `.d 2` | Delete line 2 |
| `.ins 2` | Insert a new line before line 2 (prompts for content) |
| `.clear` | Remove all lines |
| `.done` | Finish editing and continue |
| `.cancel` | Discard changes and go back |

4. After typing `.done`, choose the script target:
   - **`1`** Client-side
   - **`2`** Server-side
   - **`3`** Both

5. The tool creates `resources/sc_executor/` containing `meta.xml`, `client.lua`, and `server.lua`.

6. **In MTA F8 console** (press F8 in-game or in the server console) type:
   ```
   start sc_executor
   ```
   The resource loads immediately. To reload after a code change:
   ```
   restart sc_executor
   ```

### Saving and reusing scripts

- **`3`** — Write a new script and save it under a name (alphanumeric, `-`, `_`).
- **`2`** — Pick a saved script, optionally edit it in the editor, then deploy.
- **`4`** — List all saved scripts, view previews, delete ones you no longer need.

Scripts are stored as `.lua` files in the `executor_scripts/` directory next to `main.py`.

---

## Tutorial: App Manager (option 49)

### Blocking an app's internet access

1. From the main menu press **`3`** (Tools) → **`49`** App Manager.
2. The list shows all running user apps with CPU%, RAM, and active connection count. Apps already blocked are marked `[B]` in red.
3. To block an app's outbound internet, type **`b <number>`** — e.g. `b 3` blocks the third app in the list.  
   This adds a Windows Firewall outbound block rule named `SC_BLOCK_<exe>`. Admin rights required.
4. To unblock, type **`u <number>`**.
5. **`ba`** blocks all apps that currently have active connections in one step.
6. **`k <number>`** kills the process immediately.

The block rule persists through reboots. It is visible in Windows Defender Firewall → Advanced Settings → Outbound Rules.

---

## Tutorial: Pre-launch Scan & Protected Run

These options appear in both **App Tracer** (`[22]`) and **Scout Mode** (`[23]`).

### Pre-launch scan (`[8]` / `[6]`)

Run this **before** you launch an app to see what traces it already has on your system:
files, registry keys, services, scheduled tasks, and whether it is already running.

1. Press `8` in App Tracer (or `6` in Scout Mode).
2. Enter the app name (e.g. `discord`, `obs64`, `steam`).
3. The scanner searches AppData, ProgramData, Program Files, Temp, and the registry.
4. Use the results as your baseline before running the app.

### Protected run (`[9]` / `[7]`)

Launches an app inside a monitoring envelope:
- Takes a **filesystem + registry snapshot** before launch.
- Optionally **blocks the app's outbound internet** via Windows Firewall.
- Streams live events (file/registry/network/process) while the app runs.
- On exit, computes a **diff** showing every file added, modified, or deleted.

Step-by-step:
1. Press `9` in App Tracer (or `7` in Scout Mode).
2. Enter the full path to the `.exe`.
3. Enter the folder to watch (default: your user profile).
4. Choose whether to block internet.
5. The app launches. Press **Enter** when you want to stop monitoring.
6. The diff report shows:
   - `+` **Added** — new files created by the app
   - `~` **Modified** — files that existed before and were changed
   - `-` **Deleted** — files the app removed
   - `Unchanged` — count of files that were not touched
   - Registry changes (keys/values added, modified, or deleted)

In Scout Mode (`[7]`) a full live Scout session also runs alongside the snapshot, so all raw events are saved to `profiles/` for later review.

---

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
├── mta_hwid_backup.json  # MTA hardware ID backup (auto-created on first spoof)
├── executor_scripts/     # Saved Lua scripts (auto-created)
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
│   ├── netspeed.py       # Network speed test (ping, DNS, download)
│   ├── gaming.py         # MTA serial spoofer and identity wipe
│   ├── executor.py       # MTA Lua resource deployer
│   ├── appmgr.py         # Running app list + per-process firewall block/unblock
│   ├── sandbox.py        # Filesystem+registry snapshot, diff, protected app launch
│   ├── pkgmgr.py         # Package Manager (winget + Chocolatey)
│   ├── fileencrypt.py    # AES-256-GCM file/folder encryption
│   └── drivermgr.py      # Driver Manager (WMI PnP + driverquery)
├── profiles/             # Saved tracer and scout session files (JSON)
└── logs/                 # Exported session logs
```

## Notes

- **Admin rights** are required for RAM optimization, service management, system restore points, registry writes outside HKCU, editing the hosts file, firewall rule changes, the MTA serial spoofer, and blocking app internet access.
- **App Manager** blocks outbound internet by adding a Windows Firewall rule named `SC_BLOCK_<exe>`. Rules are visible in Windows Firewall advanced settings and survive reboots until removed.
- **Protected Run** (App Tracer / Scout Mode) takes a filesystem+registry snapshot before the app launches and diffs it after — showing exactly which files were added, modified, or deleted. Optionally blocks the app's network during the run.
- **Pre-launch Scan** runs the static AppTracer against an app name before you start it — showing existing files, registry keys, services, and scheduled tasks it already has on disk.
- **Ad Blocker** writes entries to `C:\Windows\System32\drivers\etc\hosts` between clearly marked section markers — disabling removes only those lines.
- **Secure Wipe** overwrites file content before deletion. It cannot recover files deleted through normal means.
- **Scout Mode** uses `watchdog` for filesystem monitoring and `psutil` for process/network polling. It saves sessions to `profiles/scout_*.json`.
- **Wake-on-LAN** devices are saved to `wol_devices.json` in the project directory.
- **Language** defaults to English. Switch to Czech via option 31; the setting persists in `config.json`.
- **MTA Spoofer** requires admin rights and backs up original hardware IDs to `mta_hwid_backup.json` before any change.
- **MTA Executor** deploys scripts to the server's `resources/` folder. The server must be running for `start sc_executor` to work.

## License

Unlicensed.
