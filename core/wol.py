"""Wake-on-LAN — send magic packets to wake devices on the local network."""

import re
import socket
from core.logger import CleanerLogger

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$")

# Simple persistent device list stored in-memory / optionally on disk
_DEVICE_FILE = None  # set via configure() if persistence wanted


def validate_mac(mac: str) -> bool:
    """Return True if mac is a valid XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX string."""
    return bool(_MAC_RE.match(mac.strip()))


def build_magic_packet(mac: str) -> bytes:
    """Construct a Wake-on-LAN magic packet for the given MAC address."""
    mac_clean = mac.replace(":", "").replace("-", "").upper()
    if len(mac_clean) != 12:
        raise ValueError(f"Invalid MAC address: {mac}")
    mac_bytes = bytes.fromhex(mac_clean)
    return b"\xFF" * 6 + mac_bytes * 16


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255",
                       port: int = 9, logger: CleanerLogger | None = None) -> bool:
    """Send a WOL magic packet via UDP broadcast."""
    if not validate_mac(mac):
        if logger:
            logger.error(f"send_magic_packet: invalid MAC: {mac}")
        return False
    try:
        packet = build_magic_packet(mac)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, port))
        if logger:
            logger.log("wol_send", "wol", f"Magic packet sent to {mac} via {broadcast}:{port}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"send_magic_packet error: {e}")
        return False


def load_devices(path: str) -> list[dict]:
    """Load saved WOL devices from a JSON file."""
    import json
    from pathlib import Path
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_devices(devices: list[dict], path: str) -> bool:
    """Persist WOL device list to a JSON file."""
    import json
    from pathlib import Path
    try:
        Path(path).write_text(json.dumps(devices, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False
