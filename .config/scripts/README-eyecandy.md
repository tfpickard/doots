# Wayland eyecandy: what's installed and how to use it

Everything here is optional. The defaults (mako, swaybg, swaylock) are
unchanged unless you opt in.

## Notification daemons

Only **one** process can own `org.freedesktop.Notifications`, so these are
mutually exclusive. Switch with the helper rather than starting one by hand:

```sh
notify-daemon.sh            # which one is running
notify-daemon.sh swaync     # slide-out control centre, DND, media controls
notify-daemon.sh fnott      # minimal, no GTK, fastest
notify-daemon.sh mako       # back to the default
notify-daemon.sh test       # fire one of each urgency to see the styling
```

| | config | notes |
|---|---|---|
| mako | `themes/active/mako.ini` | default, started by niri at login |
| swaync | `.config/swaync/` | edit `config.jsonc`, then run `generate.py` |
| fnott | `.config/fnott/fnott.ini` | square corners; fnott has no border-radius |

**swaync's config is generated.** swaync parses `config.json` with a strict
JSON parser: one `//` comment makes the entire file fail to load, and it
silently falls back to built-in defaults with only a `CRITICAL` on stderr.
So the documented version lives in `config.jsonc` and:

```sh
~/.config/swaync/generate.py          # rewrite config.json
~/.config/swaync/generate.py --check  # CI-style check that it's current
```

The packaged `swaync.service` is **masked** (`systemctl --user mask
swaync.service`). It ships globally enabled in `/etc/systemd/user`, and would
otherwise race mako for the bus name at every login.

Keybinds: `Mod+N` toggle centre, `Mod+Shift+N` dismiss all, `Mod+Ctrl+N` DND
(via `dnd.sh`, which papers over mako and swaync spelling it differently --
mako has no toggle flag at all, only add/remove).

## Screen lockers

`lock.sh` picks the best available and is what `Super+Alt+L` and swayidle use:

```sh
lock.sh              # $LOCKER, else effects -> swaylock -> gtklock
lock.sh swaylock     # force the plain packaged one
export LOCKER=swaylock   # change the default, in ~/.extra
```

| | binary | config |
|---|---|---|
| swaylock | `/usr/bin/swaylock` | `.config/swaylock/config` |
| swaylock-effects | `~/.local/bin/swaylock-effects` | `.config/swaylock-effects/config` |
| gtklock | `/usr/bin/gtklock` | `.config/gtklock/{config.ini,style.css}` |

### Silicon Graphics styling

Both swaylock configs are **pinned to the SGI palette** (`#29558e` indigo and
white) rather than following the desktop theme, so the lock always matches its
background image. They have no `THEME:` markers, which makes `theme-set` a
no-op on them — it only substitutes where a marker matches. Put markers back
above the colour lines to re-enable theme-following.

The background is generated per output by `lock-background.py`, which lifts the
white logo out of `~/Pictures/Wallpaper/indigo.png` as an alpha mask and
re-composites it at each monitor's exact resolution:

```sh
lock-background.py            # regenerate for connected outputs
lock-background.py --list     # show what it would generate
```

Per output, rather than one image scaled across all of them, because
`--scaling fill` crops a single picture differently on a 1920x1080 panel than
on a 1920x1200 one and the logo ends up in a different place on each screen.
`lock.sh` regenerates them and passes the `-i <output>:<path>` pairs, which is
why you should lock through the script rather than calling swaylock directly.

Set `SGI_LOCK=0` to skip all of that and use the plain configured background.

### niri gotchas, both worked around

* **swaylock-effects' `screenshots` doesn't work on niri.** It grabs the screen
  *after* taking the session lock, and while locked niri renders only the lock
  surface over a solid clear colour (`CLEAR_COLOR_LOCKED`, `src/niri.rs`), so
  you get a blurred dark-red rectangle. Irrelevant now that the background is
  the SGI image, but that's why the option is off.
* **gtklock needs `-i`.** It otherwise reaches for `wlr-input-inhibitor`, which
  niri doesn't implement, and aborts. It also does **not** expand `~` in its
  config, so paths there must be absolute or you silently get an unstyled lock.

## Screensaver

Wayland has no xscreensaver equivalent, because nothing can draw over a lock
screen. `lock-screensaver.py` does the other half instead — and it now puts a
**different vintage hack on every monitor**:

```sh
lock-screensaver.py list        # installed hacks + the vintage shortlist
lock-screensaver.py test pipes  # audition one on every screen
```

Timings, set in the niri config's swayidle line:

