# doots - dotfiles installer for macOS and Linux (Ubuntu + niri).
#
# Every managed path is a symlink from $HOME/<path> to <repo>/<path>, so the
# lists below are just repo-relative paths. Linking is conservative:
#   - an existing file/dir is MOVED to ~/.dotfiles-backup/<timestamp>/ first;
#   - an existing symlink pointing anywhere else is LEFT ALONE and reported
#     (a symlink is a deliberate choice, e.g. ~/.config/nvim -> a separate clone).
# `make status` shows what `make link` would do without touching anything.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:
.DEFAULT_GOAL := help

OS       := $(shell uname -s)
DOTFILES := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKUP   := $(HOME)/.dotfiles-backup/$(shell date +%Y%m%d-%H%M%S)
THEME    ?= cyberdream

# --- What gets linked --------------------------------------------------------
COMMON_LINKS := .zshrc .zshenv .zprofile .profile .aliases .functions .zfunc \
                .tmux.conf \
                .config/ghostty .config/themes .config/starship.toml .config/nvim

# niri desktop. hypr/dunst are dormant (see AGENTS.md) and deliberately absent.
LINUX_LINKS  := .config/niri .config/waybar .config/mako .config/fnott \
                .config/swaync .config/fuzzel .config/gtklock .config/swaylock \
                .config/swaylock-effects .config/satty .config/scripts \
                .config/gtk-3.0 .config/gtk-4.0 .icons/default

ifeq ($(OS),Darwin)
LINKS := $(COMMON_LINKS)
GHOSTTY_OS := macos.conf
else
LINKS := $(COMMON_LINKS) $(LINUX_LINKS)
GHOSTTY_OS := linux.conf
endif

# --- Packages ----------------------------------------------------------------
# Only what these configs actually use.
BREW_FORMULAE := git zsh tmux neovim fzf fd ripgrep bat eza zoxide atuin direnv \
                 starship jq gh lazygit pyenv pipx
BREW_CASKS    := ghostty font-monaspace font-jetbrains-mono-nerd-font

# Ubuntu 24.04 names. Not in apt (install separately): atuin (`cargo install
# --locked atuin`), niri, ghostty, and a neovim new enough for LazyVim (>= 0.11).
APT_PACKAGES  := zsh tmux git fzf fd-find ripgrep bat eza zoxide direnv jq gh \
                 brightnessctl playerctl wl-clipboard

# --- Link helper (exported so every recipe can `eval` it) ---------------------
define LINK_SH
link_one() {
    local rel=$$1 src="$(DOTFILES)/$$1" dst="$$HOME/$$1" cur
    if [ ! -e "$$src" ]; then echo "  missing   $$rel (not in repo)"; return; fi
    if [ -L "$$dst" ]; then
        cur=$$(readlink "$$dst")
        if [ "$$cur" = "$$src" ]; then echo "  ok        $$rel"
        else echo "  SKIPPED   $$rel (already a symlink to $$cur)"; fi
        return
    fi
    if [ -e "$$dst" ]; then
        echo "  backup    $$rel -> $(BACKUP)/$$rel"
        if [ -z "$${DRY:-}" ]; then
            mkdir -p "$$(dirname "$(BACKUP)/$$rel")"
            mv "$$dst" "$(BACKUP)/$$rel"
        fi
    fi
    echo "  link      $$rel"
    if [ -z "$${DRY:-}" ]; then
        mkdir -p "$$(dirname "$$dst")"
        ln -s "$$src" "$$dst"
    fi
}
endef
export LINK_SH

.PHONY: help install deps deps-mac deps-linux link status unlink nvim theme \
        tmux systemd sddm

help:
	@echo "doots ($(OS))"
	echo
	echo "  make install    deps + nvim + link + theme + tmux$(if $(filter Linux,$(OS)), + systemd)"
	echo "  make deps       install packages (brew on macOS, apt on Linux)"
	echo "  make link       symlink dotfiles into \$$HOME (backs up real files)"
	echo "  make status     show what 'make link' would do; changes nothing"
	echo "  make unlink     remove symlinks that point into this repo"
	echo "  make nvim       fetch the nvim config submodule"
	echo "  make theme      select a theme if none is active (THEME=$(THEME))"
	echo "  make tmux       install TPM and tmux plugins"
	echo "  make systemd    link systemd user units (Linux; does not enable them)"
	echo "  make sddm       install the SGI SDDM greeter theme (Linux; uses sudo)"

