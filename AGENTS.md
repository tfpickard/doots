# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

## Shell Aliases

Defined in `.aliases`:
- `bfm` / `b` / `m` — ESP-IDF build/flash/monitor shortcuts
- `dcu` / `dcd` / `dcdu` / `dcl` — Docker Compose shortcuts
- `gcap` — git commit -a + delayed push

Modern tool overrides in `.zshrc`:
- `cat` -> `bat --paging=never`
- `ls`/`ll`/`la`/`lt` -> `eza` variants (if installed)
- `cd` -> wraps `zoxide` (`z`) and auto-runs `ls`
