"""Hardware information — CPU, RAM, GPU, motherboard, BIOS."""
import os, platform, re, subprocess
import psutil

def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception:
        return -1, "", ""

def _wmic(alias, fields):
    rc, out, _ = _run(["wmic", alias, "get", ",".join(fields), "/format:list"])
    items, cur = [], {}
    for line in out.splitlines():
        line = line.strip()
        if "=" in line:
            k, v = line.split("=", 1)
            cur[k.strip()] = v.strip()
        elif not line and cur:
            items.append(cur); cur = {}
    if cur: items.append(cur)
    return [i for i in items if any(i.values())]

def cpu_info() -> dict:
    freq = psutil.cpu_freq()
    return {
        "name":         _cpu_name(),
        "cores_phys":   psutil.cpu_count(logical=False),
        "cores_logic":  psutil.cpu_count(logical=True),
        "freq_mhz":     round(freq.current) if freq else None,
        "freq_max_mhz": round(freq.max) if freq else None,
        "arch":         platform.machine(),
        "usage_pct":    psutil.cpu_percent(interval=0.3),
    }

def _cpu_name() -> str:
    if os.name == "nt":
        rows = _wmic("cpu", ["Name"])
        if rows: return rows[0].get("Name", "")
    if platform.system() == "Darwin":
        rc, out, _ = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if rc == 0: return out.strip()
    try:
        for line in open("/proc/cpuinfo", errors="replace"):
            if "model name" in line:
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor()

def ram_info() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    slots = []
    if os.name == "nt":
        rows = _wmic("memorychip", ["Capacity", "Speed", "MemoryType", "Manufacturer"])
        for r in rows:
            try:
                cap = int(r.get("Capacity", 0))
            except Exception:
                cap = 0
            slots.append({"size_gb": round(cap / 1e9, 1),
                          "speed_mhz": r.get("Speed","?"),
                          "manufacturer": r.get("Manufacturer","?")})
    return {
        "total_gb":   round(vm.total / 1e9, 2),
        "used_gb":    round(vm.used  / 1e9, 2),
        "percent":    vm.percent,
        "swap_gb":    round(sw.total / 1e9, 2),
        "slots":      slots,
    }

def gpu_info() -> list[dict]:
    if os.name == "nt":
        rows = _wmic("path Win32_VideoController", ["Name","AdapterRAM","DriverVersion","CurrentRefreshRate"])
        out = []
        for r in rows:
            try:
                vram = int(r.get("AdapterRAM", 0))
            except Exception:
                vram = 0
            out.append({"name": r.get("Name","?"),
                        "vram_gb": round(vram/1e9, 1) if vram else None,
                        "driver": r.get("DriverVersion","?"),
                        "refresh_hz": r.get("CurrentRefreshRate","?")})
        return out
    if platform.system() == "Darwin":
        rc, out, _ = _run(["system_profiler", "SPDisplaysDataType"])
        gpus = []
        for line in out.splitlines():
            if "Chipset Model:" in line:
                gpus.append({"name": line.split(":",1)[1].strip()})
        return gpus
    # Linux: lspci
    rc, out, _ = _run(["lspci"])
    return [{"name": l.split(":",2)[-1].strip()} for l in out.splitlines()
            if "VGA" in l or "3D" in l or "Display" in l]

def motherboard_info() -> dict:
    if os.name == "nt":
        mb = _wmic("baseboard", ["Manufacturer","Product","Version"])
        bios = _wmic("bios", ["Manufacturer","SMBIOSBIOSVersion","ReleaseDate"])
        mb_r   = mb[0]   if mb   else {}
        bios_r = bios[0] if bios else {}
        return {"manufacturer": mb_r.get("Manufacturer","?"),
                "product":      mb_r.get("Product","?"),
                "version":      mb_r.get("Version","?"),
                "bios_vendor":  bios_r.get("Manufacturer","?"),
                "bios_version": bios_r.get("SMBIOSBIOSVersion","?"),
                "bios_date":    bios_r.get("ReleaseDate","?")[:8]}
    if platform.system() == "Darwin":
        rc, out, _ = _run(["system_profiler", "SPHardwareDataType"])
        d = {}
        for line in out.splitlines():
            if "Model Name:" in line:    d["product"] = line.split(":",1)[1].strip()
            if "Model Identifier:" in line: d["version"] = line.split(":",1)[1].strip()
        return d
    # Linux: dmidecode (requires root)
    rc, out, _ = _run(["dmidecode", "-t", "baseboard"])
    d = {}
    for line in out.splitlines():
        if "Manufacturer:" in line: d["manufacturer"] = line.split(":",1)[1].strip()
        if "Product Name:" in line: d["product"] = line.split(":",1)[1].strip()
    return d

def disk_info() -> list[dict]:
    disks = []
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
            disks.append({"device": p.device, "mount": p.mountpoint,
                          "fstype": p.fstype,
                          "total_gb": round(u.total/1e9, 1),
                          "used_gb":  round(u.used/1e9, 1),
                          "percent":  u.percent})
        except Exception:
            pass
    return disks

def full_report() -> dict:
    return {"cpu": cpu_info(), "ram": ram_info(), "gpu": gpu_info(),
            "motherboard": motherboard_info(), "disks": disk_info(),
            "os": platform.platform(), "hostname": platform.node()}
