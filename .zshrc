[[ -d "$HOME/Library/bin" ]] && export PATH="$HOME"/Library/bin:$PATH
export PATH="$HOME"/.local/bin:$PATH
# # =====================================================
# #   POWERLEVEL10K INSTANT PROMPT
# # =====================================================
# # Enable Powerlevel10k instant prompt. Should stay close to the top.
# # Initialization code that may require console input (password prompts, [y/n]
# # confirmations, etc.) must go above this block; everything else may go below.
# if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
#     source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
# fi

[[ -f ~/.local/bin/starship ]] || (\
    curl -sS https://starship.rs/install.sh -o /tmp/s.sh && \
    chmod +x /tmp/s.sh && \
    /tmp/s.sh -b ~/.local/bin \
    )
eval "$(starship init zsh)"
# zmodload zsh/zprof  # Add at the top
# =====================================================
#   CORE ZSH OPTIONS
# =====================================================
# Set history options
HISTFILE=$HOME/.zsh_history
HISTSIZE=10000
SAVEHIST=10000
setopt EXTENDED_HISTORY          # Store command timestamp
setopt HIST_EXPIRE_DUPS_FIRST    # Delete duplicates first when HISTFILE size exceeds HISTSIZE
setopt HIST_IGNORE_DUPS          # Don't record an entry that was just recorded
setopt HIST_IGNORE_SPACE         # Don't record entries starting with a space
setopt HIST_FIND_NO_DUPS         # Do not display duplicates when searching
setopt HIST_VERIFY               # Show command with history expansion before running it
setopt INC_APPEND_HISTORY        # Add commands to HISTFILE in order of execution
setopt SHARE_HISTORY             # Share command history data between sessions

# Set magic equal subst for things like --option=value
setopt magicequalsubst

# =====================================================
#   PLUGIN MANAGEMENT (via znap)
# =====================================================
# Initialize znap (lazy plugin manager for zsh)
[[ -r ~/Repos/znap/znap.zsh ]] || {
    echo "Installing znap plugin manager..."
    mkdir -p ~/Repos
    git clone --depth 1 -- https://github.com/marlonrichert/zsh-snap.git ~/Repos/znap
}
source ~/Repos/znap/znap.zsh

# =====================================================
#   THEME SETUP - POWERLEVEL10K
# =====================================================
# Set up Powerlevel10k theme
# [[ -d ~/.p10k ]] || git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.p10k
# source ~/.p10k/powerlevel10k.zsh-theme
#Load p10k config file (if it exists)
# [[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# =====================================================
#   MY PLUGINS
# =====================================================
# zsh-command-histogram removed 2026-07-28 — superseded by `atuin stats`, which
# reads the same unified history DB (no separate flat file / preexec hook needed).
# See ~/.config/atuin/config.toml [stats] for subcommand grouping.

# =====================================================
#   ESSENTIAL PLUGINS
# =====================================================
# Core prezto modules for basic environment setup
znap source sorin-ionescu/prezto modules/{environment,history}

# Oh My Zsh library modules
znap source ohmyzsh/ohmyzsh lib/{cli,git,theme-and-appearance,directories,functions,grep,history,termsupport}

# =====================================================
#   COMPLETION PLUGINS
# =====================================================
# Enhanced completion with auto-suggestions
znap source zsh-users/zsh-completions      # Additional completion definitions
# znap source marlonrichert/zsh-autocomplete # Real-time type-ahead completion (loaded first for compatibility)
znap source wbingli/zsh-claudecode-completion  # Claude Code CLI completions
znap source marlonrichert/zsh-edit

# Load fzf shell integration before fzf plugins (defines __fzfcmd)
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh
# Fallback if ~/.fzf.zsh isn't present (e.g. fzf installed via brew without running install script)
(( ${+functions[__fzfcmd]} )) || __fzfcmd() {
  [ -n "$TMUX_PANE" ] && { [ "${FZF_TMUX:-0}" != 0 ] || [ -n "$FZF_TMUX_OPTS" ]; } &&
    echo "fzf-tmux ${FZF_TMUX_OPTS:--d${FZF_TMUX_HEIGHT:-40%}} -- " || echo "fzf"
}

