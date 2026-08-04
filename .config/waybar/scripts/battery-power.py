#!/usr/bin/env python3
"""Waybar rich battery module.

Reads the battery straight from sysfs (/sys/class/power_supply) so it can expose
far more than the built-in module: charge/discharge *rate* in watts and amps,
pack voltage, health (charge_full vs design), cycle count, the active charge
algorithm (Fast/Trickle/…), which supply is feeding it (AC vs USB-C PD),
temperature, time-to-full/empty, and the charge-control thresholds.

Output is a single line of Waybar JSON: {text, tooltip, class}.

Batteries report either energy-based (energy_now µWh / power_now µW) or
charge-based (charge_now µAh / current_now µA) values; this handles both.
"""
import glob
import json
import os

PS = "/sys/class/power_supply"
BAT = os.environ.get("WAYBAR_BATTERY", "BAT0")

# Bar text mode is toggled by battery-click.sh (left-click):
#   "power" -> show watts (default)   ·   "vi" -> show amps + volts
STATE_DIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
MODE_FILE = os.path.join(STATE_DIR, "waybar-battery-mode")


def bar_mode():
    try:
        with open(MODE_FILE) as f:
            m = f.read().strip()
            return m if m in ("power", "vi") else "power"
    except OSError:
        return "power"

# Same icon ramp as the built-in battery module in the config.
ICONS = ["󰂎", "󰁺", "󰁻", "󰁼", "󰁽", "󰁾", "󰁿", "󰂀", "󰂁", "󰂂", "󰁹"]
ICON_CHARGING = "󰂄"
ICON_PLUGGED = "󰚥"


def read(dev, name, default=None):
    try:
        with open(os.path.join(PS, dev, name)) as f:
            return f.read().strip()
    except (OSError, ValueError):
        return default


