#!/usr/bin/env bash
# Launch the "always running" workspace apps once, at niri startup.
#
# Placement is NOT done here -- it is done by `open-on-output` window rules in
# ~/.config/niri/config.kdl, which is more reliable because it also applies to
# windows these apps spawn later (a second VS Code window, a Teams call popout,
# a Chrome PWA relaunched from the tray).
#
# Everything is guarded by a "is it already running" check so re-running this,
# or reloading niri, never gives you two copies.
#
# Called from niri via spawn-at-startup.

set -u

CHROME=/opt/google/chrome/google-chrome
# Chrome PWA app-ids (see ~/.local/share/applications/chrome-*.desktop).
TEAMS_APP_ID=cifhbcnohmdccbgoicgdjpfamggdegmo

# Give niri a moment to bring up the external outputs. The `open-on-output`
# window rules fall back to the focused output when the named monitor isn't
# connected *yet*, so launching before the docks are advertised would park these
# windows on the built-in panel.
sleep 3

have() { command -v "$1" >/dev/null 2>&1; }

# --- VS Code Insiders (left-most external) ----------------------------------
if have code-insiders && ! pgrep -f '/code-insiders(\s|$)' >/dev/null 2>&1; then
    code-insiders >/dev/null 2>&1 &
fi

# --- Microsoft Teams PWA (centre external) ----------------------------------
if [ -x "$CHROME" ] && ! pgrep -f -- "--app-id=$TEAMS_APP_ID" >/dev/null 2>&1; then
    "$CHROME" --profile-directory=Default --app-id="$TEAMS_APP_ID" >/dev/null 2>&1 &
fi

# Don't `wait`: the launcher's job is done once both are started, and the apps
# keep running after it exits.
exit 0