# Initialize completion system (must happen before fzf-tab).
# fpath additions must come BEFORE compinit so it processes their #compdef tags.
# ~/.zfunc holds vendored completions (e.g. _eza, so `ls`/`eza` tab-complete since
# ls is aliased to eza). Docker's dir is added only if present (was a hardcoded
# /Users/tom macOS path that doesn't exist on Linux).
fpath=(~/.zfunc $fpath)
[[ -d ~/.docker/completions ]] && fpath=(~/.docker/completions $fpath)
autoload -Uz compinit
compinit

# Completion menu style must be set BEFORE fzf-tab loads (and not re-applied after),
# so fzf-tab can take over the menu. If set AFTER fzf-tab, Tab falls back to zsh's
# default menu: first Tab prints a newline, second Tab shows the list.
zstyle ':completion:*' menu select

# Fuzzy completion plugins: after compinit, before widget-wrapping plugins
znap source Freed-Wu/fzf-tab-source        # Source for fzf-tab
znap source Aloxaf/fzf-tab                 # Tab completion with fzf

znap source zsh-users/zsh-autosuggestions  # Fish-like suggestions (must come after fzf-tab)

# =====================================================
#   SYNTAX AND BEHAVIOR PLUGINS
# =====================================================

# History improvements
znap source marlonrichert/zsh-hist         # Better history command with alt-h

# Auto-pairing of brackets, quotes, etc.
znap source hlissner/zsh-autopair

# Colors for commands, directories, etc.
znap source marlonrichert/zcolors
znap eval marlonrichert/zcolors "zcolors ${(q)LS_COLORS}"

# Load direnv for automatic environment loading
znap source ptavares/zsh-direnv

# =====================================================
#   PROJECT MANAGEMENT PLUGINS
# =====================================================
# Auto-switch Python virtualenvs when entering directories
znap source MichaelAquilina/zsh-autoswitch-virtualenv

# =====================================================
#   TMUX: one session PER PROJECT, independent views
# =====================================================
# The old config named every session tmux-<timestamp>, so AUTOCONNECT could never
# match an existing one and each shell spawned a brand-new session (=> 7+ orphan
# sessions of sprawl). Instead: one session per PROJECT (git root, else $PWD).
# Every terminal opened in the same project rejoins that session; each terminal/tab
# gets its own self-destroying *grouped* view, so panes don't mirror or fight over
# size, and the view disappears when the tab closes (no session sprawl) while your
# windows and running work persist in the project session.
#
# Keep the oh-my-zsh tmux plugin for its aliases, but disable its own autostart;
# we roll our own below.
#
# Autostart policy:
#   - An explicit ZSH_TMUX_AUTOSTART in the environment ALWAYS wins (true or false).
#   - Otherwise default OFF inside VS Code's integrated terminal (TERM_PROGRAM=vscode):
#     tmux's alternate screen breaks VS Code shell integration and the Copilot agent's
#     command-output capture. Use the "zsh (tmux)" terminal profile to opt back in.
#   - Otherwise default ON (Ghostty and every other terminal) — the usual workflow.
if [[ -n "${ZSH_TMUX_AUTOSTART+set}" ]]; then
  _TMUX_AUTOSTART_WANT="$ZSH_TMUX_AUTOSTART"
elif [[ "$TERM_PROGRAM" == vscode ]]; then
  _TMUX_AUTOSTART_WANT=false
else
  _TMUX_AUTOSTART_WANT=true
fi
ZSH_TMUX_AUTOSTART=false
ZSH_TMUX_UNICODE=true
znap source ohmyzsh/ohmyzsh plugins/tmux

