# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# command -v python || command -v python3 && ln -s $(dirname python3)/python3 $(dirname python3)/python
[[ -r ~/Repos/znap/znap.zsh ]] ||
    git clone --depth 1 -- https://github.com/marlonrichert/zsh-snap.git ~/Repos/znap
source ~/Repos/znap/znap.zsh

export PATH=/opt/homebrew/bin:$PATH
# # `znap prompt` makes your prompt visible in just 15-40ms!
# znap prompt sindresorhus/pure

# # `znap source` starts plugins.
# znap source marlonrichert/zsh-autocomplete
set -o magicequalsubst

znap source sorin-ionescu/prezto modules/{environment,history}

znap source ohmyzsh/ohmyzsh lib/{cli,git,theme-and-appearance,directories,functions,grep,history,termsupport}
znap source ohmyzsh/ohmyzsh \
    plugins/{git,gitfast,git-extras,macos,brew,nmap,sudo,tmux,vi-mode}
    # 'lib/(*~(git|theme-and-appearance).zsh)' plugins/{git,brew,macos,nmap,sudo,tmux,vi-mode}
znap source ptavares/zsh-direnv
eval "$(direnv hook zsh)"

# The same goes for any other kind of custom prompt:
# znap eval starship 'starship init zsh --print-full-init'
# znap prompt
[[ -d ~/.p10k  ]] || git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.p10k
source ~/.p10k/powerlevel10k.zsh-theme
# NOTE that `znap prompt` does not work with Powerlevel10k.
# With that theme, you should use its "instant prompt" feature instead.


##
# Load your plugins with `znap source`.
#
# znap source marlonrichert/zsh-autocomplete
znap source marlonrichert/zsh-edit

# `znap install` adds new commands and completions.
znap install aureliojargas/clitest \
    zsh-users/zsh-syntax-highlighting \
    zsh-users/zsh-completions \
    zsh-users/zsh-history-substring-search \
    hlissner/zsh-autopair \
    MichaelAquilina/zsh-autoswitch-virtualenv 
    # Freed-Wu/fzf-tab-source \
    # Aloxaf/fzf-tab \
    
# `znap eval` makes evaluating generated command output up to 10 times faster.

znap eval iterm2 'curl -fsSL https://iterm2.com/shell_integration/zsh'

# You can also choose to load one or more files specifically:
    
ZSH_TMUX_AUTOSTART=${ZSH_TMUX_AUTOSTART:-true}
ZSH_TMUX_AUTOSTART=${ZSH_TMUX_AUTOCONNECT:-true}
ts=$(date +"%m-%d-%yT%H:%M:%S")
ZSH_TMUX_DEFAULT_SESSION_NAME=${ZSH_TMUX_DEFAULT_SESSION_NAME:-"tmux-$ts"}
ZSH_TMUX_UNICODE=true
znap source ohmyzsh/ohmyzsh \
    plugins/tmux

# znap source ohmyzsh/ohmyzsh \
#     plugins/{git,brew,macos,nmap,sudo,vi-mode}

# No special syntax is needed to configure plugins. Just use normal Zsh
# statements:

znap source marlonrichert/zsh-hist
bindkey '^[q' push-line-or-edit
bindkey -r '^Q' '^[Q'

#ZSH_AUTOSUGGEST_STRATEGY=(  completion)
# ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=#ff00ff,bg=cyan,bold,underline"
znap source zsh-users/zsh-autosuggestions

ZSH_HIGHLIGHT_HIGHLIGHTERS=( main brackets pattern cursor )
znap source zsh-users/zsh-syntax-highlighting
znap source zsh-users/zsh-completions
znap source zsh-users/zsh-history-substring-search

znap source    Freed-Wu/fzf-tab-source
znap source    Aloxaf/fzf-tab
znap source    hlissner/zsh-autopair
znap source    MichaelAquilina/zsh-autoswitch-virtualenv
# disable sort when completing `git checkout`
zstyle ':completion:*:git-checkout:*' sort false
# set descriptions format to enable group support
# NOTE: don't use escape sequences (like '%F{red}%d%f') here, fzf-tab will ignore them
zstyle ':completion:*:descriptions' format '[%d]'
# set list-colors to enable filename colorizing
zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}
# force zsh not to show completion menu, which allows fzf-tab to capture the unambiguous prefix
zstyle ':completion:*' menu no
# preview directory's content with eza when completing cd
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --color=always $realpath'
# custom fzf flags
# NOTE: fzf-tab does not follow FZF_DEFAULT_OPTS by default
zstyle ':fzf-tab:*' fzf-flags --color=fg:1,fg+:2 --bind=tab:accept
# To make fzf-tab follow FZF_DEFAULT_OPTS.
# NOTE: This may lead to unexpected behavior since some flags break this plugin. See Aloxaf/fzf-tab#455.
zstyle ':fzf-tab:*' use-fzf-default-opts yes
# switch group using `<` and `>`
zstyle ':fzf-tab:*' switch-group '<' '>'
zstyle ':fzf-tab:*' fzf-command ftb-tmux-popup
zstyle ':fzf-tab:*' popup-min-size 50 8
autoload -U compinit
compinit
zstyle ':completion:*' matcher-list '' 'l:|=* r:|=*'
# For testing, you might not need any plugins

bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
bindkey "$terminfo[kcuu1]" history-substring-search-up
bindkey "$terminfo[kcud1]" history-substring-search-down
##
# Cache the output of slow commands with `znap eval`.
#

# If the first arg is a repo, then the command will run inside it. Plus,
# whenever you update a repo with `znap pull`, its eval cache gets regenerated
# automatically.
znap eval trapd00r/LS_COLORS "$( whence -a dircolors gdircolors ) -b LS_COLORS"

# The cache gets regenerated, too, when the eval command has changed. For
# example, here we include a variable. So, the cache gets invalidated whenever
# this variable has changed.
znap source marlonrichert/zcolors
znap eval   marlonrichert/zcolors "zcolors ${(q)LS_COLORS}"

# Combine `znap eval` with `curl` or `wget` to download, cache and source
# individual files:
# znap eval omz-git 'curl -fsSL \
#     https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/git/git.plugin.zsh'


##
# Defer initilization code with lazily loaded functions created by
# `znap function`.
#

# For each of the examples below, the `eval` statement on the right is not
# executed until you try to execute the associated command or try to use
# completion on it.

znap function _pyenv pyenv              'eval "$( pyenv init - --no-rehash )"'
compctl -K    _pyenv pyenv

znap function _pip_completion pip       'eval "$( pip completion --zsh )"'
compctl -K    _pip_completion pip

znap function _python_argcomplete pipx  'eval "$( register-python-argcomplete pipx  )"'
complete -o nospace -o default -o bashdefault \
           -F _python_argcomplete pipx

znap function _pipenv pipenv            'eval "$( pipenv --completion )"'
compdef       _pipenv pipenv

# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

[[ -f ~/.aliases ]] && source ~/.aliases
[[ -f ~/.functions ]] && source ~/.functions
[[ -f ~/.exports ]] && source ~/.exports
[[ -f ~/.path ]] && source ~/.path
[[ -f ~/.extra ]] && source ~/.extra

export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
