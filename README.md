# ByteSweep

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

The main menu is organized into six categories.

### Cleaning
| # | Feature | Description |
|---|---------|-------------|
| 1 | System Scan | Scan for temp files, WU cache, DNS cache, thumbnails, and more — shows sizes before cleaning |
| 2 | Quick Clean | Removes temporary files and empties the recycle bin |
| 3 | Standard Clean | Quick + browser caches, prefetch, DNS flush |
| 4 | Deep Clean | Standard + Windows Update cache, log files, thumbnail cache |
| 5 | Team Clean | All-in-one: deep system + all browsers + privacy tracking files |
| 6 | High-value Space Makers | Dev junk, package caches, Windows component store, hibernation/page file, app caches, Recycle Bin/Trash, and old backup files |

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

### Security
| # | Feature | Description |
|---|---------|-------------|
| 47 | File Encryption | Multi-algorithm `.scenc` encryption/decryption, folder mode, algorithm switcher, and auto-detect on decrypt |
| 50 | Hash Cracker | Crack MD5/SHA1/SHA256/SHA512/bcrypt with auto-detection, wordlists, and brute-force modes |
| 51 | Password Generator | Generate strong passwords, pronounceable variants, and live entropy/strength scoring |
| 52 | File Integrity Monitor | Create baseline hashes and detect added/modified/deleted files with diff output |
| 53 | Network Scanner | Port scans, banner grabbing, ping sweep, traceroute, reverse DNS, and WHOIS |
| 54 | Memory Inspector | Process inspection (env/cmdline/files/connections), secret hints, and memory string scan |
| 55 | Steganography | Hide/extract payloads in images (PNG/BMP) with optional password protection |
| 56 | Metadata Stripper | Read/remove metadata from images, DOCX, and PDF files |
| 57 | Breach Checker (HIBP) | k-anonymity password leak check and e-mail breach check (with API key) |
| 58 | SSL/TLS Inspector | Certificate validity, expiry warnings, protocol/cipher checks, and weak protocol detection |
| 59 | 2FA / TOTP Generator | Encrypted TOTP vault with live rotating codes and secret generation |
| 60 | File Analyzer | Magic-byte detection, entropy scoring, extension mismatch checks, and strings extraction |
| 61 | Log Analyzer | System/auth log anomaly scan with event counters and top suspicious IPs |
| 62 | Password Manager | Encrypted local vault for credentials with search, edit, and plaintext export |
| 63 | Encrypted Backup | Password-protected backup creation/restore with verification and manifest tracking |
| 64 | Startup / Persistence Auditor | Cross-platform startup/persistence scan with risk flags and export |
| 69 | Webcam / Mic Auditor | Camera and microphone access audit (platform-specific sources) |

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
| 44 | Factory Setup Wizard | New-PC provisioning profiles (Dev/Gaming/Office/Family): optional restore checkpoint, app bundle install from manifest, smart startup/services optimization, power-plan target |
| 45 | Tweaks Center | Essential + advanced Windows tweaks, preference toggles, and performance-plan actions (with cautions for high-impact operations) |
| 46 | Package Manager | Install, uninstall, upgrade packages via winget and Chocolatey; show upgradable list |
| 49 | App Manager | List running user apps with CPU/RAM/connections; kill or block/unblock internet per process |
| 71 | JSON / YAML / XML Formatter | Auto-detect and format JSON/XML/YAML from files or pasted input |

### Monitoring
| # | Feature | Description |
|---|---------|-------------|
| 22 | App Tracer | Real-time file/process/network tracing; **Pre-launch scan** (static trace before launch); **Protected Run** (snapshot + optional net block + added/modified/deleted diff on exit) |
| 23 | Scout Mode | Deep monitoring — file/registry/network/process/DLL/DNS/pipe events, risk score + verdict, persistence diff, auto HTML report, optional VirusTotal checks, **Pre-launch scan**, and **Protected Run** with live feed + diff |
| 24 | System Health | Composite health score (0–100, A–F) across CPU, RAM, disk, startup load, and uptime |
| 25 | Crash Logs | Read critical/error events from Windows Event Log, BSOD history, and minidump files |
| 26 | Disk Health | Physical disk info, SMART counters (temperature, wear, errors), partition usage bars |
| 38 | System Info | Full hardware snapshot — CPU, RAM sticks, GPU, disks, network adapters — with file export |
| 39 | Network Speed Test | Ping latency (3 servers), DNS resolution timing, 10 MB download speed test |
| 48 | Driver Manager | List PnP drivers (WMI), highlight unsigned drivers, list kernel drivers (driverquery), open Device Manager |
| 65 | System Dashboard | Live CPU/RAM/disk/network dashboard with per-core and throughput view |
| 66 | Port Monitor | List all active/listening ports and optional live LISTEN refresh mode |
| 67 | Temperature Monitor | Sensor temperature view with live mode (where supported) |
| 68 | Battery Info | Battery percentage, charging state, and estimated time remaining |
| 70 | Disk Analyzer | Top folders/files/extensions by size with percentage bars |

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

---

## Tutorial: App Manager (option 49)

