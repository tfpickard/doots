# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a personal dotfiles repository for macOS (with some Linux/Hyprland configs). The repo is managed with git and deployed by symlinking or copying files to their target locations in `$HOME`.

## Repository Structure

| Path | Purpose |
|------|---------|
| `.zshrc` | Zsh shell configuration |
| `.aliases` | Shell aliases (sourced by `.zshrc`) |
| `.tmux.conf` | Tmux configuration |
| `.config/ghostty/` | Ghostty terminal emulator config |
| `.config/hypr/` | Hyprland window manager (Linux) |
| `.config/nvim/` | Neovim configuration |
| `.config/eww/` | Eww widget system |
| `.config/waybar/` | Waybar status bar (Linux) |

## Key Architectural Patterns

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

### Hyprland config uses switchable presets
`.config/hypr/conf/` contains named preset files for animations, decorations, layouts, monitors, and window borders. The active preset for each category is referenced from the parent `.conf` file (e.g., `animation.conf` sources one of `conf/animations/*.conf`).

### Waybar layout is deliberately compact
The bar is sized to survive its worst case: a long window title used to push the right-hand island clean off the screen. Guards against that:

- `custom/niriwindow` caps the title at 34 characters, in `scripts/niri-window.py` (`MAX_LEN`, which ellipsises) *and* as a `max-length` backstop in the config and in `scripts/compositor-config.py`'s Hyprland variant. Change all three together.
- Base font is 11px, module padding is `0 5px`, and bar `spacing` is 2.

### Waybar modules keep a fixed width
The bar used to shift horizontally whenever a reading gained or lost a digit. Two conventions prevent that, and new modules are expected to follow both:

1. **Fixed character counts.** Numeric fields are padded in `themes/dope/config` (`{usage:>3}`, `{temperatureC:>2}`), and modules with alternate formats of differing length set `min-length`. JetBrains Mono gives every digit and the space the same advance width, so equal character counts are equal pixel widths.
2. **`min-width` floors in `style.css`.** Nerd Font *icons* are not uniform width (9-16px in the set used here), so a module that swaps its icon still resizes even with the character count pinned. The floors at the bottom of `style.css` are measured from each module's widest variant -- measure rather than guess when adding one.

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
