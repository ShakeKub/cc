"""Application downloader catalog and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from core.logger import CleanerLogger


@dataclass(frozen=True)
class AppItem:
    key: str
    name: str
    url: str
    filename: str
    description: str


_APP_CATALOG: dict[str, list[AppItem]] = {
    "browsers": [
        AppItem(
            key="chrome",
            name="Google Chrome",
            url="https://dl.google.com/chrome/install/ChromeStandaloneSetup64.exe",
            filename="ChromeSetup.exe",
            description="Fast, stable Chromium-based browser.",
        ),
        AppItem(
            key="firefox",
            name="Mozilla Firefox",
            url="https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US",
            filename="FirefoxSetup.exe",
            description="Privacy-focused open-source browser.",
        ),
        AppItem(
            key="edge",
            name="Microsoft Edge",
            url="https://go.microsoft.com/fwlink/?linkid=2109047&Channel=Stable&language=en",
            filename="MicrosoftEdgeSetup.exe",
            description="Windows default Chromium browser.",
        ),
        AppItem(
            key="brave",
            name="Brave",
            url="https://laptop-updates.brave.com/latest/win64",
            filename="BraveSetup.exe",
            description="Privacy-first Chromium browser.",
        ),
        AppItem(
            key="chrome_canary",
            name="Google Chrome Canary",
            url="https://dl.google.com/chrome/install/GoogleChromeCanaryStandaloneSetup64.exe",
            filename="ChromeCanarySetup.exe",
            description="Preview channel for Chrome features.",
        ),
        AppItem(
            key="opera",
            name="Opera",
            url="https://download.opera.com/download/get/?partner=www&opsys=Windows",
            filename="OperaSetup.exe",
            description="Feature-rich browser with built-in VPN.",
        ),
    ],
    "gaming": [
        AppItem(
            key="steam",
            name="Steam",
            url="https://cdn.cloudflare.steamstatic.com/client/installer/SteamSetup.exe",
            filename="SteamSetup.exe",
            description="PC game store and launcher.",
        ),
        AppItem(
            key="epic",
            name="Epic Games Launcher",
            url="https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi",
            filename="EpicGamesLauncherInstaller.msi",
            description="Epic Games Store launcher.",
        ),
        AppItem(
            key="gog",
            name="GOG Galaxy",
            url="https://webinstallers.gog.com/GOG_Galaxy_2.0.exe",
            filename="GOG_Galaxy_2.0.exe",
            description="GOG Galaxy game launcher.",
        ),
        AppItem(
            key="ubisoft",
            name="Ubisoft Connect",
            url="https://ubistatic3-a.akamaihd.net/orbit/launcher_installer/UbisoftConnectInstaller.exe",
            filename="UbisoftConnectInstaller.exe",
            description="Ubisoft game launcher.",
        ),
        AppItem(
            key="battlenet",
            name="Battle.net",
            url="https://www.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe",
            filename="BattleNetSetup.exe",
            description="Blizzard game launcher.",
        ),
    ],
    "communication": [
        AppItem(
            key="discord",
            name="Discord",
            url="https://discord.com/api/download?platform=win",
            filename="DiscordSetup.exe",
            description="Voice, video, and text chat for communities.",
        ),
        AppItem(
            key="slack",
            name="Slack",
            url="https://slack.com/ssb/download-win64",
            filename="SlackSetup.exe",
            description="Team chat and collaboration.",
        ),
        AppItem(
            key="teams",
            name="Microsoft Teams",
            url="https://go.microsoft.com/fwlink/?linkid=2187327",
            filename="TeamsSetup.exe",
            description="Meetings and collaboration for Microsoft 365.",
        ),
        AppItem(
            key="zoom",
            name="Zoom",
            url="https://zoom.us/client/latest/ZoomInstallerFull.exe",
            filename="ZoomInstaller.exe",
            description="Video conferencing and webinars.",
        ),
        AppItem(
            key="telegram",
            name="Telegram Desktop",
            url="https://telegram.org/dl/desktop/win64",
            filename="TelegramDesktopSetup.exe",
            description="Secure messaging client.",
        ),
        AppItem(
            key="signal",
            name="Signal",
            url="https://updates.signal.org/desktop/signal-desktop-win-setup.exe",
            filename="SignalSetup.exe",
            description="Private messaging with end-to-end encryption.",
        ),
    ],
    "tools": [
        AppItem(
            key="vscode",
            name="Visual Studio Code",
            url="https://update.code.visualstudio.com/latest/win32-x64-user/stable",
            filename="VSCodeSetup.exe",
            description="Code editor by Microsoft.",
        ),
        AppItem(
            key="github_desktop",
            name="GitHub Desktop",
            url="https://desktop.githubusercontent.com/releases/latest/GitHubDesktopSetup.exe",
            filename="GitHubDesktopSetup.exe",
            description="GitHub client for Windows.",
        ),
        AppItem(
            key="obs",
            name="OBS Studio",
            url="https://cdn-fastly.obsproject.com/downloads/OBS-Studio-Installer.exe",
            filename="OBS-Studio-Installer.exe",
            description="Streaming and recording software.",
        ),
        AppItem(
            key="git",
            name="Git for Windows",
            url="https://github.com/git-for-windows/git/releases/latest/download/Git-64-bit.exe",
            filename="GitForWindowsSetup.exe",
            description="Git SCM for Windows.",
        ),
        AppItem(
            key="powertoys",
            name="PowerToys",
            url="https://github.com/microsoft/PowerToys/releases/latest/download/PowerToysSetup-x64.exe",
            filename="PowerToysSetup.exe",
            description="Windows power-user utilities.",
        ),
        AppItem(
            key="7zip",
            name="7-Zip",
            url="https://www.7-zip.org/a/7z2401-x64.exe",
            filename="7zip-x64.exe",
            description="File archiver and extractor.",
        ),
        AppItem(
            key="winrar",
            name="WinRAR",
            url="https://www.rarlab.com/rar/winrar-x64-621.exe",
            filename="WinRARSetup.exe",
            description="Archive manager with RAR support.",
        ),
        AppItem(
            key="notion",
            name="Notion",
            url="https://desktop-release.notion-static.com/Notion%20Setup%20x64.exe",
            filename="NotionSetup.exe",
            description="Notes, docs, and project workspace.",
        ),
        AppItem(
            key="figma",
            name="Figma",
            url="https://desktop.figma.com/win/FigmaSetup.exe",
            filename="FigmaSetup.exe",
            description="Collaborative design tool.",
        ),
        AppItem(
            key="canva",
            name="Canva",
            url="https://desktop-release.canva.com/Canva%20Setup.exe",
            filename="CanvaSetup.exe",
            description="Graphic design platform.",
        ),
        AppItem(
            key="1password",
            name="1Password",
            url="https://downloads.1password.com/win/1PasswordSetup.exe",
            filename="1PasswordSetup.exe",
            description="Password manager and vault.",
        ),
        AppItem(
            key="docker",
            name="Docker Desktop",
            url="https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe",
            filename="DockerDesktopInstaller.exe",
            description="Containers and development environments.",
        ),
    ],
    "media": [
        AppItem(
            key="spotify",
            name="Spotify",
            url="https://download.scdn.co/SpotifySetup.exe",
            filename="SpotifySetup.exe",
            description="Music and podcasts streaming.",
        ),
        AppItem(
            key="vlc",
            name="VLC Media Player",
            url="https://get.videolan.org/vlc/last/win64/vlc-3.0.20-win64.exe",
            filename="vlc-win64.exe",
            description="Open-source media player.",
        ),
    ],
}


def get_catalog() -> dict[str, list[AppItem]]:
    return _APP_CATALOG


def list_apps(category: str | None = None) -> list[AppItem]:
    if category:
        return list(_APP_CATALOG.get(category, []))
    apps: list[AppItem] = []
    for items in _APP_CATALOG.values():
        apps.extend(items)
    return apps


def _sanitize_filename(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in ("-", "_", "."))
    return cleaned or "download.bin"


def resolve_filename(item: AppItem) -> str:
    if item.filename:
        return _sanitize_filename(item.filename)
    path = urlparse(item.url).path
    return _sanitize_filename(Path(path).name or f"{item.key}.exe")


def default_download_dir() -> Path:
    dl = Path.home() / "Downloads"
    return dl if dl.exists() else Path.cwd()


def download_app(
    item: AppItem,
    dest_dir: Path,
    logger: CleanerLogger,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / resolve_filename(item)

    try:
        req = Request(item.url, headers={"User-Agent": "ByteSweep/1.0"})
        with urlopen(req, timeout=30) as response:
            total = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            with open(dest_path, "wb") as fh:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
        logger.log(
            "app_download",
            "app_downloader",
            f"{item.name} -> {dest_path}",
            freed_bytes=0,
            risk_level="safe",
            success=True,
        )
        return dest_path
    except Exception as exc:
        logger.error(f"App download failed ({item.name}): {exc}")
        raise