### Blocking an app's internet access

1. From the main menu press **`4`** (Tools) → **`49`** App Manager.
2. The list shows all running user apps with CPU%, RAM, and active connection count. Apps already blocked are marked `[B]` in red.
3. To block an app's outbound internet, type **`b <number>`** — e.g. `b 3` blocks the third app in the list.  
   This adds a Windows Firewall outbound block rule named `SC_BLOCK_<exe>`. Admin rights required.
4. To unblock, type **`u <number>`**.
5. **`ba`** blocks all apps that currently have active connections in one step.
6. **`k <number>`** kills the process immediately.

The block rule persists through reboots. It is visible in Windows Defender Firewall → Advanced Settings → Outbound Rules.

---

## Tutorial: Tweaks Center (option 45)

Tweaks Center is a controlled workflow for Windows tweaks with preview, compatibility checks, conflict hints, undo support, and profile management.

### Recommended flow

1. From the main menu press **`4`** (Tools) → **`45`** Tweaks Center.
2. Choose a category:
   - **`1`** Essential Tweaks
   - **`2`** Advanced Tweaks
   - **`3`** Customize Preferences
   - **`4`** Performance Plans
3. Preview first:
   - Use **`p 1,3`** to run **dry-run only** for selected tweaks.
   - Dry-run shows planned actions, admin/restart requirements, and compatibility notes.
4. Apply changes:
   - Use **`n`** (single), **`a 1,3`** (selected), or **`all`**.
   - The app asks for confirmation after preview.
5. Review outcomes:
   - Batch output includes per-tweak status and benchmark delta (when available).
   - Benchmark reports are saved in `logs/tweak_benchmark_*.json`.

### Search, favorites, and profiles

- **`5` Search Tweaks**: find tweaks quickly and apply/preview directly from results.
- **`6` Favorites**: store your regular set and re-apply them in one pass.
- **`7` Profile Manager**:
  - Save profile from keys or from favorites.
  - Apply, export, import, and delete profiles.
  - Local profile files are stored in `profiles/tweak_profiles/`.

### Undo and restart dashboard

- **`8` Undo & Restart Dashboard** provides:
  - Undo last reversible change.
  - Undo last reversible batch.
  - Pending restart list and clear action.
  - Recent undo history.

> Note: Not every tweak is reversible. High-impact or destructive actions may be marked as non-reversible.

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