install: deps nvim link theme tmux $(if $(filter Linux,$(OS)),systemd)
	@echo "Done. Open a new shell (exec zsh)."

# --- Packages ----------------------------------------------------------------
deps: $(if $(filter Darwin,$(OS)),deps-mac,deps-linux)

deps-mac:
	@if ! command -v brew >/dev/null; then
	    if [ ! -x /opt/homebrew/bin/brew ] && [ ! -x /usr/local/bin/brew ]; then
	        /bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
	    fi
	    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
	        [ -x "$$b" ] && { eval "$$("$$b" shellenv)"; break; }
	    done
	fi
	brew install $(BREW_FORMULAE)
	for cask in $(BREW_CASKS); do
	    # An app installed by hand (not via brew) makes `brew install --cask` fail.
	    if [ "$$cask" = ghostty ] && [ -d /Applications/Ghostty.app ]; then continue; fi
	    brew list --cask "$$cask" >/dev/null 2>&1 || brew install --cask "$$cask"
	done

deps-linux:
	@command -v apt-get >/dev/null || { echo "deps-linux only knows apt"; exit 1; }
	sudo apt-get install -y $(APT_PACKAGES)
	for tool in atuin niri ghostty; do
	    command -v "$$tool" >/dev/null || echo "note: $$tool is not from apt; install it separately"
	done

# --- Linking -----------------------------------------------------------------
link:
	@eval "$$LINK_SH"
	echo "Linking into $$HOME:"
	for p in $(LINKS); do link_one "$$p"; done
	ln -sfn $(GHOSTTY_OS) "$(DOTFILES)/.config/ghostty/os/active"
	echo "  ghostty   os/active -> $(GHOSTTY_OS)"
	[ -d "$(BACKUP)" ] && echo "Backups are in $(BACKUP)" || true

status:
	@eval "$$LINK_SH"
	echo "Would link into $$HOME (dry run):"
	for p in $(LINKS); do DRY=1 link_one "$$p"; done
	echo "  ghostty   os/active -> $$(readlink "$(DOTFILES)/.config/ghostty/os/active" 2>/dev/null || echo unset) (want $(GHOSTTY_OS))"
	echo "  theme     $$(readlink "$(DOTFILES)/.config/themes/active" 2>/dev/null || echo none selected)"
	[ -e "$(DOTFILES)/.config/nvim/init.lua" ] && echo "  nvim      submodule present" || echo "  nvim      submodule not fetched (make nvim)"
	[ -d "$$HOME/.tmux/plugins/tpm" ] && echo "  tmux      TPM installed" || echo "  tmux      TPM missing (make tmux)"

unlink:
	@for p in $(LINKS); do
	    dst="$$HOME/$$p"
	    if [ -L "$$dst" ] && [ "$$(readlink "$$dst")" = "$(DOTFILES)/$$p" ]; then
	        rm "$$dst" && echo "  removed   $$p"
	    fi
	done
	echo "Backups (if any) are under $$HOME/.dotfiles-backup/"

# --- Components --------------------------------------------------------------
nvim:
	@dir="$(DOTFILES)/.config/nvim"
	if [ -e "$$dir/init.lua" ]; then
	    echo "nvim config present"
	elif [ -z "$$(ls -A "$$dir" 2>/dev/null)" ]; then
	    git -C "$(DOTFILES)" submodule update --init .config/nvim
	else
	    echo "$$dir has files but no init.lua; not touching it"; exit 1
	fi

theme:
	@if [ -L "$(DOTFILES)/.config/themes/active" ]; then
	    echo "theme already selected: $$(readlink "$(DOTFILES)/.config/themes/active") (switch with theme-set)"
	else
	    "$(DOTFILES)/.config/themes/theme-set" $(THEME)
	fi

tmux:
	@tpm="$$HOME/.tmux/plugins/tpm"
	[ -d "$$tpm" ] || git clone --depth 1 https://github.com/tmux-plugins/tpm "$$tpm"
	"$$tpm/bin/install_plugins"

