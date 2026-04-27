"""Startup / Persistence Auditor — cross-platform startup location scanner."""

import os
import re
import subprocess
from pathlib import Path

_SUSP: list[tuple[re.Pattern, str]] = [
    (re.compile(r'(?i)(\\temp\\|/tmp/|%temp%|appdata.local.temp)'), 'temp dir'),
    (re.compile(r'(?i)(-enc\b|-encodedcommand)'), 'encoded payload'),
    (re.compile(r'(?i)\bbase64\b'), 'base64'),
    (re.compile(r'(?i)\b(mshta|regsvr32|rundll32|wscript|cscript|certutil)\b'), 'LOLBIN'),
    (re.compile(r'(?i)\.(vbs|js|hta|wsf|jse|vbe)\b'), 'script ext'),
    (re.compile(r'(?i)\b(net\s+user|net\s+localgroup|sc\s+(create|config|start))\b'), 'admin op'),
    (re.compile(r'(?i)(curl|wget)\s+.*\|\s*(bash|sh|python|perl|ruby)'), 'pipe to shell'),
    (re.compile(r'\\\\[a-z0-9]'), 'UNC path'),
    (re.compile(r'(?i)\bnohup\b'), 'nohup'),
]

RISK_LABEL = {0: 'OK', 1: 'LOW', 2: 'MEDIUM', 3: 'HIGH'}


def _check_flags(command: str) -> list[str]:
    return [label for pat, label in _SUSP if pat.search(command)]


def _risk_level(flags: list[str]) -> int:
    if any(f in ('LOLBIN', 'encoded payload', 'base64', 'pipe to shell') for f in flags):
        return 3
    if any(f in ('temp dir', 'script ext', 'admin op', 'UNC path') for f in flags):
        return 2
    if flags:
        return 1
    return 0


def _make_entry(source: str, name: str, command: str, enabled: bool = True) -> dict:
    flags = _check_flags(command)
    exists: bool | None = None
    try:
        tok = command.strip().strip('"').split('"')[0].strip().split()[0]
        if tok:
            p = Path(tok)
            if p.is_absolute():
                exists = p.exists()
                if not exists:
                    flags.append('missing file')
    except Exception:
        pass
    return {
        'source':  source,
        'name':    name,
        'command': command[:200],
        'enabled': enabled,
        'risk':    _risk_level(flags),
        'flags':   flags,
        'exists':  exists,
    }


# ── Windows ───────────────────────────────────────────────────

