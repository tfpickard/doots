# =====================================================
#   POWERLEVEL10K INSTANT PROMPT
# =====================================================
# Enable Powerlevel10k instant prompt. Should stay close to the top.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

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
[[ -d ~/.p10k ]] || git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.p10k
source ~/.p10k/powerlevel10k.zsh-theme
# Load p10k config file (if it exists)
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

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
znap source marlonrichert/zsh-edit         # Better line editing
znap source zsh-users/zsh-completions      # Additional completion definitions 
# znap source marlonrichert/zsh-autocomplete # Real-time type-ahead completion (loaded first for compatibility)
znap source zsh-users/zsh-autosuggestions  # Fish-like suggestions based on history

# Fuzzy completion plugins
znap source Freed-Wu/fzf-tab-source        # Source for fzf-tab 
znap source Aloxaf/fzf-tab                 # Tab completion with fzf

# =====================================================
#   SYNTAX AND BEHAVIOR PLUGINS
# =====================================================
# Syntax highlighting (must be sourced after completion plugins)
znap source zsh-users/zsh-syntax-highlighting

# History improvements
znap source marlonrichert/zsh-hist         # Better history command with alt-h
znap source zsh-users/zsh-history-substring-search  # Fish-like up/down for history

# Auto-pairing of brackets, quotes, etc.
znap source hlissner/zsh-autopair

# Colors for commands, directories, etc.
znap source marlonrichert/zcolors
znap eval marlonrichert/zcolors "zcolors ${(q)LS_COLORS}"

# Load direnv for automatic environment loading
znap source ptavares/zsh-direnv
eval "$(direnv hook zsh)"

# =====================================================
#   PROJECT MANAGEMENT PLUGINS
# =====================================================
# Auto-switch Python virtualenvs when entering directories
znap source MichaelAquilina/zsh-autoswitch-virtualenv

# tmux configuration and auto-start
ZSH_TMUX_AUTOSTART=${ZSH_TMUX_AUTOSTART:-true}
ZSH_TMUX_AUTOCONNECT=${ZSH_TMUX_AUTOCONNECT:-true}
ts=$(date +"%m-%d-%yT%H:%M:%S")
ZSH_TMUX_DEFAULT_SESSION_NAME=${ZSH_TMUX_DEFAULT_SESSION_NAME:-"tmux-$ts"}
ZSH_TMUX_UNICODE=true
znap source ohmyzsh/ohmyzsh plugins/tmux

# Git-related plugins
znap source ohmyzsh/ohmyzsh plugins/{git,gitfast,git-extras}

# OS-specific plugins
if [[ $(uname) == "Darwin" ]]; then
  znap source ohmyzsh/ohmyzsh plugins/{macos,brew}
else
  # Linux-specific plugins
  znap source ohmyzsh/ohmyzsh plugins/{sudo}
fi

# =====================================================
#   LEARNING AND PRODUCTIVITY PLUGINS
# =====================================================
# Shows when you should use an existing alias
znap source MichaelAquilina/zsh-you-should-use
# Configure YSU behavior
export YSU_MESSAGE_FORMAT="💡 $(tput bold)You should use:%B$(tput sgr0) %alias $(tput dim)instead of %command$(tput sgr0)"
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

# History search with up/down arrows
# bindkey '^[[A' history-substring-search-up
# bindkey '^[[B' history-substring-search-down
bindkey "$terminfo[kcuu1]" history-substring-search-up
bindkey "$terminfo[kcud1]" history-substring-search-down

# =====================================================
#   HISTORY AND SEARCH ENHANCEMENT
# =====================================================
# Install fzf if not already installed
if ! command -v fzf &>/dev/null; then
  echo "Installing fzf for enhanced history search..."
  if [[ $(uname) == "Darwin" ]]; then
    brew install fzf
    $(brew --prefix)/opt/fzf/install --key-bindings --completion --no-update-rc
  else
    git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
    ~/.fzf/install --key-bindings --completion --no-update-rc
  fi
fi

# Load fzf key bindings and completion
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

