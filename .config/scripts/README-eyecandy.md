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

Two niri-specific gotchas, both worked around already:

* **swaylock-effects' `screenshots` does not work on niri.** It grabs the
  screen *after* taking the session lock, and while locked niri renders only
  the lock surface over a solid clear colour (`CLEAR_COLOR_LOCKED` = dark red,
  `src/niri.rs`) -- so you get a blurred red rectangle. `lock.sh` captures the
  desktop with `grim` first and passes it in with `--image`, then deletes the
  capture (it's a plaintext picture of your unlocked screen).
* **gtklock needs `-i`.** It otherwise tries `wlr-input-inhibitor`, which niri
  doesn't implement, and aborts. It also does **not** expand `~` in its config,
  so paths there must be absolute.

## Screensaver

Wayland has no xscreensaver equivalent, because nothing can draw over a lock
screen. `lock-screensaver.py` does the other half instead: swayidle runs a
random GL hack at 5 minutes, any input dismisses it, and a real lock takes over
at 10.

```sh
lock-screensaver.py list        # 258 hacks; shortlist is FAVOURITES in the file
lock-screensaver.py test pipes  # audition one
```

The hacks are X11, so they run through `xwayland-satellite`. A niri window rule
matches on **title** (`from the XScreenSaver`) rather than app-id, because each
hack sets its own app-id -- `Atlantis`, `Flurry`, `GLMatrix` -- so an app-id
rule only ever fullscreens the one hack it names.

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