Scout Mode also supports a local VirusTotal API key (`[v]` in Scout menu). If configured, file hashes from the session can be checked automatically after stop and the HTML report is refreshed with VT verdict badges.

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
├── locales/
│   ├── en.json           # English strings
│   └── cs.json           # Czech strings
├── core/
│   ├── __init__.py
│   ├── adblocker.py      # Hosts-based ad and tracker blocker
│   ├── appmgr.py         # Running app list + per-process firewall block/unblock
│   ├── archivecrack.py   # ZIP/7z/RAR password cracking helpers
│   ├── autoruns.py       # Comprehensive autorun entry manager
│   ├── backup.py         # Encrypted backup create/restore/list/delete
│   ├── browser.py        # Browser cleaning (Chrome, Edge, Firefox)
│   ├── camaudit.py       # Webcam/microphone access audit
│   ├── cleaner.py        # System cleaning (temp, WU cache, DNS, prefetch, recycle bin)
│   ├── codeformatter.py  # JSON/YAML/XML formatting + validation
│   ├── contextmenu.py    # Context menu entry manager
│   ├── crashlog.py       # Windows Event Log and minidump reader
│   ├── disk.py           # Disk usage analysis
│   ├── diskanalyzer.py   # Folder/file/extension size analysis
│   ├── diskhealth.py     # Physical disk SMART data reader
│   ├── dnstools.py       # DNS flush and hosts file editor
│   ├── drivermgr.py      # Driver Manager (WMI PnP + driverquery)
│   ├── duplicates.py     # Duplicate file finder (SHA-1, two-pass)
│   ├── emptyfolders.py   # Empty folder finder and cleaner
│   ├── envvars.py        # Environment variables editor
│   ├── factory.py        # Factory setup wizard logic
│   ├── fileanalyzer.py   # Magic/entropy/strings/headers analysis
│   ├── fileencrypt.py    # Multi-algorithm file/folder encryption
│   ├── firewall.py       # Windows Firewall rule manager
│   ├── fontmgr.py        # Font manager
│   ├── hashcrack.py      # Hash cracking engine
│   ├── health.py         # System health scoring
│   ├── hibp.py           # HaveIBeenPwned client helpers
│   ├── history.py        # Network, USB, and app launch history
│   ├── i18n.py           # Translation layer (t(), set_language(), available_languages())
│   ├── integrity.py      # Baseline hash and integrity diff tool
│   ├── largefile.py      # Large file finder
│   ├── loganalyzer.py    # System/auth log anomaly analyzer
│   ├── logger.py         # Session logger with TXT/JSON export
│   ├── memscanner.py     # Process/memory inspection helpers
│   ├── metastrip.py      # Metadata read/remove for image/doc/pdf
│   ├── msicache.py       # MSI installer cache orphan finder
│   ├── netscanner.py     # Port scan, ping sweep, traceroute, whois
│   ├── netspeed.py       # Network speed test (ping, DNS, download)
│   ├── network.py        # Network connections, DNS, ping, diagnostics
│   ├── optimizer.py      # RAM optimization, services, power plans
│   ├── passgen.py        # Password generation + entropy scoring
│   ├── pdfcrack.py       # PDF password cracking helpers
│   ├── perfboost.py      # One-click performance optimization
│   ├── pkgmgr.py         # Package Manager (winget + Chocolatey)
│   ├── privacy.py        # Telemetry toggles, tracking file removal
│   ├── process.py        # Process listing, kill, suspicious detection
│   ├── pwdmgr.py         # Encrypted local password manager
│   ├── recovery.py       # Recycle Bin and VSS shadow copy recovery
│   ├── registry.py       # Registry scan, backup, restore
│   ├── restore.py        # System Restore point manager
│   ├── sandbox.py        # Filesystem+registry snapshot, diff, protected app launch
│   ├── scheduler.py      # Task scheduler integration
│   ├── scout.py          # Scout Mode — deep real-time monitoring + report export
│   ├── securewipe.py     # Multi-pass secure file wipe
│   ├── shortcutfix.py    # Broken shortcut scanner and fixer
│   ├── sslcheck.py       # SSL/TLS certificate inspector
│   ├── startup.py        # Startup entry manager
│   ├── startupaudit.py   # Startup/persistence risk auditor
│   ├── stego.py          # LSB steganography helper
│   ├── sysinfo.py        # Full system info snapshot and export
│   ├── sysmonitor.py     # Live system dashboard metrics
│   ├── totp.py           # TOTP generation + encrypted vault
│   ├── tracer.py         # Static app trace scanner
│   ├── tracer_session.py # Live app tracing (watchdog-based)
│   ├── tweaks.py         # Tweaks Center (essential, advanced, preferences, performance)
│   ├── uninstaller.py    # Program and built-in app uninstaller
│   ├── winupdate.py      # Windows Update manager
│   ├── wol.py            # Wake-on-LAN magic packet sender
│   └── wordlist.txt      # Bundled password wordlist for cracking features
├── profiles/             # Saved tracer and scout session files (JSON)
└── logs/                 # Exported session logs
```

## Notes

- **Admin rights** are required for RAM optimization, service management, system restore points, registry writes outside HKCU, editing the hosts file, firewall rule changes, and blocking app internet access.
- **App Manager** blocks outbound internet by adding a Windows Firewall rule named `SC_BLOCK_<exe>`. Rules are visible in Windows Firewall advanced settings and survive reboots until removed.
- **Factory Setup Wizard** runs profile-based provisioning for fresh systems and can create a restore checkpoint before changes.
- **Tweaks Center** includes dry-run previews, compatibility/conflict checks, undo dashboard, restart tracking, search/favorites, and profile import/export.
- **Manifest installs** are supported in Package Manager (`.json`): create templates, install custom manifests, or run built-in bundles.
- **Smart Startup/Services optimizer** provides impact-based recommendations first, then applies selected profiles with reversible actions.
- **Audit trail** is persistent across sessions (`logs/audit_trail.jsonl`) and exportable via Logs & Reports as TXT/JSON.
- **Security category** adds hash cracking, password generation, integrity baselines, deep network scan, memory inspector, steganography, metadata stripping, HIBP checks, SSL/TLS inspection, TOTP vault, file/log analyzers, encrypted backup, startup/persistence audit, and webcam/mic audit.
- **File Encryption** now supports multiple algorithms, auto-detect decrypt, and optional cracking workflows for `.scenc`, archives, and encrypted PDFs.
- **Protected Run** (App Tracer / Scout Mode) takes a filesystem+registry snapshot before the app launches and diffs it after — showing exactly which files were added, modified, or deleted. Optionally blocks the app's network during the run.
- **Pre-launch Scan** runs the static AppTracer against an app name before you start it — showing existing files, registry keys, services, and scheduled tasks it already has on disk.
- **Ad Blocker** writes entries to `C:\Windows\System32\drivers\etc\hosts` between clearly marked section markers — disabling removes only those lines.
- **Secure Wipe** overwrites file content before deletion. It cannot recover files deleted through normal means.
- **Scout Mode** uses `watchdog` for filesystem monitoring and `psutil` for process/network polling, now tracks persistence events, computes verdict/risk, auto-exports HTML, and can enrich reports with VirusTotal results.
- **Monitoring additions** include live system dashboard, port monitor, temperature monitor, battery info, and disk analyzer.
- **Optional dependencies** for advanced features: `Pillow` (steganography/image metadata), `pypdf` (PDF cracking/metadata), `py7zr`/`rarfile` or 7-Zip/UnRAR binaries (archive cracking), and `bcrypt` (bcrypt hash checks).
- **Wake-on-LAN** devices are saved to `wol_devices.json` in the project directory.
- **Language** defaults to English. Switch to Czech via option 31; the setting persists in `config.json`.

## License

Unlicensed.
