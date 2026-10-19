# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Overview

This is a personal dotfiles repository, primarily for a Linux/niri desktop with some macOS configs (zsh, tmux, ghostty) that also apply there. The repo is managed with git and deployed by symlinking or copying files to their target locations in `$HOME`.

## Repository Structure

| Path | Purpose |
|------|---------|
| `.zshrc` | Zsh shell configuration |
| `.aliases` | Shell aliases (sourced by `.zshrc`) |
| `.tmux.conf` | Tmux configuration |
| `.config/ghostty/` | Ghostty terminal emulator config |
| `.config/niri/` | niri window manager (Linux) -- the live WM; see below |
| `.config/hypr/` | Hyprland window manager config -- **dormant**, not the active WM (see note below) |
| `.config/nvim/` | Neovim configuration (git submodule: tfpickard/dotenvim) |
| `.config/waybar/` | Waybar status bar (Linux) |

## Key Architectural Patterns

### niri is the live window manager; hypr is dormant, not deleted
This repo was originally built around Hyprland (see `.config/hypr/`, a full preset-based config with 25 scripts); an eww sidebar that went with it has since been removed. The desktop now runs **niri**, and `hypr/` isn't wired into it: `niri/config.kdl` never references it. It's kept in the repo deliberately rather than deleted -- if you ever go back to Hyprland, the preset system in `hypr/conf/` is a complete, working config, not an abandoned fragment. `waybar/scripts/compositor-config.py`'s "hyprland" mode is the one live bridge between the two setups: it derives a Hyprland-compatible bar config from the same niri theme source, for exactly the day this might get used again.

`dunst` is genuinely stale rather than dormant-by-design: it's not in the notification-daemon switcher (`scripts/notify-daemon.sh`), not in `theme-set`'s applier table, and its only callers are inside the dormant `hypr/` tree. `mako`/`swaync`/`fnott` are the three real, switchable options.

### niri: a fixed desk, not ad-hoc tiling
`niri/config.kdl` declares ten **named workspaces** (`workspace "name" { open-on-output "..." }`), each pinned to a physical monitor, rather than letting dynamic workspaces accumulate however they land:

| Workspace | Output | Contents |
|---|---|---|
| `code`, `agents` | left external (`BJ4X5X2`) | VS Code, two windows, full-bleed (per-workspace `layout{}` override: `gaps 0`) |
| `chat`, `mail`, `web1`, `web2`, `term1` | centre external (`920C993`) | Teams+Slack, Outlook, browsing, one terminal |
| `web3`, `term2`, `term3` | laptop panel (`eDP-1`) | remaining browsing/terminals |