def read_int(dev, name, default=None):
    v = read(dev, name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def fmt_time(hours):
    if hours is None or hours <= 0 or hours > 100:
        return None
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    if h == 0:
        return f"{m}m"
    return f"{h}h {m:02d}m"


def active_source():
    """Return a human label for whatever is currently supplying power, or None."""
    for dev in sorted(os.listdir(PS)):
        if dev == BAT:
            continue
        online = read_int(dev, "online")
        if online != 1:
            continue
        typ = read(dev, "type") or ""
        if dev == "AC" or typ == "Mains":
            return "AC adapter"
        if typ == "USB" or dev.lower().startswith("ucsi") or "usb" in dev.lower():
            # USB-C PD: try to show negotiated voltage/current if present.
            vn = read_int(dev, "voltage_now")
            cn = read_int(dev, "current_now")
            if vn and cn:
                return f"USB-C PD ({vn/1e6:.0f}V {cn/1e6:.1f}A)"
            return "USB-C PD"
        return typ or dev
    return None


def main():
    if not os.path.isdir(os.path.join(PS, BAT)):
        print(json.dumps({"text": "", "tooltip": f"No battery {BAT}", "class": "error"}))
        return

    capacity = read_int(BAT, "capacity", 0)
    status = read(BAT, "status", "Unknown")
    charging = status == "Charging"
    full = status == "Full"

    voltage = read_int(BAT, "voltage_now")          # µV
    current = read_int(BAT, "current_now")          # µA
    power_now = read_int(BAT, "power_now")          # µW (energy-based packs)

    # Watts: prefer reported power, else V*I.
    watts = None
    if power_now:
        watts = power_now / 1e6
    elif voltage and current:
        watts = (voltage / 1e6) * (current / 1e6)

    amps = current / 1e6 if current else None
    volts = voltage / 1e6 if voltage else None

    # Charge (µAh) or energy (µWh) for health + time estimates.
    now = read_int(BAT, "charge_now")
    full_cap = read_int(BAT, "charge_full")
    design = read_int(BAT, "charge_full_design")
    unit_rate = current  # µA
    if now is None:
        now = read_int(BAT, "energy_now")
        full_cap = read_int(BAT, "energy_full")
        design = read_int(BAT, "energy_full_design")
        unit_rate = power_now  # µW

    health = None
    if full_cap and design:
        health = full_cap / design * 100.0

    # Time to full / empty.
    time_str = None
    if unit_rate and unit_rate > 0 and now is not None and full_cap is not None:
        if charging:
            time_str = fmt_time((full_cap - now) / unit_rate)
        elif status == "Discharging":
            time_str = fmt_time(now / unit_rate)

    cycles = read_int(BAT, "cycle_count")
    health_str = read(BAT, "health")
    tech = read(BAT, "technology")
    temp_raw = read_int(BAT, "temp")  # tenths of a degree C
    temp_c = temp_raw / 10.0 if temp_raw is not None else None
    model = read(BAT, "model_name")
    manufacturer = read(BAT, "manufacturer")
    thr_start = read_int(BAT, "charge_control_start_threshold")
    thr_end = read_int(BAT, "charge_control_end_threshold")

    # Active charge algorithm, e.g. "Trickle [Fast] Standard" -> "Fast".
    charge_types = read(BAT, "charge_types")
    charge_algo = None
    if charge_types:
        for tok in charge_types.split():
            if tok.startswith("[") and tok.endswith("]"):
                charge_algo = tok[1:-1]
                break

    source = active_source() if status in ("Charging", "Full", "Not charging") else None

    # --- bar text -----------------------------------------------------------
    if charging:
        icon = ICON_CHARGING
    elif full:
        icon = ICON_PLUGGED
    else:
        idx = min(len(ICONS) - 1, max(0, round(capacity / 100 * (len(ICONS) - 1))))
        icon = ICONS[idx]

    # Show the live rate next to the percent so it's visible at a glance.
    # Left-click toggles between wattage and current+voltage (mode file).
    mode = bar_mode()
    if status in ("Charging", "Discharging") and (watts or amps):
        arrow = "" if charging else ""
        if mode == "vi" and amps is not None:
            detail = f"{amps:.2f}A"
            if volts is not None:
                detail += f" {volts:.1f}V"
            text = f"{icon}  {capacity}% {arrow}{detail}"
        elif watts is not None:
            text = f"{icon}  {capacity}% {arrow}{watts:.0f}W"
        else:
            text = f"{icon}  {capacity}%"
    else:
        text = f"{icon}  {capacity}%"

    # --- css class ----------------------------------------------------------
    classes = []
    if charging:
        classes.append("charging")
    if capacity <= 10 and not charging:
        classes.append("critical")
    elif capacity <= 25 and not charging:
        classes.append("warning")

    # --- tooltip ------------------------------------------------------------
    lines = []
    head = f"<b>{status}</b> · {capacity}%"
    if time_str:
        head += f" · {'full in' if charging else 'left'} {time_str}"
    lines.append(head)
    lines.append("")

    if watts is not None:
        verb = "Charge rate" if charging else ("Draw" if status == "Discharging" else "Power")
        rate = f"{verb}: <b>{watts:.1f} W</b>"
        if amps is not None:
            rate += f"  ({amps:.2f} A"
            rate += f" @ {volts:.2f} V)" if volts is not None else ")"
        lines.append(rate)
    if source:
        lines.append(f"Source: {source}")
    if charge_algo and status in ("Charging", "Full", "Not charging"):
        lines.append(f"Charge mode: {charge_algo}")
    if thr_start is not None and thr_end is not None:
        lines.append(f"Charge limit: {thr_start}–{thr_end}%")

    lines.append("")
    if health is not None:
        cap_note = ""
        if full_cap and design:
            cap_note = f"  ({full_cap/1e6:.2f}/{design/1e6:.2f} Ah)"
        lines.append(f"Health: <b>{health:.0f}%</b>{cap_note}")
    if health_str:
        lines.append(f"Condition: {health_str}")
    if cycles is not None:
        lines.append(f"Cycles: {cycles}")
    if temp_c is not None:
        lines.append(f"Temp: {temp_c:.1f}°C")
    if tech:
        lines.append(f"Chemistry: {tech}")
    if model:
        who = f"{manufacturer} " if manufacturer else ""
        lines.append(f"Pack: {who}{model}")

    lines.append("")
    lines.append("<i>Left: toggle W ↔ A/V · Right: powertop</i>")

    tooltip = "\n".join(lines).strip()

    print(json.dumps({"text": text, "tooltip": tooltip, "class": classes}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never let the bar break
        print(json.dumps({"text": "󰂑", "tooltip": f"battery error: {e}", "class": "error"}))