# Enhanced history search with fzf
# This will allow up-arrow to show a multi-line view of matching history
# Based on what you've already typed
function fzf-history-widget() {
  local selected num
  setopt localoptions noglobsubst noposixbuiltins pipefail no_aliases 2> /dev/null
  selected=( $(fc -rl 1 | 
    awk '{ cmd=$0; sub(/^[ \t]*[0-9]+\**[ \t]+/, "", cmd); if (!seen[cmd]++) print $0 }' |
    FZF_DEFAULT_OPTS="--height ${FZF_TMUX_HEIGHT:-40%} $FZF_DEFAULT_OPTS -n2..,.. --scheme=history --bind=ctrl-r:toggle-sort,ctrl-z:ignore --query=${(qqq)LBUFFER} +m" $(__fzfcmd)) )
  local ret=$?
  if [ -n "$selected" ]; then
    num=$selected[1]
    if [ -n "$num" ]; then
      zle vi-fetch-history -n $num
    fi
  fi
  zle reset-prompt
  set +x
}
zle -N fzf-history-widget
bindkey '^R' fzf-history-widget
bindkey '^[[A' fzf-history-widget  # Up arrow for history search
bindkey '^[OA' fzf-history-widget  # Alternative Up arrow code

# Don't bind standard up/down keys to history-substring-search
# since we're using fzf-history-widget instead
# =====================================================
#   TOOL INTEGRATIONS AND COMPLETIONS
# =====================================================
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
#   ENVIRONMENT TOOLS
# =====================================================
# Python environment setup
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv >/dev/null; then
  eval "$(pyenv init -)"
  export WORKON_HOME="$HOME/.virtualenvs"
  export PIP_VIRTUALENV_BASE="$WORKON_HOME"
  pyenv virtualenvwrapper_lazy
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

