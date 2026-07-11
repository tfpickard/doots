#!/usr/bin/env python3
"""Waybar weather module.

Location is resolved from your public IP (ipinfo.io, wttr.in fallback) and
weather comes from Open-Meteo (free, no API key, reliable). Results are cached
so the bar never hammers the network:

    location  -> ~/.cache/waybar/weather-location.json   (6 h TTL)
    weather   -> ~/.cache/waybar/weather.json            (15 min TTL)

Output is a single line of Waybar JSON: {text, tooltip, class, alt}.

Why not geoclue? Mozilla Location Service (geoclue's Wi-Fi backend) was shut
down in 2024, so IP geolocation is now both simpler and more reliable.

Env:
    WEATHER_UNIT = f | c   (default: f — user is in the US)
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse

CACHE_DIR = os.path.expanduser("~/.cache/waybar")
LOC_CACHE = os.path.join(CACHE_DIR, "weather-location.json")
WX_CACHE = os.path.join(CACHE_DIR, "weather.json")
LOC_TTL = 6 * 3600
WX_TTL = 15 * 60
UNIT = os.environ.get("WEATHER_UNIT", "f").lower()
FAHRENHEIT = not UNIT.startswith("c")

# WMO weather code -> (description, day glyph, night glyph)
# Glyphs are Nerd Font "weather" icons (verified present in JetBrainsMono NF).
SUN, MOON = "\U000f0599", "\U000f0594"  # md-weather placeholders (overridden below)
WMO = {
    0:  ("Clear",            "\ue30d", "\ue32b"),
    1:  ("Mainly clear",     "\ue30d", "\ue32b"),
    2:  ("Partly cloudy",    "\ue302", "\ue37e"),
    3:  ("Overcast",         "\ue312", "\ue312"),
    45: ("Fog",              "\ue303", "\ue346"),
    48: ("Rime fog",         "\ue303", "\ue346"),
    51: ("Light drizzle",    "\ue309", "\ue326"),
    53: ("Drizzle",          "\ue309", "\ue326"),
    55: ("Dense drizzle",    "\ue318", "\ue325"),
    56: ("Freezing drizzle", "\ue3ad", "\ue3ad"),
    57: ("Freezing drizzle", "\ue3ad", "\ue3ad"),
    61: ("Light rain",       "\ue308", "\ue325"),
    63: ("Rain",             "\ue318", "\ue318"),
    65: ("Heavy rain",       "\ue318", "\ue318"),
    66: ("Freezing rain",    "\ue3ad", "\ue3ad"),
    67: ("Freezing rain",    "\ue3ad", "\ue3ad"),
    71: ("Light snow",       "\ue30a", "\ue327"),
    73: ("Snow",             "\ue31a", "\ue31a"),
    75: ("Heavy snow",       "\ue31a", "\ue31a"),
    77: ("Snow grains",      "\ue31a", "\ue31a"),
    80: ("Light showers",    "\ue309", "\ue326"),
    81: ("Showers",          "\ue318", "\ue318"),
    82: ("Violent showers",  "\ue318", "\ue318"),
    85: ("Snow showers",     "\ue30a", "\ue327"),
    86: ("Snow showers",     "\ue31a", "\ue31a"),
    95: ("Thunderstorm",     "\ue30f", "\ue32a"),
    96: ("Thunder + hail",   "\ue31d", "\ue31d"),
    99: ("Thunder + hail",   "\ue31d", "\ue31d"),
}
ICON_HUMIDITY = "\ue373"
ICON_WIND = "\ue34b"
ICON_FEELS = "\ue350"
ICON_SUNRISE = "\ue34c"
ICON_SUNSET = "\ue34d"
ICON_HILO_HI = "\U000f0512"  # thermometer-high
ICON_HILO_LO = "\U000f0511"  # thermometer-low
ICON_UMBRELLA = "\ue371"


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "waybar-weather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _fresh(path, ttl):
    try:
        return (time.time() - os.path.getmtime(path)) < ttl
    except OSError:
        return False


def _read(path):
    with open(path) as f:
        return json.load(f)


def _write(path, obj):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def get_location():
    if _fresh(LOC_CACHE, LOC_TTL):
        try:
            return _read(LOC_CACHE)
        except Exception:
            pass
    loc = None
    # 1) ipinfo.io
    try:
        d = _get("https://ipinfo.io/json")
        lat, lon = d["loc"].split(",")
        loc = {"lat": float(lat), "lon": float(lon),
               "city": d.get("city", ""), "region": d.get("region", "")}
    except Exception:
        loc = None
    # 2) wttr.in fallback
    if loc is None:
        try:
            d = _get("https://wttr.in/?format=j1")
            a = d["nearest_area"][0]
            loc = {"lat": float(a["latitude"]), "lon": float(a["longitude"]),
                   "city": a["areaName"][0]["value"], "region": a["region"][0]["value"]}
        except Exception:
            loc = None
    if loc:
        _write(LOC_CACHE, loc)
    return loc


def get_weather():
    loc = get_location()
    if not loc:
        raise RuntimeError("no location")
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "current": "temperature_2m,apparent_temperature,weather_code,is_day,"
                   "relative_humidity_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,"
                 "precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 1,
    }
    if FAHRENHEIT:
        params.update({"temperature_unit": "fahrenheit",
                       "wind_speed_unit": "mph"})
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    data = _get(url)
    data["_loc"] = loc
    return data


def build_output(data):
    cur = data["current"]
    daily = data["daily"]
    loc = data["_loc"]
    unit = "°F" if FAHRENHEIT else "°C"
    wunit = "mph" if FAHRENHEIT else "km/h"
    code = int(cur["weather_code"])
    is_day = int(cur.get("is_day", 1)) == 1
    desc, day_icon, night_icon = WMO.get(code, ("Unknown", "\ue374", "\ue374"))
    icon = day_icon if is_day else night_icon
    temp = round(cur["temperature_2m"])
    feels = round(cur["apparent_temperature"])
    hi = round(daily["temperature_2m_max"][0])
    lo = round(daily["temperature_2m_min"][0])
    hum = round(cur["relative_humidity_2m"])
    wind = round(cur["wind_speed_10m"])
    pop = daily.get("precipitation_probability_max", [None])[0]
    sunrise = daily["sunrise"][0].split("T")[-1]
    sunset = daily["sunset"][0].split("T")[-1]
    place = loc.get("city") or ""
    if loc.get("region"):
        place = f"{place}, {loc['region']}" if place else loc["region"]

    text = f"{icon}  {temp}{unit}"
    pop_line = f"\n{ICON_UMBRELLA}  {pop}% precip" if pop is not None else ""
    tooltip = (
        f"<b>{desc}</b>  {temp}{unit}   {place}\n"
        f"{ICON_FEELS}  Feels {feels}{unit}"
        f"    {ICON_HILO_HI} {hi}{unit}  {ICON_HILO_LO} {lo}{unit}\n"
        f"{ICON_HUMIDITY}  {hum}% humidity"
        f"    {ICON_WIND}  {wind} {wunit}"
        f"{pop_line}\n"
        f"{ICON_SUNRISE}  {sunrise}    {ICON_SUNSET}  {sunset}"
    )
    cls = "day" if is_day else "night"
    if code in (95, 96, 99):
        cls = "storm"
    elif code in (71, 73, 75, 77, 85, 86):
        cls = "snow"
    elif code in (61, 63, 65, 80, 81, 82, 51, 53, 55):
        cls = "rain"
    return {"text": text, "tooltip": tooltip, "class": cls, "alt": desc}


def main():
    if _fresh(WX_CACHE, WX_TTL):
        try:
            sys.stdout.write(json.dumps(_read(WX_CACHE)))
            return
        except Exception:
            pass
    try:
        out = build_output(get_weather())
        _write(WX_CACHE, out)
    except Exception:
        # Fall back to stale cache if we have one, else a quiet placeholder.
        try:
            out = _read(WX_CACHE)
        except Exception:
            out = {"text": "\ue374", "tooltip": "Weather unavailable", "class": "error"}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