`Mod+1`..`Mod+0` focus these **by name**, not index -- workspace index is per-output, so on an unnamed setup the same key means a different workspace depending which monitor has focus. Window-rules (`open-on-workspace`) place Teams/Slack/Outlook/VS Code, since their app-ids are unambiguous (VS Code's two windows are told apart by title). Three plain Chrome windows and three ghostty windows are NOT distinguishable this way -- they share an app-id with their siblings -- so `scripts/niri_placement.py` places those six over IPC at startup, by serializing launches so "the newest matching window nobody has claimed yet" is unambiguous even though the windows themselves are identical. `scripts/niri-autostart-apps.py` and `scripts/niri-replace.py` are two thin entry points into that one engine (launch vs. re-place-only, for after a dock cycle).

**A real trap hit while building this:** `layer-rule { match namespace="^wallpaper$"; place-within-backdrop true }` looks like it should make the wallpaper additionally visible in the Overview -- it actually redirects the surface into backdrop-compositing *instead of* its normal spot, replacing the desktop background with flat grey outside the Overview. niri auto-reloads `config.kdl` on save (no explicit `load-config-file` needed), so this went live immediately and was only caught by a screenshot. Not currently used in this config for that reason.

### Waybar draws one bar per output, generated from a single source
The committed theme (`waybar/themes/dope/config`) is one bar definition; `launch.sh` calls `compositor-config.py niri-outputs` to expand it into an array, one entry per connected monitor, before waybar ever sees it. Both `custom/niriws` and `custom/niriwindow` take a `--output <connector>` flag so each bar shows only its own monitor's workspaces and focused window -- without this, all ten named workspaces (and whichever window is globally focused) would show identically on every bar.

**The trap:** waybar's `"output"` config key matches the Wayland *connector* name (`DP-2`, `eDP-1`), which is exactly what `niri/config.kdl`'s `output` blocks deliberately do NOT key on (they use `"make model serial"`, because connector names change when cables move between ports). The generator resolves serial -> current connector from `niri msg -j outputs` at launch time, not at config-write time. `output-watch.py` restarts waybar when the connected-output set changes (inferred from `WorkspacesChanged`, since niri's IPC has no dedicated output-change event), debounced 1s since docking fires a burst of these.

The Hyprland-conversion mode described in "Waybar status modules" below is the other branch of this same generator, not a separate code path.

### Ghostty config is modular
`.config/ghostty/config` uses `config-file =` directives to compose from sub-directories:
- `font/<name>` — font settings (currently `monaspace-neon`)
- `leading/<n>` — line height adjustment (currently `default`)
- `theme/<name>` — color theme (currently `catppuccin-mocha`)
- `opacity/<pct>` — background opacity (currently `85%`)
- `shader/<name>` — custom GLSL shader (currently `underwater`)

To change any of these, edit the `config-file =` lines in `.config/ghostty/config` to point to a different file in the same subdirectory.

### Zsh plugins managed by znap
`.zshrc` uses [znap](https://github.com/marlonrichert/zsh-snap) (cloned to `~/Repos/znap/`) to lazily load plugins from GitHub. Additional completions go in `~/.config/zsh/completions/`. Slow eval results are cached with `mroth/evalcache`.

Sourcing order: `.zshrc` -> `.aliases` -> `.functions` -> `.exports` -> `.path` -> `.extra`

### Tmux plugins managed by TPM
`.tmux.conf` uses [TPM](https://github.com/tmux-plugins/tpm) at `~/.tmux/plugins/tpm/`. The prefix is remapped to `C-a`. Plugins are installed/updated with `prefix + I`.

Custom keybindings of note:
- `prefix + C-g` / `prefix + g` — summon Muxgeist AI pane
- `prefix + h` — open sidechat pane
- `prefix + j` — open sc-picker popup
- `Alt+backtick` (no prefix) — toggle a popup on the persistent `scratch` session (shared with niri's `Mod+Space`)

### Scratch terminals: two of them, on persistent tmux sessions
`scripts/scratch-term.sh` emulates a scratchpad over IPC, because niri doesn't have one. There are two independent terminals, each with its own window, its own tmux session and its own look:

| Key | Window | tmux session | Look (`ghostty/scratch/*`) |
|---|---|---|---|
| `Mod+Space` | centred float, 70% x 65%, heavy drop shadow | `scratch` | plum, cursor-smear shader |
| `Mod+Shift+Space` | fills the working area, translucent, desktop blurred behind it | `scratch-full` | teal, falling-snow shader |

The `Alt+backtick` popup inside any tmux client (`.tmux.conf`) attaches to the same `scratch` session as `Mod+Space`, so they share shells.

- **Toggling:** the first press spawns the terminal. Later presses summon it, or, if it already has focus, park it on the unpinned named workspace `scratch` and give focus back to whatever had it before the summon (kept in `$XDG_RUNTIME_DIR/scratch-term.<variant>.prev`).
- **Telling them apart:** each is a ghostty with its own `--class` (`dev.tom.scratch`, `dev.tom.scratch-full`), so niri's window rules can match it. Each also gets its own `--config-file`, which loads after the main config and therefore wins over the theme, opacity and shader picks.
- **Which display:** it is summoned onto a display that does *not* hold the focus, so the window you are working in stays visible:
  - with 2 or more external screens, the nearest other external (never the laptop panel);
  - with 1 external, the other of the two displays;
  - with none, the only display.

  "Nearest" means the smallest gap between screen edges, then the closest centres, then left-to-right. `scratch-term.sh pick-output` exposes this rule, and `tests/test-scratch-term.sh` covers each case.
- **The full-screen one is a float, not fullscreen:** niri draws a solid backdrop behind real fullscreen windows, so a translucent one would never show anything through it. It is a float sized to 100% of the working area, which leaves waybar visible. `background-effect { blur true; xray false; }` blurs the actual windows underneath; niri marks this kind of blur experimental, and it disappears during open/close animations.
- **Focus-follows-mouse:** focus-follows-mouse is on and `warp-mouse-to-focus` is off, so after a summon the pointer is still on the other screen. Nudging the mouse hands focus back to the window under it; pressing the key again refocuses the scratch terminal, and the press after that hides it.
- **`exit`:** both launchers set `detach-on-destroy on` for their session. With the global `off`, `exit` would otherwise move the scratch window to another session instead of closing it.

### Hyprland config uses switchable presets (dormant)
`.config/hypr/conf/` contains named preset files for animations, decorations, layouts, monitors, and window borders. The active preset for each category is referenced from the parent `.conf` file (e.g., `animation.conf` sources one of `conf/animations/*.conf`). Not currently read by anything -- see "niri is the live window manager" above.

### Waybar layout is deliberately compact
The bar is sized to survive its worst case: a long window title used to push the right-hand island clean off the screen. Guards against that:

- `custom/niriwindow` caps the title at 34 characters, in `scripts/niri-window.py` (`MAX_LEN`, which ellipsises) *and* as a `max-length` backstop in the config and in `scripts/compositor-config.py`'s Hyprland variant. Change all three together.
- Base font is 11px, module padding is `0 5px`, and bar `spacing` is 2.

### Waybar modules keep a fixed width
The bar used to shift horizontally whenever a reading gained or lost a digit. Two conventions prevent that, and new modules are expected to follow both:

1. **Fixed character counts.** Numeric fields are padded in `themes/dope/config` (`{usage:>3}`, `{temperatureC:>2}`), and modules with alternate formats of differing length set `min-length`. JetBrains Mono gives every digit and the space the same advance width, so equal character counts are equal pixel widths.
2. **`min-width` floors in `style.css`.** Nerd Font *icons* are not uniform width (9-16px in the set used here), so a module that swaps its icon still resizes even with the character count pinned. The floors at the bottom of `style.css` are measured (or, where a live bar wasn't available to screenshot, cross-calibrated against modules that were) from each module's widest variant -- measure/derive rather than guess when adding one.

   **The floor is not automatic, though.** `custom/weather` and `mpris` deliberately have none: a floor exists to stop *frequent* jitter (a value that updates every few seconds), and both of these change on a much longer cadence (15 minutes; once per track) where an occasional width change is the better trade against permanently reserving space for a worst case that's rarely hit. `custom-battery` (updates every 5s, state cycles constantly) is the shape that does want one. Ask "how often does this actually change" before adding a floor, not just "what's the widest it gets."

Custom scripts emit their own text, so they pad it themselves (see `scripts/cpu-freq.py`, `scripts/battery-power.py`) and swap icons in place rather than appending an extra glyph.

### Waybar separators are gradients, not borders
Modules are divided by 1px rules instead of wide padding: a **solid** rule marks a boundary between unrelated clusters, a **dotted** rule joins related readings (volume/brightness, cpu/freq/temp, memory/disk, and so on). Both are faint by design.

They are painted with `background-image` gradients rather than `border-left`, for two reasons that are easy to trip over:

1. GTK3 here renders a 1px `dotted` border as **nothing at all**, and a 1px `dashed` border as a **solid line** -- so `border-style` cannot express the related/unrelated distinction.
2. Insetting a border vertically requires margins, which push a module's minimum height above the bar's own and make waybar log `Requested height: 34 is less than the minimum height: 36`. A gradient's height is set directly with `background-size`, so no margins are needed.

The rules are anchored as the *left* edge of the first module in each run, never the right edge of the last. Modules hide themselves when they have nothing to report (mpris with no player, tray with no icons), and left-anchoring means a separator disappears with the module it belongs to instead of dangling at an island's edge.

Note that `:hover` uses `background-color`, not the `background` shorthand -- the shorthand resets `background-image` and would erase the separators on hover.

### Waybar status modules
`custom/aiagents` (`scripts/ai-agents.py`) shows live GitHub Copilot agent sessions. There is no `gh copilot status` command, so it reads what the agent writes to `~/.copilot/session-state/<id>/`: an `inuse.<pid>.lock` marks a session as owned by a running host, and replaying the tail of `events.jsonl` yields its state -- an unanswered `permission.requested` or an open `ask_user` tool call means **blocked** (red, blinking), an open turn means **working**, `session.task_complete` means **done**. The bar shows the single most urgent state, in the order blocked > working > done > idle -- `working` outranks `done` deliberately, since "done" is sticky for an hour and would otherwise show a green tick while agents were visibly still running. Its bar icon is `md-space_invaders`, deliberately not `md-robot` -- that one is already spoken for by `custom/ai` (Ask AI), and two identical robots in the same island are indistinguishable at 11px. Stale locks are common, so the owning PID must still be alive and look like a Copilot host.

Three things about that event stream are easy to get wrong, and each one silently hides live sessions:

- Sessions are shut down and resumed repeatedly (one had five of each), so `session.shutdown` must be **cleared** by a later `session.start`/`session.resume`. Treating it as terminal hides a busy session for as long as the old shutdown sits inside the replay window.
- The replay window is the tail of the file, not the whole thing -- event files reach 10MB. It widens until it contains a turn boundary, otherwise an open turn can't be told from a finished one.
- `workspace.yaml` writes the session name as a YAML block scalar (`name: |-`) when the first message spans lines, so a naive `key: value` split yields a literal `"|-"`. Sidebar chats also run with a cwd of `~/.copilot/chats/<uuid>`, which is not a useful place name.

`custom/github` (`scripts/github-status.py`) shows the review queue and activity on your own PRs, via one GraphQL query per authenticated `gh` account (work and personal are both covered, using `gh auth token --user`). Results are cached in `~/.cache/waybar-github-status.json`; waybar polls the cache often while GitHub itself is only hit every `WAYBAR_GH_TTL` seconds. "New activity" is measured against what you have acknowledged by clicking, not against wall-clock time.

### Cursor theme is generated, not downloaded
The pointer is `dmz-white-4bit`: DMZ-White rebuilt as pixel art by [.config/scripts/pixelate-cursors.py](.config/scripts/pixelate-cursors.py). Every cursor is area-downscaled to a 16x16 grid, its alpha hard-thresholded (which is what actually reads as "8-bit" -- and conveniently discards the soft drop shadow), quantised to 16 colours, then scaled back up by whole numbers so one source pixel becomes a crisp block.

Regenerate with `.config/scripts/pixelate-cursors.py DMZ-White --name dmz-white-4bit`; `--list` shows the installed themes and `--grid`/`--colors` tune the effect. Working from an existing theme means the whole cursor set comes along, including its ~38 symlinked aliases.

**Legacy themes need the modern cursor names added.** DMZ (like most older X11 themes) ships only traditional names -- `xterm`, `hand2`, `left_ptr`. Modern toolkits (GTK4, Qt, Electron, Firefox) ask by CSS name -- `text`, `pointer`, `default` -- and when those are missing the request does not fail loudly, it silently falls through to whatever other theme the app can find. The symptom is a mix: a blocky pointer in waybar but a smooth one in VS Code, or a stray red I-beam from a theme you are not even using. `CSS_ALIASES` in the generator symlinks ~41 CSS names onto whichever legacy name exists, which is what makes the theme apply uniformly.

Two things to keep in mind:

- **The generated theme lives in `~/.icons/` and is not in this repo** -- it is derived, so regenerate it after a re-image. The generator and both config files that point at it *are* tracked. `~/.icons` rather than `~/.local/share/icons` because only the former is in the search path compiled into libXcursor and libwayland-cursor; `$XDG_DATA_HOME/icons` is a newer addition that not every build has.
- **Toolkits cache the cursor theme at process start.** There is no "theme changed" notification a GTK, Qt or Chromium app will act on, so a running app keeps whatever it loaded at launch -- and for Electron, a *window* reload is not enough, since it reuses the same process. If a cursor change looks like it did nothing, check the app's start time before suspecting the theme. `pixelate-cursors.py --verify` reports what libXcursor actually resolves right now, which separates "theme is wrong" from "app is stale".
- Cursor size must stay a whole-number multiple of the grid (16/32/48/64, currently 32). Any other size makes Xcursor rescale a sprite it cannot divide evenly and the blocks come out ragged.
- **A third place this gets set, easy to miss:** `gtk-4.0/settings.ini` and `gtk-3.0/settings.ini` each carry their own `gtk-cursor-theme-name`/`-size`, independent of the niri and `.icons/default/index.theme` settings below. All three used to disagree (a stray `Yaru@24` sat in an untracked `gtk-4.0/settings.ini`), which is exactly the "mix" symptom described above but coming from a GTK-specific override rather than a missing CSS alias.

It is selected in two places, because they cover different clients: `cursor { xcursor-theme }` in `.config/niri/config.kdl` for Wayland, and `.icons/default/index.theme` (`Inherits=`) for XWayland and legacy X11 apps. Change both together, plus `gsettings set org.gnome.desktop.interface cursor-theme`.

## Shell Aliases

Defined in `.aliases`:
- `bfm` / `b` / `m` — ESP-IDF build/flash/monitor shortcuts
- `dcu` / `dcd` / `dcdu` / `dcl` — Docker Compose shortcuts
- `gcap` — git commit -a + delayed push

Modern tool overrides in `.zshrc`:
- `cat` -> `bat --paging=never`
- `ls`/`ll`/`la`/`lt` -> `eza` variants (if installed)
- `cd` -> wraps `zoxide` (`z`) and auto-runs `ls`
