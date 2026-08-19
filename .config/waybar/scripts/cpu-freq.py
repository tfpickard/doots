#!/usr/bin/env python3
"""Waybar CPU frequency / governor module.

The built-in cpu module only shows aggregate usage. This adds the missing
frequency picture for a many-core machine: the scaling governor and driver,
the energy-performance preference (intel_pstate EPP), the average / peak / min
core clock, and how many cores are actually busy right now.

Bar text:  {icon} {avg}GHz
Tooltip:   governor, driver, EPP, avg/max/min GHz, active cores N/total,
           and a compact per-core clock grid.

Output is a single line of Waybar JSON: {text, tooltip, class}.
"""
import glob
import json
import os
import re
import time

CPU_BASE = "/sys/devices/system/cpu"
BUSY_THRESHOLD = 0.10  # a core counts as "active" above 10% utilisation
STATE_DIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
THROTTLE_STATE = os.path.join(STATE_DIR, "waybar-cpu-throttle.json")
THERMAL_TEMP_C = 95  # at/above this we call an active throttle "thermal"

ICON_PERF = "󰓅"       # speedometer — performance-ish
ICON_SAVE = "󰾆"       # gauge low — powersave
ICON_DEFAULT = ""    # cpu chip
ICON_THROTTLE = "󰀦"   # warning triangle — actively throttling


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def read_int(path, default=None):
    v = read(path)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def cpu_dirs():
    dirs = []
    for d in sorted(
        glob.glob(os.path.join(CPU_BASE, "cpu[0-9]*")),
        key=lambda p: int(re.search(r"cpu(\d+)$", p).group(1)),
    ):
        if os.path.isdir(os.path.join(d, "cpufreq")):
            dirs.append(d)
    return dirs


def sample_stat():
    """Return {cpuN: (idle, total)} from /proc/stat for per-core utilisation."""
    out = {}
    try:
        with open("/proc/stat") as f:
            for line in f:
                if not line.startswith("cpu"):
                    continue
                parts = line.split()
                name = parts[0]
                if name == "cpu":  # aggregate line, skip
                    continue
                vals = list(map(int, parts[1:]))
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
                total = sum(vals)
                out[name] = (idle, total)
    except OSError:
        pass
    return out


def active_cores():
    a = sample_stat()
    time.sleep(0.25)
    b = sample_stat()
    count = 0
    for name, (idle1, total1) in a.items():
        if name not in b:
            continue
        idle2, total2 = b[name]
        dt = total2 - total1
        di = idle2 - idle1
        if dt <= 0:
            continue
        usage = 1.0 - (di / dt)
        if usage >= BUSY_THRESHOLD:
            count += 1
    return count


def package_temp():
    """Return the CPU package temperature in °C, or None."""
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if read(os.path.join(h, "name")) != "coretemp":
                continue
            for lbl in glob.glob(os.path.join(h, "temp*_label")):
                if "Package" in (read(lbl) or ""):
                    inp = lbl.replace("_label", "_input")
                    v = read_int(inp)
                    if v is not None:
                        return v / 1000.0
        except OSError:
            continue
    return None


def throttle_counts():
    """Sum of hardware thermal-throttle counters (package + per-core).

    These increment on thermal *and* externally asserted PROCHOT throttling
    (e.g. an underpowered charger), so they catch both. RAPL/PL1 power capping
    is not reflected here.
    """
    pkg = read_int(os.path.join(CPU_BASE, "cpu0", "thermal_throttle",
                                "package_throttle_count")) or 0
    core = 0
    for c in glob.glob(os.path.join(CPU_BASE, "cpu*", "thermal_throttle",
                                    "core_throttle_count")):
        core += read_int(c) or 0
    return pkg, core


