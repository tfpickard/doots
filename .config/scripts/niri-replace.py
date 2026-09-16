#!/usr/bin/env python3
"""Re-place the ten fixed-desk apps without launching anything new.

For after a dock cycle scrambles things -- a monitor reconnects and a named
workspace's windows ended up somewhere else, or you want the fixed desk
re-sorted without relaunching every app. Same engine as
niri-autostart-apps.py, just with spawning disabled: it only adopts and
moves windows that already exist.

Bind this to a key, or run it by hand after docking/undocking.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import niri_placement  # noqa: E402


if __name__ == "__main__":
    niri_placement.run(spawn=False)