_tmux_project_autostart() {
  # Interactive TTYs only; bail if already in tmux or tmux is unavailable.
  [[ -o interactive && -t 1 ]] || return
  [[ -n "$TMUX" ]] && return
  [[ "$TERM" == dumb ]] && return
  command -v tmux >/dev/null || return
  [[ "$_TMUX_AUTOSTART_WANT" == true ]] || return

  # Project name: git superproject (so submodules map to the parent) -> toplevel
  # -> current dir. A manual ZSH_TMUX_DEFAULT_SESSION_NAME always wins.
  local root name view
  if [[ -n "$ZSH_TMUX_DEFAULT_SESSION_NAME" ]]; then
    name="$ZSH_TMUX_DEFAULT_SESSION_NAME"
  else
    root="$(command git rev-parse --show-superproject-working-tree 2>/dev/null)"
    [[ -z "$root" ]] && root="$(command git rev-parse --show-toplevel 2>/dev/null)"
    [[ -z "$root" ]] && root="$PWD"
    name="${root:t}"
  fi
  name="${name//[^A-Za-z0-9_-]/-}"   # tmux dislikes '.'/':'/spaces in names
  [[ -z "$name" ]] && name="main"

  # Persistent per-project session that owns the windows/work.
  command tmux has-session -t "=$name" 2>/dev/null || command tmux new-session -d -s "$name"

  # Attach through a private grouped session (independent current-window pointer =>
  # no mirroring/resize lock) that self-destroys on detach (=> no sprawl). Created
  # and attached in one call so it never gets reaped before we attach.
  view="${name}-$$"
  exec command tmux new-session -t "$name" -s "$view" \; set-option -t "$view" destroy-unattached on
}
_tmux_project_autostart

# Git-related plugins
znap source ohmyzsh/ohmyzsh plugins/{git,gitfast,git-extras}

# OS-specific plugins
if [[ $(uname) == "Darwin" ]]; then
    znap source ohmyzsh/ohmyzsh plugins/{macos,brew}
else
    # Linux-specific plugins
    znap source ohmyzsh/ohmyzsh plugins/sudo
fi

# =====================================================
#   LEARNING AND PRODUCTIVITY PLUGINS
# =====================================================
# Shows when you should use an existing alias
znap source MichaelAquilina/zsh-you-should-use
# Configure YSU behavior
# export YSU_MESSAGE_FORMAT="💡 $(tput bold)You should use:%B$(tput sgr0) %alias $(tput dim)instead of %command$(tput sgr0)"
export YSU_MODE=ALL  # Show suggestions for global and git aliases

# Shows ZSH tips and tricks in your terminal
znap source molovo/tipz
# Configure tipz
export TIPZ_TEXT="💡 ZSH Tip: "


# =====================================================
#   KEYBINDINGS AND SHORTCUTS
# =====================================================
# Enable vi mode
znap source ohmyzsh/ohmyzsh plugins/vi-mode

# Push line for editing
bindkey '^[q' push-line-or-edit
bindkey -r '^Q' '^[Q'


# =====================================================
#   FZF (required by fzf-tab completion, above)
# =====================================================
# Install fzf if not already installed. History search is handled by atuin
# (see the end of this file); fzf remains for fzf-tab Tab-completion.
if ! command -v fzf &>/dev/null; then
    echo "Installing fzf for fzf-tab completion..."
    if [[ $(uname) == "Darwin" ]]; then
        brew install fzf
        $(brew --prefix)/opt/fzf/install --key-bindings --completion --no-update-rc
    else
        git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
        ~/.fzf/install --key-bindings --completion --no-update-rc
    fi
fi


