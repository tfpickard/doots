#!/usr/bin/env python3
"""Launch and place the ten fixed-desk workspace apps at niri startup.

Placement logic lives in niri_placement.py -- see that file's docstring for
the algorithm (why launches are serialized, how the ambiguous Chrome/ghostty
windows get told apart). This is just the "launch what's missing" entry
point; `niri-replace.py` is the "fix what's already there" one, for after a
dock cycle.

Called from niri via spawn-at-startup (config.kdl).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import niri_placement  # noqa: E402


if __name__ == "__main__":
    niri_placement.run(spawn=True)