| after | happens |
|---|---|
| 10 min | one vintage hack per monitor, fullscreen |
| any input | hacks are killed, you're back where you were |
| 45 min | hacks stop, screen locks for real |
| 46 min | screens off (battery only — `idle-dpms.sh` no-ops on AC) |

DPMS sits *after* the lock deliberately. With the lock at 45 minutes, blanking
at the old 15 would have left the machine dark but **unlocked** for half an
hour. The cost is 35 minutes of GL hacks before the lock; move the DPMS
timeout down if you'd rather have the battery back.

The shortlist favours period pieces — `atlantis` and `sproingies` are the
actual SGI IRIX demos, `pipes` is Windows 95, `flyingtoasters` is After Dark
1989, plus the early Mesa/GLX demos and the original 2D X11 hacks. Hacks that
mangle screen contents (`decayscreen`, `slidescreen`, `xanalogtv`) are never
auto-selected: there's nothing behind them on Wayland, so they just look
broken. `test` still runs them.

**Multi-monitor placement is done over IPC, not by window rule.** Each hack
sets its own app-id from its name (`Atlantis`, `Flurry`, `GLMatrix`), so a
niri rule can only fullscreen them generically — matching on *title*, which
they all share. Which screen each lands on is then set with
`niri msg action move-window-to-monitor --id <id> <output>`, one at a time so
each new window can be identified before the next appears.

## Wallpaper

swaybg, awww and mpvpaper all draw to the same layer, so they're exclusive:

```sh
wallpaper.sh                    # what's running
wallpaper.sh static [PATH]      # swaybg (the login default)
wallpaper.sh anim PATH          # awww, with a transition
wallpaper.sh video PATH         # mpvpaper, muted and looping
wallpaper.sh off
```

**awww is the maintained successor to swww** -- renamed October 2025 and moved
to Codeberg; the old `LGFae/swww` GitHub repo is archived. Installed to
`~/.local/bin`.

## Night light

`wlsunset` runs from the niri config (it has no config file, only flags). The
coordinates are Denver, matching the system timezone. Raise `-t` toward 4500 if
3600 is too orange to work in.

## Terminal

`cbonsai` presets are aliases, since it has no config file:

```sh
bonsai          # grow one tree
bonsai-idle     # infinite screensaver mode, any key quits
bonsai-zen      # slow, dense, seasonal leaves
bonsai-print    # print a finished tree and exit
```

## Building the two non-packaged tools

```sh
# awww (animated wallpaper)
sudo apt install liblz4-dev
git clone https://codeberg.org/LGFae/awww && cd awww
cargo build --release
install -m755 target/release/awww target/release/awww-daemon ~/.local/bin/

# swaylock-effects (blur + clock)
sudo apt install meson libpam0g-dev libcairo2-dev libxkbcommon-dev \
                 libgdk-pixbuf-2.0-dev scdoc wayland-protocols libwayland-dev
git clone https://github.com/jirutka/swaylock-effects && cd swaylock-effects
meson setup build --prefix=$HOME/.local -Dman-pages=disabled
ninja -C build
install -m755 build/swaylock ~/.local/bin/swaylock-effects
```

`jirutka/swaylock-effects` is the more recently updated fork (2024) -- the
original `mortie/swaylock-effects` was last touched in 2023. Neither is
actively developed, so treat the fork as "works today", not "maintained".
Installing it as `swaylock-effects` deliberately leaves the packaged
`/usr/bin/swaylock` untouched as a fallback.

## Theming

`theme-set` restyles all of this. swaync picks colours up through a CSS
`@import` of `themes/active/waybar.css`; swaylock, swaylock-effects and fnott
have no include mechanism, so their colour values are rewritten in place under
`# THEME:<key>` marker lines.

Those markers are on their own lines because **swaylock does not strip trailing
`#` comments** -- `color=0f1113  # THEME:lock-bg` is parsed as the literal
colour and silently falls back to white. Existing alpha is preserved, so the
translucent `rrggbbaa` values in the effects config survive a theme switch.

gtklock's `style.css` is plain GTK CSS with inlined colours; it is not
currently rewritten by `theme-set`.

## SDDM greeter

`.config/sddm/sgi-sddm/` is an SGI-styled greeter matching the lock screen, so
the machine looks the same before and after login. Install and activate it
with:

```sh
make sddm
```

That symlinks it into `/usr/share/sddm/themes`, points
`/etc/sddm.conf.d/theme.conf.user` at it, and installs JetBrainsMono
system-wide — the greeter runs as the `sddm` user and cannot see fonts in your
home. See the theme's own README for the details, including how to roll back.