def throttle_status():
    """Compare current throttle counters against the previous run.

    Returns (active, total_events, cause) where `active` is True if the
    counters moved since the last invocation (i.e. throttling right now).
    """
    pkg, core = throttle_counts()
    total = pkg + core
    prev_total = None
    try:
        with open(THROTTLE_STATE) as f:
            prev_total = json.load(f).get("total")
    except (OSError, ValueError):
        prev_total = None

    try:
        with open(THROTTLE_STATE, "w") as f:
            json.dump({"total": total, "pkg": pkg, "core": core}, f)
    except OSError:
        pass

    active = prev_total is not None and total > prev_total
    delta = (total - prev_total) if (active and prev_total is not None) else 0

    cause = None
    if active:
        t = package_temp()
        if t is not None and t >= THERMAL_TEMP_C:
            cause = f"thermal (~{t:.0f}°C)"
        else:
            cause = "external PROCHOT (power/charger)"
    return active, total, delta, cause


def main():
    dirs = cpu_dirs()
    total = len(dirs) or os.cpu_count() or 1

    # Governor / driver / EPP come from cpu0's policy (uniform on this box).
    cf0 = os.path.join(CPU_BASE, "cpu0", "cpufreq")
    governor = read(os.path.join(cf0, "scaling_governor"), "?")
    driver = read(os.path.join(cf0, "scaling_driver"))
    epp = read(os.path.join(cf0, "energy_performance_preference"))

    # Per-core current frequency (kHz).
    freqs = []
    for d in dirs:
        khz = read_int(os.path.join(d, "cpufreq", "scaling_cur_freq"))
        if khz:
            freqs.append(khz)

    if freqs:
        avg = sum(freqs) / len(freqs) / 1e6   # GHz
        fmax = max(freqs) / 1e6
        fmin = min(freqs) / 1e6
    else:
        avg = fmax = fmin = 0.0

    max_khz = read_int(os.path.join(cf0, "cpuinfo_max_freq"))
    min_khz = read_int(os.path.join(cf0, "cpuinfo_min_freq"))

    busy = active_cores()
    throttling, throttle_total, throttle_delta, throttle_cause = throttle_status()

    # --- bar text -----------------------------------------------------------
    if governor == "performance":
        icon = ICON_PERF
    elif governor == "powersave":
        icon = ICON_SAVE
    else:
        icon = ICON_DEFAULT
    text = f"{icon}  {avg:.1f}GHz"
    if throttling:
        text += f"  {ICON_THROTTLE}"

    classes = [governor] if governor and governor != "?" else []
    if busy >= max(1, total * 0.75):
        classes.append("busy")
    if throttling:
        classes.append("throttling")

    # --- tooltip ------------------------------------------------------------
    lines = []
    lines.append(f"<b>Governor:</b> {governor}" + (f"  ({driver})" if driver else ""))
    if epp:
        lines.append(f"<b>EPP:</b> {epp}")
    lines.append("")
    lines.append(f"<b>Clock avg:</b> {avg:.2f} GHz")
    lines.append(f"<b>Peak core:</b> {fmax:.2f} GHz    <b>Min:</b> {fmin:.2f} GHz")
    if max_khz:
        rng = f"{(min_khz or 0)/1e6:.1f}–{max_khz/1e6:.1f} GHz"
        lines.append(f"<b>HW range:</b> {rng}")
    lines.append(f"<b>Active cores:</b> {busy}/{total}")

    # Throttle line.
    if throttling:
        lines.append(f"{ICON_THROTTLE} <b>Throttling now</b> (+{throttle_delta}) — {throttle_cause}")
    elif throttle_total:
        lines.append(f"Throttle events (since boot): {throttle_total}")

    # Compact per-core grid, 4 columns.
    if freqs:
        lines.append("")
        lines.append("<b>Per-core (GHz):</b>")
        cells = [f"{i:>2}:{khz/1e6:>4.1f}" for i, khz in enumerate(freqs)]
        for row in range(0, len(cells), 4):
            lines.append("  ".join(cells[row:row + 4]))

    lines.append("")
    lines.append("<i>Left: toggle governor · Right: s-tui monitor</i>")

    tooltip = "\n".join(lines)

    print(json.dumps({"text": text, "tooltip": tooltip, "class": classes}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"text": "󰻠", "tooltip": f"cpufreq error: {e}", "class": "error"}))