systemd:
	@# Linked FILE BY FILE on purpose. ~/.config/systemd/user also holds
	@# enablement state (the .wants/ directories written by
	@# `systemctl --user enable`), so replacing the whole directory with a
	@# symlink into the repo would silently disable every enabled unit.
	[ "$(OS)" = Linux ] || { echo "systemd is Linux-only"; exit 1; }
	mkdir -p "$$HOME/.config/systemd/user"
	for unit in "$(DOTFILES)"/.config/systemd/user/*; do
	    [ -e "$$unit" ] || continue
	    ln -sfn "$$unit" "$$HOME/.config/systemd/user/$$(basename "$$unit")"
	    echo "  linked    $$(basename "$$unit")"
	done
	systemctl --user daemon-reload
	echo "Enable with: systemctl --user enable --now <unit>"

sddm:
	@# SDDM only looks in /usr/share/sddm/themes, and it runs as the `sddm`
	@# user, so the theme has to be reachable from outside $$HOME.
	@#
	@# The theme is upstream Sugar Candy QML plus a patch series. Patching
	@# through a symlink would rewrite the tracked files and leave the repo
	@# permanently dirty, so the theme is COPIED and then patched in place.
	@# The cost is that edits under .config/sddm are not live: re-run
	@# `make sddm` to see them. Keeping the QML pristine with the changes in
	@# patches/ preserves the upstream-refresh path: drop a newer Sugar Candy
	@# in, re-run this, and the patches either apply or say which hunk moved.
	@#
	@# SDDM reads *every* file in /etc/sddm.conf.d, whatever its extension,
	@# in sorted order, and the last Current= wins. A backup left next to the
	@# real config therefore shadows it -- theme.conf.user.bak-simple-sddm
	@# sorts after theme.conf.user and silently held the greeter on the stock
	@# theme. Backups go in /etc/sddm.conf.d.backups, outside the read path,
	@# and any other file setting Current= is moved there too.
	[ "$(OS)" = Linux ] || { echo "sddm is Linux-only"; exit 1; }
	src="$(DOTFILES)/.config/sddm/sgi-sddm"
	dst=/usr/share/sddm/themes/sgi-sddm
	[ -d "$$src" ] || { echo "SDDM theme not found"; exit 1; }
	sudo rm -rf "$$dst"
	sudo cp -rL "$$src" "$$dst"
	sudo rm -rf "$$dst/patches"
	echo "Copied $$dst"
	for p in "$$src"/patches/*.patch; do
	    [ -f "$$p" ] || continue
	    if sudo patch -d "$$dst" -p1 --batch --forward <"$$p" >/dev/null; then
	        echo "  applied   $$(basename "$$p")"
	    else
	        echo "$$(basename "$$p") did not apply; see *.rej under $$dst"; exit 1
	    fi
	done
	sudo -u sddm test -r "$$dst/Main.qml" || echo "warning: the sddm user cannot read the installed theme"
	sudo mkdir -p /etc/sddm.conf.d
	printf '[Theme]\nCurrent=sgi-sddm\n' | sudo tee /etc/sddm.conf.d/theme.conf.user >/dev/null
	echo "SDDM theme set to sgi-sddm"
	for f in /etc/sddm.conf.d/*; do
	    [ -f "$$f" ] || continue
	    [ "$$f" = /etc/sddm.conf.d/theme.conf.user ] && continue
	    grep -q '^[[:space:]]*Current=' "$$f" || continue
	    sudo mkdir -p /etc/sddm.conf.d.backups
	    sudo mv "$$f" /etc/sddm.conf.d.backups/
	    echo "moved $$f aside: it also sets Current= and would shadow ours"
	done
	# The greeter renders with the sddm user's fonts, not yours.
	if [ -d "$$HOME/.local/share/fonts/JetBrainsMonoNF" ]; then
	    sudo mkdir -p /usr/local/share/fonts/JetBrainsMonoNF
	    sudo cp -n "$$HOME"/.local/share/fonts/JetBrainsMonoNF/*.ttf /usr/local/share/fonts/JetBrainsMonoNF/ 2>/dev/null || true
	    sudo fc-cache -f >/dev/null 2>&1 || true
	    echo "JetBrainsMono installed system-wide for the greeter"
	fi
