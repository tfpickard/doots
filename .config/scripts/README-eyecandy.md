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
lock-screensaver.py shuffle     # a new random hack on each screen
```

### Driving it by hand

| key | |
|---|---|
| `Mod+Z` | screensaver now, on every screen — exactly what the 10-minute timeout does |
| `Mod+Shift+Z` | **new random animation on each screen, without dismissing it** |
| `Mod+Ctrl+Shift+Z` / `Mod+Alt+Z` | walk the shortlist in order instead, forwards / back |
| `Mod+Ctrl+Z` | atlantis on the built-in panel — and the off switch for any hack |
| `Mod+Ctrl+T` | **just the journal text on the built-in panel**, toggled; stays up while you work |
| anything else | dismisses the screensaver, as always |

All of these act on **every monitor**, one hack per screen; only `Mod+Ctrl+Z` and
`Mod+Ctrl+T` are single-screen. `shuffle` never hands back a hack that is already on screen,
and the ordered walk moves a screenful at a time (position remembered in
`$XDG_RUNTIME_DIR/lock-screensaver.cycle`), so with three monitors you see nine
different hacks in three presses.

There is no `xscreensaver-command -next` to bind: no xscreensaver daemon runs
here, these are the bare GL hacks on rootless XWayland, so "next" means kill and
relaunch. Cycling also clears the ambient atlantis and the `Mod+Ctrl+T` text,
since otherwise the new hack just stacks on top of them.

### The text screen keeps a journal

The left external always shows text, one line at a time — and the lines are a
**stream of consciousness**: one salty voice living inside this machine,
narrating its day, building on what it said before, and reacting (badly, and
personally) to headlines that leak in from Reddit, Hacker News, Bluesky
trending, the BBC and Wikipedia's current-events portal.

```sh
screensaver-journal.py --status   # entries, next one due, its current boulder
screensaver-journal.py --news     # the headlines it would see right now
screensaver-journal.py --force    # write an entry now
screensaver-phrase.py             # the next line, exactly as the screen gets it
lock-screensaver.py text          # the text itself, on the laptop panel (Mod+Ctrl+T);
                                  # again to stop; -o DP-2 for another screen
```

`screensaver-journal.timer` checks every 20 minutes; an entry is due every
2.3–4.2 hours, or straight after a reboot or an hour-plus sleep. The voice only
exists while the machine is awake — entries are never dated inside a shutdown or
suspend, and on waking it is told how long it was gone. A reboot also resets the
task it grinds at daily, which is the point.

Everything grown lives in `~/.local/share/lock-screensaver/` (`journal.jsonl`,
`memory.json`), deliberately outside the repo. `--backfill "2026-10-11 23:08"`
reconstructs entries from the machine's real boot/suspend history and each day's
real news; the v1 random-phrase corpus survives as `phrases-master.txt`, which
the picker still resurfaces as old memories. The v1 code is tagged
`screensaver-phrases-v1`, and snapshots live under `backups/` in that directory.

The entries are written by the Copilot CLI. If it reports the monthly quota as
used up, the generator waits 6 hours before trying again (the usual 45 minutes
would only resubmit a request that is guaranteed to fail), and the journal picks
up again by itself once the quota resets. The first week, 11–19 October 2026,
was written while the quota was exhausted, so it was written by hand as the
voice. It went through the generator's own line filters and is built on the
real boot/suspend history and real headlines; those entries are tagged `model:
"hand-authored backfill …"` in `journal.jsonl`. A local `qwen2.5:7b` was tried
as a fallback and dropped: it copied the example lines word for word and ignored
the news.

X/Twitter is deliberately absent: it serves nothing without a login, and its
usual mirror (nitter) is now just a placeholder page. Bluesky's public trending
topics stand in for it.

### How "every key except that one" works

swayidle cannot tell the cycle keys from any other key: it only knows the
session stopped being idle, and the keypress asking for a new animation is
input like any other. So the decision is made in the script instead —
`resume` runs `lock-screensaver.py wake`, not `stop`:

1. the keybind runs `shuffle`, which first drops a marker file;
2. `wake` waits ~350ms, long enough for that marker to appear whichever of the
   two the compositor happens to run first;
3. marker present → leave the hacks up, the cycle is already replacing them.
   No marker → this was a real "I'm back", so stop.

Dismissal after the first cycle is handled by a **second swayidle** with a
one-second timeout, started alongside the hacks and killed with them. The main
one fires `resume` only once per idle period, so from the first cycle onwards it
is spent — without the watcher the screensaver would be up with no key left that
could dismiss it.

That watcher is killed with `SIGKILL` rather than `SIGTERM` on purpose: swayidle
runs its `resume` command as it exits if it happens to be idle at the time, and
a dying watcher's parting `wake` will otherwise land on the *next* screensaver a
few seconds later and kill it on sight.

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

**If the screensaver flashes up and vanishes**, the `:12` XWayland has wedged:
the socket file is still there and even `xdpyinfo` answers, but no window ever
reaches the screen, so every hack exits within a quarter of a second. The script
detects a hack that dies before it has a window, replaces the server and retries
once, so this should heal itself; `pkill -f 'xwayland-satellite :12'` is the
manual version.

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
