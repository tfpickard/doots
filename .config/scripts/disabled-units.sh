#!/usr/bin/env bash
# List service units that are currently disabled but could be enabled, limited
# to long-running daemons.
#
#   disabled-units.sh [--user]
#
# "Long-running" is tested by *excluding* Type=oneshot rather than requiring
# Type=forking. forking is a legacy double-fork convention that almost nothing
# uses any more (exactly one unit on this machine), while oneshot is the only
# service type that runs to completion and exits -- so excluding it drops
# run-once units (lid-close hooks, pcrlock, networkd-wait-online) and keeps
# every daemon regardless of how it signals readiness.
#
# --state=disabled already implies enable-able: units with no [Install] section
# report as static, and masked/alias/generated are excluded by systemd itself.
# RefuseManualStart=no additionally drops units only startable by an event.
#
# Template units are shown as foo@.service and must be enabled with an instance
# name, e.g. `systemctl enable openvpn@myconf.service`. They are queried here
# via a throwaway foo@x.service instance because `systemctl show` rejects a
# bare template name, then the real name is restored for output.
set -euo pipefail

scope=(--system)
case "${1-}" in
    --user) scope=(--user) ;;
    --system | '') ;;
    *)
        printf 'usage: %s [--user]\n' "${0##*/}" >&2
        exit 2
        ;;
esac

systemctl "${scope[@]}" list-unit-files --type=service --state=disabled --no-legend --no-pager |
    cut -d' ' -f1 | sed 's/@\.service$/@x.service/' |
    xargs -r systemctl "${scope[@]}" show --no-pager -p Id -p Type -p RefuseManualStart |
    awk -v RS= -F'\n' '{
        delete v
        for (i = 1; i <= NF; i++) { p = index($i, "="); v[substr($i, 1, p - 1)] = substr($i, p + 1) }
        if (v["Type"] != "oneshot" && v["RefuseManualStart"] == "no") {
            sub(/@x\.service$/, "@.service", v["Id"])
            print v["Id"]
        }
    }' |
    sort
