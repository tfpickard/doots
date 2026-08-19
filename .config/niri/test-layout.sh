#!/usr/bin/env bash
# Check the multi-monitor layout defined in config.kdl.
#
# The two external monitors are identical Dell P2419H panels, so niri can only
# tell them apart by the unique EDID *serial number* baked into each panel.
# This script identifies each monitor by that serial (not by connector name),
# which is exactly why the layout survives swapping HDMI/DP cables.
#
# Usage:
#   ./test-layout.sh           Verify current layout matches the expected map.
#   ./test-layout.sh --reload  Re-apply config.kdl (niri msg action
#                              load-config-file), then verify. Use this after
#                              editing config.kdl.
#   ./test-layout.sh --watch   Re-verify whenever the outputs change. Leave it
#                              running, physically swap the HDMI/DP cables, and
#                              watch it confirm the layout stays correct.
set -uo pipefail

# Expected layout: "<kind>:<key>=<expected_logical_x>"
#   serial:<edid-serial>  -> match a monitor by its EDID serial (cable-proof)
#   name:<connector>      -> match a monitor by its connector name
EXPECTED=(
    "serial:BJ4X5X2=0"      # left-most external
    "serial:920C993=1920"   # center external
    "name:eDP-1=3840"       # right-most built-in laptop panel
)

verify() {
    NIRI_OUTPUTS_JSON="$(niri msg -j outputs)" \
        python3 - "${EXPECTED[@]}" <<'PY'
import json, os, sys

specs = []
for arg in sys.argv[1:]:
    sel, want_x = arg.split("=")
    kind, key = sel.split(":", 1)
    specs.append((kind, key, int(want_x)))

outputs = list(json.loads(os.environ["NIRI_OUTPUTS_JSON"]).values())
by_serial = {o.get("serial"): o for o in outputs}
by_name = {o.get("name"): o for o in outputs}

ok = True
for kind, key, want_x in specs:
    o = (by_serial if kind == "serial" else by_name).get(key)
    if not o:
        print("MISSING  %s=%s (expected x=%d)" % (kind, key, want_x))
        ok = False
        continue
    got_x = o["logical"]["x"]
    status = "OK  " if got_x == want_x else "FAIL"
    if got_x != want_x:
        ok = False
    print("%s %-9s %-12s [%s] on %-6s x=%d (want %d)" % (
        status, o.get("make"), o.get("model"), key, o.get("name"), got_x, want_x))

print()
print("RESULT:", "PASS - layout matches config" if ok else "FAIL - layout drifted")
sys.exit(0 if ok else 1)
PY
}

case "${1:-}" in
    --reload)
        echo "==> Reloading config.kdl..."
        niri msg action load-config-file
        sleep 1
        verify
        ;;
    --watch)
        echo "==> Watching for output changes (Ctrl-C to stop)."
        echo "    Swap your HDMI/DP cables now and watch the result stay PASS."
        echo
        last=""
        # Re-verify on every output-related event from the compositor.
        niri msg event-stream 2>/dev/null | grep --line-buffered -iE "output" |
        while IFS= read -r _; do
            now="$(verify 2>&1)"
            if [[ "$now" != "$last" ]]; then
                echo "----- $(date '+%H:%M:%S') -----"
                echo "$now"
                last="$now"
            fi
        done
        ;;
    "" )
        verify
        ;;
    * )
        echo "Unknown option: $1" >&2
        echo "Usage: $0 [--reload | --watch]" >&2
        exit 2
        ;;
esac
