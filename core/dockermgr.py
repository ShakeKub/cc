"""Docker manager — containers, images, volumes via docker CLI."""
import subprocess, json

def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -2, "", "Docker not installed or not in PATH"
    except Exception as e:
        return -1, "", str(e)

def is_available() -> bool:
    rc, _, _ = _run(["docker", "info"], timeout=5)
    return rc == 0

def list_containers(all: bool = True) -> list[dict]:
    args = ["docker", "ps", "--format", "{{json .}}"]
    if all: args.append("-a")
    rc, out, err = _run(args)
    if rc != 0: return [{"error": err}]
    containers = []
    for line in out.splitlines():
        try: containers.append(json.loads(line))
        except Exception: pass
    return containers

def list_images() -> list[dict]:
    rc, out, err = _run(["docker", "images", "--format", "{{json .}}"])
    if rc != 0: return [{"error": err}]
    images = []
    for line in out.splitlines():
        try: images.append(json.loads(line))
        except Exception: pass
    return images

def list_volumes() -> list[dict]:
    rc, out, err = _run(["docker", "volume", "ls", "--format", "{{json .}}"])
    if rc != 0: return [{"error": err}]
    vols = []
    for line in out.splitlines():
        try: vols.append(json.loads(line))
        except Exception: pass
    return vols

def container_action(container_id: str, action: str) -> dict:
    """action: start|stop|restart|rm|pause|unpause"""
    rc, out, err = _run(["docker", action, container_id])
    return {"ok": rc == 0, "output": (out + err).strip()}

def image_action(image_id: str, action: str) -> dict:
    """action: rmi|pull"""
    rc, out, err = _run(["docker", action, image_id])
    return {"ok": rc == 0, "output": (out + err).strip()}

def container_logs(container_id: str, tail: int = 50) -> str:
    rc, out, err = _run(["docker", "logs", "--tail", str(tail), container_id])
    return out + err

def system_prune(volumes: bool = False) -> dict:
    cmd = ["docker", "system", "prune", "-f"]
    if volumes: cmd.append("--volumes")
    rc, out, err = _run(cmd, timeout=60)
    return {"ok": rc == 0, "output": (out + err).strip()}

def stats_snapshot() -> list[dict]:
    rc, out, err = _run(["docker", "stats", "--no-stream", "--format", "{{json .}}"])
    if rc != 0: return []
    stats = []
    for line in out.splitlines():
        try: stats.append(json.loads(line))
        except Exception: pass
    return stats
