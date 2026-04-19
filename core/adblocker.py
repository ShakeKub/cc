"""Hosts-based Ad Blocker — block ad/tracking domains via the hosts file."""

from pathlib import Path
from core.logger import CleanerLogger

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
MARKER_START = "# == System Cleaner Ad Block Start =="
MARKER_END   = "# == System Cleaner Ad Block End =="

# Curated list of common ad/tracking domains
BLOCK_LIST = [
    "ads.google.com",
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "googletagmanager.com",
    "googletagservices.com",
    "adservice.google.com",
    "adservice.google.co.uk",
    "pagead2.googlesyndication.com",
    "partner.googleadservices.com",
    "www.googleadservices.com",
    "ad.doubleclick.net",
    "stats.g.doubleclick.net",
    "cm.g.doubleclick.net",
    "tracking.g.doubleclick.net",
    "ads.yahoo.com",
    "analytics.yahoo.com",
    "ads.twitter.com",
    "analytics.twitter.com",
    "ads.facebook.com",
    "pixel.facebook.com",
    "connect.facebook.net",
    "graph.facebook.com",
    "an.facebook.com",
    "ads.linkedin.com",
    "px.ads.linkedin.com",
    "snapads.com",
    "sc-static.net",
    "ads.snapchat.com",
    "ads.tiktok.com",
    "analytics.tiktok.com",
    "imasdk.googleapis.com",
    "pagead.l.doubleclick.net",
    "secure.adnxs.com",
    "ib.adnxs.com",
    "adnxs.com",
    "rubiconproject.com",
    "fastlane.rubiconproject.com",
    "pubads.g.doubleclick.net",
    "securepubads.g.doubleclick.net",
    "adbrite.com",
    "adroll.com",
    "d.adroll.com",
    "s.adroll.com",
    "criteo.com",
    "dis.us.criteo.com",
    "sslwidget.criteo.com",
    "widget.criteo.com",
    "taboola.com",
    "nr-data.net",
    "outbrain.com",
    "ads.outbrain.com",
    "widgets.outbrain.com",
    "sp.analytics.yahoo.com",
    "scorecardresearch.com",
    "b.scorecardresearch.com",
    "s.yimg.com",
    "cdn.amazon-adsystem.com",
    "aax.amazon-adsystem.com",
    "c.amazon-adsystem.com",
    "z-na.amazon-adsystem.com",
    "fls-na.amazon.com",
    "analytics.google.com",
    "ssl.google-analytics.com",
    "www.google-analytics.com",
    "google-analytics.com",
    "metrics.apple.com",
    "telemetry.microsoft.com",
    "vortex.data.microsoft.com",
    "settings-win.data.microsoft.com",
    "watson.telemetry.microsoft.com",
    "oca.telemetry.microsoft.com",
    "sqm.microsoft.com",
    "telecommand.telemetry.microsoft.com",
    "statsfe1.ws.microsoft.com",
    "statsfe2.ws.microsoft.com",
]


def is_enabled() -> bool:
    """Check if the ad-block section exists in the hosts file."""
    if not HOSTS_PATH.exists():
        return False
    try:
        text = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
        return MARKER_START in text
    except Exception:
        return False


def enable(logger: CleanerLogger) -> tuple[bool, int]:
    """Add block list to hosts file. Returns (success, count_added)."""
    try:
        text = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
        if MARKER_START in text:
            return True, 0  # already enabled

        block_lines = [MARKER_START]
        for domain in BLOCK_LIST:
            block_lines.append(f"0.0.0.0 {domain}")
        block_lines.append(MARKER_END)

        HOSTS_PATH.write_text(
            text.rstrip() + "\n\n" + "\n".join(block_lines) + "\n",
            encoding="utf-8",
        )
        logger.log("adblocker_enable", "adblocker",
                   f"Ad blocker enabled — {len(BLOCK_LIST)} domains blocked")
        return True, len(BLOCK_LIST)
    except Exception as e:
        logger.error(f"adblocker enable error: {e}")
        return False, 0


def disable(logger: CleanerLogger) -> bool:
    """Remove the block list section from the hosts file."""
    try:
        text = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
        if MARKER_START not in text:
            return True  # already disabled
        start = text.find(MARKER_START)
        end = text.find(MARKER_END)
        if end == -1:
            end = len(text)
        else:
            end += len(MARKER_END)
        cleaned = text[:start].rstrip() + "\n" + text[end:].lstrip()
        HOSTS_PATH.write_text(cleaned, encoding="utf-8")
        logger.log("adblocker_disable", "adblocker", "Ad blocker disabled")
        return True
    except Exception as e:
        logger.error(f"adblocker disable error: {e}")
        return False


def get_blocked_domains() -> list[str]:
    """Return the list of currently blocked domains parsed from hosts file."""
    if not HOSTS_PATH.exists():
        return []
    domains = []
    in_block = False
    try:
        for line in HOSTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() == MARKER_START:
                in_block = True
                continue
            if line.strip() == MARKER_END:
                break
            if in_block and line.startswith("0.0.0.0 "):
                domains.append(line.split()[1])
    except Exception:
        pass
    return domains