# Conda initialization (if installed)
if [ -f "/opt/homebrew/Caskroom/miniconda/base/bin/conda" ]; then
  __conda_setup="$('/opt/homebrew/Caskroom/miniconda/base/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
  if [ $? -eq 0 ]; then
    eval "$__conda_setup"
  else
    if [ -f "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
      . "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    else
      export PATH="/opt/homebrew/Caskroom/miniconda/base/bin:$PATH"
    fi
  fi
  unset __conda_setup
fi

# =====================================================
#   PATH CONFIGURATION
# =====================================================
# Add Homebrew to PATH
export PATH="/opt/homebrew/bin:$PATH"

# Add local bin directories
export PATH="$HOME/.local/bin:$HOME/.local/share/nvim/bin:$PATH"
# =====================================================
#   ALIASES AND FUNCTIONS
# =====================================================
# Load aliases from separate files if they exist
[[ -f ~/.aliases ]] && source ~/.aliases
[[ -f ~/.functions ]] && source ~/.functions
[[ -f ~/.exports ]] && source ~/.exports
[[ -f ~/.path ]] && source ~/.path
[[ -f ~/.extra ]] && source ~/.extra

# Enhanced ls command with lsd if available
if command -v lsd &>/dev/null; then
  alias ls="eza"
  alias ll="eza -l"
  alias la="eza -la"
  alias lt="eza --tree"
fi

# Improved cd with auto-ls
function cd() {
  builtin cd "$@" && ls
}
# Auto-start tmux if not already in tmux
[[ -z $TMUX ]] && exec tmux
#
# # Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# # Initialization code that may require console input (password prompts, [y/n]
# # confirmations, etc.) must go above this block; everything else may go below.
# if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
#   source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
# fi
#
# # command -v python || command -v python3 && ln -s $(dirname python3)/python3 $(dirname python3)/python
# [[ -r ~/Repos/znap/znap.zsh ]] ||
#     git clone --depth 1 -- https://github.com/marlonrichert/zsh-snap.git ~/Repos/znap
# source ~/Repos/znap/znap.zsh
#
# export PATH=/opt/homebrew/bin:$PATH
# # # `znap prompt` makes your prompt visible in just 15-40ms!
# # znap prompt sindresorhus/pure
#
# # # `znap source` starts plugins.
# # znap source marlonrichert/zsh-autocomplete
# set -o magicequalsubst
#
# znap source sorin-ionescu/prezto modules/{environment,history}
#
# znap source ohmyzsh/ohmyzsh lib/{cli,git,theme-and-appearance,directories,functions,grep,history,termsupport}
# znap source ohmyzsh/ohmyzsh \
#     plugins/{git,gitfast,git-extras,macos,brew,nmap,sudo,tmux,vi-mode}
#     # 'lib/(*~(git|theme-and-appearance).zsh)' plugins/{git,brew,macos,nmap,sudo,tmux,vi-mode}
# znap source ptavares/zsh-direnv
# eval "$(direnv hook zsh)"
#
# # The same goes for any other kind of custom prompt:
# # znap eval starship 'starship init zsh --print-full-init'
# # znap prompt
# [[ -d ~/.p10k  ]] || git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.p10k
# source ~/.p10k/powerlevel10k.zsh-theme
# # NOTE that `znap prompt` does not work with Powerlevel10k.
# # With that theme, you should use its "instant prompt" feature instead.
#
#
# ##
# # Load your plugins with `znap source`.
# #
# # znap source marlonrichert/zsh-autocomplete
# znap source marlonrichert/zsh-edit
#
# # `znap install` adds new commands and completions.
# znap install aureliojargas/clitest \
#     zsh-users/zsh-syntax-highlighting \
#     zsh-users/zsh-completions \
#     zsh-users/zsh-history-substring-search \
#     hlissner/zsh-autopair \
#     # MichaelAquilina/zsh-autoswitch-virtualenv 
#     # Freed-Wu/fzf-tab-source \
#     # Aloxaf/fzf-tab \
#
# # `znap eval` makes evaluating generated command output up to 10 times faster.
#
# znap eval iterm2 'curl -fsSL https://iterm2.com/shell_integration/zsh'
#
# # You can also choose to load one or more files specifically:
#
# ZSH_TMUX_AUTOSTART=${ZSH_TMUX_AUTOSTART:-true}
# ZSH_TMUX_AUTOSTART=true
# ZSH_TMUX_AUTOCONNECT=${ZSH_TMUX_AUTOCONNECT:-true}
# ts=$(date +"%m-%d-%yT%H:%M:%S")
# ZSH_TMUX_DEFAULT_SESSION_NAME=${ZSH_TMUX_DEFAULT_SESSION_NAME:-"tmux-$ts"}
# ZSH_TMUX_UNICODE=true
# znap source ohmyzsh/ohmyzsh \
#     plugins/tmux
#
# # znap source ohmyzsh/ohmyzsh \
# #     plugins/{git,brew,macos,nmap,sudo,vi-mode}
#
# # No special syntax is needed to configure plugins. Just use normal Zsh
# # statements:
#
# znap source marlonrichert/zsh-hist
# bindkey '^[q' push-line-or-edit
# bindkey -r '^Q' '^[Q'
#
# #ZSH_AUTOSUGGEST_STRATEGY=(  completion)
# # ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=#ff00ff,bg=cyan,bold,underline"
# znap source zsh-users/zsh-autosuggestions
#
# ZSH_HIGHLIGHT_HIGHLIGHTERS=( main brackets pattern cursor )
# znap source zsh-users/zsh-syntax-highlighting
# znap source zsh-users/zsh-completions
# znap source zsh-users/zsh-history-substring-search
#
# znap source    Freed-Wu/fzf-tab-source
# znap source    Aloxaf/fzf-tab
# znap source    hlissner/zsh-autopair
# znap source    MichaelAquilina/zsh-autoswitch-virtualenv
# # disable sort when completing `git checkout`
# zstyle ':completion:*:git-checkout:*' sort false
# # set descriptions format to enable group support
# # NOTE: don't use escape sequences (like '%F{red}%d%f') here, fzf-tab will ignore them
# zstyle ':completion:*:descriptions' format '[%d]'
# # set list-colors to enable filename colorizing
# zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}
# # force zsh not to show completion menu, which allows fzf-tab to capture the unambiguous prefix
# zstyle ':completion:*' menu no
# # preview directory's content with eza when completing cd
# zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --color=always $realpath'
# # custom fzf flags
# # NOTE: fzf-tab does not follow FZF_DEFAULT_OPTS by default
# zstyle ':fzf-tab:*' fzf-flags --color=fg:1,fg+:2 --bind=tab:accept
# # To make fzf-tab follow FZF_DEFAULT_OPTS.
# # NOTE: This may lead to unexpected behavior since some flags break this plugin. See Aloxaf/fzf-tab#455.
# zstyle ':fzf-tab:*' use-fzf-default-opts yes
# # switch group using `<` and `>`
# zstyle ':fzf-tab:*' switch-group '<' '>'
# # zstyle ':fzf-tab:*' fzf-command ftb-tmux-popup
# zstyle ':fzf-tab:*' popup-min-size 80 12
# autoload -U compinit
# compinit
# zstyle ':completion:*' matcher-list '' 'l:|=* r:|=*'
# # For testing, you might not need any plugins
#
# bindkey '^[[A' history-substring-search-up
# bindkey '^[[B' history-substring-search-down
# bindkey "$terminfo[kcuu1]" history-substring-search-up
# bindkey "$terminfo[kcud1]" history-substring-search-down
# ##
# # Cache the output of slow commands with `znap eval`.
# #
#
# # If the first arg is a repo, then the command will run inside it. Plus,
# # whenever you update a repo with `znap pull`, its eval cache gets regenerated
# # automatically.
# znap eval trapd00r/LS_COLORS "$( whence -a dircolors gdircolors ) -b LS_COLORS"
#
# # The cache gets regenerated, too, when the eval command has changed. For
# # example, here we include a variable. So, the cache gets invalidated whenever
# # this variable has changed.
# znap source marlonrichert/zcolors
# znap eval   marlonrichert/zcolors "zcolors ${(q)LS_COLORS}"
#
# # Combine `znap eval` with `curl` or `wget` to download, cache and source
# # individual files:
# # znap eval omz-git 'curl -fsSL \
# #     https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/git/git.plugin.zsh'
#
#
# ##
# # Defer initilization code with lazily loaded functions created by
# # `znap function`.
# #
#
#
#
#
#
# # export WORKON_HOME="$HOME/.virtualenvs"
#
# # For each of the examples below, the `eval` statement on the right is not
# # executed until you try to execute the associated command or try to use
# # completion on it.
#
#
# znap function _pip_completion pip       'eval "$( pip completion --zsh )"'
# compctl -K    _pip_completion pip
#
# znap function _python_argcomplete pipx  'eval "$( register-python-argcomplete pipx  )"'
# complete -o nospace -o default -o bashdefault \
#            -F _python_argcomplete pipx
#
# znap function _pipenv pipenv            'eval "$( pipenv --completion )"'
# compdef       _pipenv pipenv
#
# # To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
#
# [[ -f ~/.aliases ]] && source ~/.aliases
# [[ -f ~/.functions ]] && source ~/.functions
# [[ -f ~/.exports ]] && source ~/.exports
# [[ -f ~/.path ]] && source ~/.path
# [[ -f ~/.extra ]] && source ~/.extra
#
# export NVM_DIR="$HOME/.config/nvm"
# [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
# [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
# [[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
#
# # pnpm
# export PNPM_HOME="/home/tom/.local/share/pnpm"
# case ":$PATH:" in
#   *":$PNPM_HOME:"*) ;;
#   *) export PATH="$PNPM_HOME:$PATH" ;;
# esac
# # pnpm endw
#
# export PYENV_ROOT="$HOME/.pyenv"
# export PATH="$PYENV_ROOT/bin:$PATH"
# eval "$(pyenv init -)"
# export WORKON_HOME="$HOME/.virtualenvs"
# export PIP_VIRTUALENV_BASE="$WORKON_HOME"
# pyenv virtualenvwrapper
#
# which lsd 2>&1 >/dev/null && alias ls=lsd
#
# # >>> conda initialize >>>
# # !! Contents within this block are managed by 'conda init' !!
# __conda_setup="$('/opt/homebrew/Caskroom/miniconda/base/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
# if [ $? -eq 0 ]; then
#     eval "$__conda_setup"
# else
#     if [ -f "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
#         . "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
#     else
#         export PATH="/opt/homebrew/Caskroom/miniconda/base/bin:$PATH"
#     fi
# fi
# unset __conda_setup
# # <<< conda initialize <<<
#
# [[ -z $TMUX ]] && exec tmux
#
# # Created by `pipx` on 2025-05-05 03:49:37
# export PATH="$PATH:/Users/tom/.local/bin"