def _scan_windows() -> list[dict]:
    import winreg
    entries: list[dict] = []
    hive_names = {winreg.HKEY_CURRENT_USER: 'HKCU', winreg.HKEY_LOCAL_MACHINE: 'HKLM'}
    run_keys = [
        (winreg.HKEY_CURRENT_USER,  r'Software\Microsoft\Windows\CurrentVersion\Run'),
        (winreg.HKEY_CURRENT_USER,  r'Software\Microsoft\Windows\CurrentVersion\RunOnce'),
        (winreg.HKEY_LOCAL_MACHINE, r'Software\Microsoft\Windows\CurrentVersion\Run'),
        (winreg.HKEY_LOCAL_MACHINE, r'Software\Microsoft\Windows\CurrentVersion\RunOnce'),
        (winreg.HKEY_LOCAL_MACHINE, r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'),
    ]
    for hive, key_path in run_keys:
        try:
            key = winreg.OpenKey(hive, key_path)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    leaf = key_path.rsplit('\\', 1)[-1]
                    entries.append(_make_entry(f'Registry {hive_names[hive]}\\{leaf}', name, str(val)))
                    i += 1
                except OSError:
                    break
        except OSError:
            pass

    for folder in [
        Path(os.environ.get('APPDATA', '')) / r'Microsoft\Windows\Start Menu\Programs\Startup',
        Path(os.environ.get('PROGRAMDATA', '')) / r'Microsoft\Windows\Start Menu\Programs\Startup',
    ]:
        if folder.is_dir():
            for f in folder.iterdir():
                if f.is_file():
                    entries.append(_make_entry(f'Startup folder', f.name, str(f)))

    try:
        r = subprocess.run(['schtasks', '/query', '/fo', 'CSV', '/nh'],
                           capture_output=True, text=True, timeout=15)
        for line in r.stdout.splitlines():
            parts = line.split(',')
            if len(parts) >= 3:
                name = parts[0].strip('"')
                status = parts[2].strip('"')
                entries.append(_make_entry('Scheduled Task', name, name,
                                           enabled=(status in ('Ready', 'Running'))))
    except Exception:
        pass

    return entries


# ── macOS ─────────────────────────────────────────────────────

def _scan_macos() -> list[dict]:
    import plistlib
    entries: list[dict] = []

    plist_dirs = [
        (Path.home() / 'Library/LaunchAgents',         'LaunchAgent (user)'),
        (Path('/Library/LaunchAgents'),                  'LaunchAgent (system)'),
        (Path('/Library/LaunchDaemons'),                 'LaunchDaemon'),
        (Path('/System/Library/LaunchDaemons'),          'LaunchDaemon (Apple)'),
        (Path('/System/Library/LaunchAgents'),           'LaunchAgent (Apple)'),
    ]
    for d, label in plist_dirs:
        if not d.is_dir():
            continue
        for plist_file in sorted(d.glob('*.plist')):
            try:
                data = plistlib.loads(plist_file.read_bytes())
                args = data.get('ProgramArguments', [])
                prog = data.get('Program', '')
                cmd = ' '.join(str(a) for a in args) if args else prog
                name = data.get('Label', plist_file.stem)
                enabled = not data.get('Disabled', False)
                entries.append(_make_entry(label, name, cmd or str(plist_file), enabled=enabled))
            except Exception:
                entries.append(_make_entry(label, plist_file.stem, str(plist_file)))

    # User crontab
    try:
        r = subprocess.run(['crontab', '-l'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split(None, 5)
                cmd = parts[5] if len(parts) > 5 else line
                entries.append(_make_entry('crontab (user)', line[:60], cmd))
    except Exception:
        pass

    # Shell RC — only suspicious lines
    for rc in [Path.home() / f for f in ('.zshrc', '.zprofile', '.bash_profile', '.bashrc', '.profile')]:
        if rc.is_file():
            try:
                for lineno, line in enumerate(rc.read_text(errors='replace').splitlines(), 1):
                    line = line.strip()
                    if line and not line.startswith('#') and _check_flags(line):
                        entries.append(_make_entry(f'{rc.name}:{lineno}', line[:60], line))
            except Exception:
                pass

    return entries


# ── Linux ─────────────────────────────────────────────────────

def _scan_linux() -> list[dict]:
    entries: list[dict] = []

    # /etc/crontab + /etc/cron.d/*
    cron_files: list[Path] = []
    if Path('/etc/crontab').is_file():
        cron_files.append(Path('/etc/crontab'))
    if Path('/etc/cron.d').is_dir():
        cron_files.extend(sorted(Path('/etc/cron.d').iterdir()))
    for cf in cron_files:
        try:
            for line in cf.read_text(errors='replace').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' in line.split()[0]:
                    continue
                parts = line.split(None, 6)
                cmd = parts[-1] if len(parts) >= 6 else line
                entries.append(_make_entry(f'crontab ({cf.name})', line[:60], cmd))
        except Exception:
            pass

    # User crontab
    try:
        r = subprocess.run(['crontab', '-l'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split(None, 5)
                cmd = parts[5] if len(parts) > 5 else line
                entries.append(_make_entry('crontab (user)', line[:60], cmd))
    except Exception:
        pass

    # /etc/rc.local
    rc_local = Path('/etc/rc.local')
    if rc_local.is_file():
        try:
            for line in rc_local.read_text(errors='replace').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    entries.append(_make_entry('rc.local', line[:60], line))
        except Exception:
            pass

    # systemd enabled services
    try:
        r = subprocess.run(
            ['systemctl', 'list-unit-files', '--type=service', '--state=enabled',
             '--no-pager', '--plain'],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.splitlines():
            parts = line.split()
            if not parts or not parts[0].endswith('.service'):
                continue
            name = parts[0]
            cmd = ''
            try:
                r2 = subprocess.run(['systemctl', 'cat', name],
                                    capture_output=True, text=True, timeout=5)
                for l2 in r2.stdout.splitlines():
                    if l2.startswith('ExecStart='):
                        cmd = l2.split('=', 1)[1].lstrip('-')
                        break
            except Exception:
                pass
            entries.append(_make_entry('systemd service', name, cmd or name))
    except Exception:
        pass

    # XDG autostart
    autostart = Path.home() / '.config/autostart'
    if autostart.is_dir():
        for df in sorted(autostart.glob('*.desktop')):
            try:
                cmd = ''
                for line in df.read_text(errors='replace').splitlines():
                    if line.startswith('Exec='):
                        cmd = line.split('=', 1)[1]
                        break
                entries.append(_make_entry('XDG autostart', df.stem, cmd or str(df)))
            except Exception:
                pass

    # /etc/profile.d — only suspicious lines
    if Path('/etc/profile.d').is_dir():
        for sh in sorted(Path('/etc/profile.d').glob('*.sh')):
            try:
                for lineno, line in enumerate(sh.read_text(errors='replace').splitlines(), 1):
                    line = line.strip()
                    if line and not line.startswith('#') and _check_flags(line):
                        entries.append(_make_entry(f'profile.d/{sh.name}:{lineno}', line[:60], line))
            except Exception:
                pass

    # Shell RCs — only suspicious lines
    for rc in [Path.home() / f for f in ('.bashrc', '.bash_profile', '.profile', '.zshrc', '.zprofile')]:
        if rc.is_file():
            try:
                for lineno, line in enumerate(rc.read_text(errors='replace').splitlines(), 1):
                    line = line.strip()
                    if line and not line.startswith('#') and _check_flags(line):
                        entries.append(_make_entry(f'{rc.name}:{lineno}', line[:60], line))
            except Exception:
                pass

    return entries


# ── Public API ────────────────────────────────────────────────

def scan() -> list[dict]:
    """Scan startup/persistence locations. Returns entries sorted by risk (high first)."""
    try:
        sysname = os.uname().sysname
    except AttributeError:
        sysname = 'Windows'

    if os.name == 'nt':
        entries = _scan_windows()
    elif sysname == 'Darwin':
        entries = _scan_macos()
    else:
        entries = _scan_linux()

    entries.sort(key=lambda e: e['risk'], reverse=True)
    return entries


def summary(entries: list[dict]) -> dict:
    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for e in entries:
        counts[e['risk']] += 1
    return {'total': len(entries), 'high': counts[3], 'medium': counts[2],
            'low': counts[1], 'ok': counts[0]}