# =====================================================
#   TOOL INTEGRATIONS AND COMPLETIONS
# =====================================================
[[ -d ~/.config/zsh/completions ]] || mkdir -p ~/.config/zsh/completions
# (N) = nullglob: expand to nothing (not a "no matches found" error) when the
# completions dir is empty.
for x in ~/.config/zsh/completions/*(N); do
    [[ "$x" =~ ".zwc" ]] && continue
    if [[ -f $x ]]; then
        source $x
    fi
done

# Pip completion
znap function _pip_completion pip 'eval "$( pip completion --zsh )"'
compctl -K _pip_completion pip

# Pipx completion
znap function _python_argcomplete pipx 'eval "$( register-python-argcomplete pipx )"'
complete -o nospace -o default -o bashdefault -F _python_argcomplete pipx

# Pipenv completion
znap function _pipenv pipenv 'eval "$( pipenv --completion )"'
compdef _pipenv pipenv

# iTerm2 integration
znap eval iterm2 'curl -fsSL https://iterm2.com/shell_integration/zsh'

# =====================================================
#   PERFORMANCE OPTIMIZATIONS
# =====================================================
znap source romkatv/zsh-defer
znap source mroth/evalcache

# Cache slow evaluations
# pyenv must be on PATH *before* its init is evaluated, so set PYENV_ROOT/PATH
# here. Guarded so an absent pyenv stays silent (no more evalcache error).
export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PYENV_ROOT/bin:$PATH"
command -v pyenv >/dev/null && _evalcache pyenv init -
_evalcache direnv hook zsh

# znap source olets/zsh-abbr

# =====================================================
#   ADVANCED NAVIGATION AND COMPLETION
# =====================================================
znap source psprint/zsh-navigation-tools

# =====================================================
#   DEVELOPMENT WORKFLOW
# =====================================================
znap source MichaelAquilina/zsh-auto-notify
export AUTO_NOTIFY_THRESHOLD=15  # Notify for long compilations


# =====================================================
#   ENVIRONMENT TOOLS
# =====================================================
# Python environment setup (PYENV_ROOT/PATH already exported above, before the
# pyenv init call). virtualenvwrapper_lazy needs the pyenv-virtualenvwrapper plugin.
if command -v pyenv >/dev/null; then
    export WORKON_HOME="$HOME/.virtualenvs"
    export PIP_VIRTUALENV_BASE="$WORKON_HOME"
    # Only init virtualenvwrapper when its scripts are actually on PATH. Otherwise
    # `pyenv virtualenvwrapper_lazy` spams errors every startup AND attempts a
    # PEP 668-blocked pip install. To enable: `pipx install virtualenvwrapper`.
    if command -v virtualenvwrapper_lazy.sh >/dev/null 2>&1 || command -v virtualenvwrapper.sh >/dev/null 2>&1; then
        pyenv virtualenvwrapper_lazy
    fi
fi

# Node.js environment setup
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # Load nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # Load completion

# pnpm
export PNPM_HOME="$HOME/.local/share/pnpm"
if [ -d "$PNPM_HOME" ]; then
    case ":$PATH:" in
        *":$PNPM_HOME:"*) ;;
        *) export PATH="$PNPM_HOME:$PATH" ;;
    esac
fi

# Go environment setup
export GOPATH="$HOME/go"
export PATH="$GOPATH/bin:$PATH"
#
# # Conda initialization (if installed)
# if [ -f "/opt/homebrew/Caskroom/miniconda/base/bin/conda" ]; then
#     __conda_setup="$('/opt/homebrew/Caskroom/miniconda/base/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
#     if [ $? -eq 0 ]; then
#         eval "$__conda_setup"
#     else
#         if [ -f "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
#             . "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
#         else
#             export PATH="/opt/homebrew/Caskroom/miniconda/base/bin:$PATH"
#         fi
#     fi
#     unset __conda_setup
# fi
#
# =====================================================
#   PATH CONFIGURATION
# =====================================================
# Add Homebrew to PATH
[[ -d /opt/homebrew/bin ]] && \
    export PATH="/opt/homebrew/bin:/opt/homebrew/opt/gnu-getopt/bin:$PATH"

# Add local bin directories
export PATH="$HOME/.local/share/nvim/bin:$PATH"

export LLM_USER_PATH=$HOME/.config/llm
# =====================================================
#   ALIASES AND FUNCTIONS
# =====================================================
# Load aliases from separate files if they exist
[[ -f ~/.aliases ]] && source ~/.aliases
[[ -f ~/.functions ]] && source ~/.functions
[[ -f ~/.exports ]] && source ~/.exports
[[ -f ~/.path ]] && source ~/.path
[[ -f ~/.extra ]] && source ~/.extra

# Modern CLI tool aliases (add to your .aliases file)
alias neofetch='fastfetch'  # neofetch is archived upstream; fastfetch replaces it
# alias find='fd'
# alias grep='rg'
# On Debian/Ubuntu the fd binary is installed as `fdfind` (name clash with another
# package). This shim makes the standard `fd` name work WITHOUT hijacking `find`.
command -v fdfind >/dev/null && ! command -v fd >/dev/null && alias fd='fdfind'

# Enhanced ls command with eza if available
if command -v eza &>/dev/null; then
    export EZA_ICONS_AUTO=true
    alias ls="eza"
    alias ll="eza -la"
    alias lh="eza -lah"
    alias la="eza -las newest"
    alias lls="eza -lahs size"
    alias lt="eza --tree"
fi

# cd with auto-ls. Prefer zoxide's `z` jump, but check for the FUNCTION precisely
# (`command -v z` can match a stale hashed `z` and then fail at runtime with
# "command not found: z"). zoxide is initialized near the bottom of this file, so
# during early startup `z` may not exist yet — fall back to the builtin then.
function cd() {
    if (( $+functions[z] )); then
        z "$@" && ls
    else
        builtin cd "$@" && ls
    fi
}
# zprof  # Add at the bottom (comment out after testing)


if [[ -d ~/.p ]]; then
    pushd $HOME/.p >/dev/null 
    for f in *; do 
        [[ -x $f ]] && source $f
    done
    popd
fi

# tmux autostart is handled earlier by _tmux_project_autostart (per-project
# sessions, and it intentionally skips VS Code). This old unconditional
# `exec tmux` was redundant AND re-enabled tmux inside VS Code, defeating that
# logic, so it's disabled.
# [[ -z $TMUX && -t 1 ]] && exec tmux

znap source zsh-users/zsh-syntax-highlighting

# OpenClaw Completion (guarded: path differs per machine and may be absent;
# the old line hardcoded a /Users/tom macOS path and errored on Linux)
[[ -f ~/.openclaw/completions/openclaw.zsh ]] && source ~/.openclaw/completions/openclaw.zsh

# Register the vendored ~/.zfunc/_eza completion. ~/.zfunc is already on fpath
# before the FIRST compinit above, so DON'T run compinit again here: a second
# compinit after fzf-tab + the widget-wrapping plugins breaks fzf-tab (Tab prints
# a newline and needs a second press). znap also wraps `compdef` to DEFER it
# (queues into _znap_compdef) and never flushes this late, so register directly.
autoload -Uz _eza 2>/dev/null && _comps[eza]=_eza

export PATH="$PATH:$HOME/.local/bin"

znap eval zoxide 'zoxide init zsh'

# =====================================================
#   ATUIN - shell history (Ctrl-R)
# =====================================================
# Atuin replaces the old hand-rolled fzf history widget AND
# zsh-history-substring-search: it records every command into a local SQLite DB
# (~/.local/share/atuin/history.db) with cwd/exit/duration/timestamp, and owns
# Ctrl-R (search everything). Up-arrow is deliberately taken back from atuin
# further down (see "HISTORY CYCLING"). Local-only: no cloud sync (auto_sync=false).
# Handy: `atuin stats`, `atuin search --cwd .`, `atuin wrapped`.
# Kept as a plain eval (not znap-cached) so a future `atuin` upgrade can't serve a
# stale init. Must stay at/near the end so atuin's keybindings win.
command -v atuin >/dev/null && eval "$(atuin init zsh)"
# Atuin 18.x also binds '?' at an EMPTY prompt to an experimental AI assistant
# (atuin ai), which needs a backend we don't have and is surprising magic. Undo
# it so '?' is always a literal '?' in insert mode. (vi command-mode '?' stays as
# the normal history-search.)
if command -v atuin >/dev/null; then
    bindkey -M viins '?' self-insert
    bindkey -M main  '?' self-insert
fi

# Shift-Up = atuin's TUI pinned to the CURRENT DIRECTORY via --filter-mode, still
# prefilled with whatever you've typed. Plain Up no longer opens any TUI (see
# below), so this is the quick way into a cwd-scoped search.
# Defined after the atuin init since it reuses _atuin_search.
if command -v atuin >/dev/null; then
    _atuin_up_search_dir() {
        if [[ ! $BUFFER == *$'\n'* ]]; then
            _atuin_search --filter-mode directory "$@"
        else
            zle up-line
        fi
    }
    _atuin_up_search_dir_vicmd() { _atuin_up_search_dir --keymap-mode=vim-normal }
    _atuin_up_search_dir_viins() { _atuin_up_search_dir --keymap-mode=vim-insert }
    zle -N atuin-up-search-dir-vicmd _atuin_up_search_dir_vicmd
    zle -N atuin-up-search-dir-viins _atuin_up_search_dir_viins
    # Shift-Up escape sequence (CSI 1;2A) across keymaps.
    bindkey -M viins '^[[1;2A' atuin-up-search-dir-viins
    bindkey -M vicmd '^[[1;2A' atuin-up-search-dir-vicmd
    bindkey -M emacs '^[[1;2A' atuin-up-search-dir-viins
fi

# =====================================================
#   HISTORY CYCLING (Up/Down) + Tab hand-off to atuin
# =====================================================
# Traditional behavior: Up/Down walk one command at a time through history, no
# full-screen tool, no subprocess. If the line is non-empty, only entries that
# start with what you already typed are matched (type "git " then Up to walk your
# git commands). Must come after `atuin init`, which binds Up itself.
#
# Tab *while cycling* escalates to the fuzzy tool: it drops the history entry you
# landed on, restores the prefix you originally typed, and opens atuin's TUI
# prefilled with it. Tab at any other time is normal (fzf-tab) completion.
#
# NOTE: this deliberately does NOT use zsh's up-line-or-beginning-search. That
# function decides "am I continuing a search run?" with [[ $LASTWIDGET == $WIDGET ]],
# and $WIDGET is wrong inside a wrapper widget (zsh-autosuggestions rebinds us and
# calls through an autosuggest-orig-* name). The check then fails on every press,
# the cursor is never rewound to the typed prefix, and the 2nd Up searches for the
# whole recalled command -- giving a history depth of exactly 1. We track run state
# ourselves off (BUFFER, CURSOR), which no wrapper can perturb.

# The prefix the user actually typed before the run started, plus the exact
# (BUFFER, CURSOR) we left behind, used to detect "still cycling".
typeset -g  __hist_cycle_prefix=''
typeset -gi __hist_cycle_cursor=0
typeset -g  __hist_cycle_buffer=$'\0'
typeset -gi __hist_cycle_endcur=-1
# Whatever ^I was bound to before we wrap it (fzf-tab-complete, normally).
typeset -g  __hist_cycle_tab_orig="${${$(builtin bindkey -M viins '^I')##* }:-expand-or-complete}"

# Are we mid-run? Keyed off the exact (BUFFER, CURSOR) we left behind, so nothing
# a wrapper widget does to $WIDGET can confuse us. vi command mode clamps CURSOR to
# len-1 after we return, hence the off-by-one tolerance; $LASTWIDGET is accepted as
# a second opinion for the same reason.
_hist_cycle_active() {
    [[ $BUFFER == "$__hist_cycle_buffer" ]] || return 1
    [[ $LASTWIDGET == hist-cycle-(up|down) ]] && return 0
    (( CURSOR == __hist_cycle_endcur || CURSOR == __hist_cycle_endcur - 1 ))
}
_hist_cycle_end() { __hist_cycle_buffer=$'\0'; __hist_cycle_endcur=-1 }

_hist_cycle_move() {
    local dir=$1
    if _hist_cycle_active; then
        # Continuing: rewind to the typed prefix so the search keeps matching it.
        CURSOR=$__hist_cycle_cursor
    else
        if [[ $BUFFER == *$'\n'* ]]; then
            [[ $dir == up ]] && zle .up-line-or-history || zle .down-line-or-history
            _hist_cycle_end
            return
        fi
        __hist_cycle_prefix=$LBUFFER
        __hist_cycle_cursor=$CURSOR
        # Rewind to the newest entry. zle keeps the history position for the whole
        # line-editing session, so without this an abandoned run (e.g. Up Up then
        # ^U) leaves the next Up searching from wherever the last one stopped
        # instead of from your most recent command. Assigning HISTNO rewrites the
        # buffer, so put the typed line back afterwards.
        local buf=$BUFFER cur=$CURSOR
        HISTNO=$HISTCMD
        BUFFER=$buf
        CURSOR=$cur
    fi

    if [[ $dir == up ]]; then
        zle .history-beginning-search-backward
    elif ! zle .history-beginning-search-forward; then
        # Walked past the newest match: give the user their own line back.
        BUFFER=$__hist_cycle_prefix
        CURSOR=${#BUFFER}
        _hist_cycle_end
        return
    fi
    CURSOR=${#BUFFER}
    __hist_cycle_buffer=$BUFFER
    __hist_cycle_endcur=$CURSOR
}
_hist_cycle_up()   { _hist_cycle_move up }
_hist_cycle_down() { _hist_cycle_move down }
zle -N hist-cycle-up _hist_cycle_up
zle -N hist-cycle-down _hist_cycle_down

_hist_cycle_tab() {
    if _hist_cycle_active && (( ${+widgets[atuin-search-viins]} )); then
        BUFFER=$__hist_cycle_prefix
        CURSOR=${#BUFFER}
        _hist_cycle_end
        if [[ $KEYMAP == vicmd ]]; then
            zle atuin-search-vicmd
        else
            zle atuin-search-viins
        fi
        return
    fi
    zle "$__hist_cycle_tab_orig" -- "$@"
}
zle -N hist-cycle-tab _hist_cycle_tab

# Both the normal and application-mode Up/Down sequences, in every keymap.
for _hc_keymap in emacs viins vicmd main; do
    bindkey -M $_hc_keymap '^[[A' hist-cycle-up
    bindkey -M $_hc_keymap '^[OA' hist-cycle-up
    bindkey -M $_hc_keymap '^[[B' hist-cycle-down
    bindkey -M $_hc_keymap '^[OB' hist-cycle-down
    bindkey -M $_hc_keymap '^I'   hist-cycle-tab
done
unset _hc_keymap
# vi command mode: k/j cycle too (atuin binds k to its TUI).
bindkey -M vicmd 'k' hist-cycle-up
bindkey -M vicmd 'j' hist-cycle-down

# Start every prompt with a clean run, so a hand-typed line that happens to equal
# the last recalled one isn't mistaken for a continuation.
autoload -Uz add-zsh-hook && add-zsh-hook precmd _hist_cycle_end

# Tell zsh-autosuggestions these are history-navigation widgets. Without this it
# classifies them as buffer-modifying, fetches a suggestion after every press, and
# the async autosuggest-suggest widget fires in the middle of a cycling run.
ZSH_AUTOSUGGEST_CLEAR_WIDGETS+=(hist-cycle-up hist-cycle-down)
