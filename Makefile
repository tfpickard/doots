SHELL := /bin/bash
.PHONY: all install deps deps-mac deps-linux backup symlinks nvim hypr ghostty shell tmux git clean help

# Detect OS
UNAME_S := $(shell uname -s)
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)

# Directories
DOTFILES_DIR := $(shell pwd)
CONFIG_DIR := $(HOME)/.config
BACKUP_DIR := $(HOME)/.dotfiles_backup_$(TIMESTAMP)

# Package lists
MAC_PACKAGES := 1password-cli alacritty awscli bat docker docker-buildx \
				docker-compose direnv dropbear ef fzf figlet fg fzy firefox git git-lfs gh \
				ghostty gzip haha lolcat lazygit lua-lang uage-server neofetch neovim nmap \
				nvm pam-reattach pipx pyenv pyenv-virtualenv pyenv-virtualenvwrapper \
				ripgrep rustup tmux virtualenv virtualenvwrapper watch wget yq yarn

LINUX_PACKAGES := neovim tmux zsh git fzf eza bat fd ripgrep lazygit \
                  direnv python-pyenv nodejs npm ghostty-git \
                  hyprland waybar dunst rofi alacritty firefox yq

# Files to symlink to home directory
HOME_FILES := .zshrc .tmux.conf .aliases .functions .gitignore .p10k.zsh \
              .zshenv .zprofile .profile

# Directories to symlink to .config
CONFIG_DIRS := nvim hypr ghostty waybar dunst rofi alacritty
please alphabetize this list
all: deps backup symlinks nvim
	@echo "🎉 Dotfiles installation complete!"
	@echo "💡 You may need to:"
	@echo "   - Restart your shell: exec zsh"
	@echo "   - Install Neovim plugins: nvim +Lazy"
	@echo "   - Configure Hyprland for your displays"

help:
	@echo "Available targets:"
	@echo "  all        - Install everything (deps, backup, symlinks, nvim)"
	@echo "  install    - Alias for 'all'"
	@echo "  deps       - Install system dependencies"
	@echo "  deps-mac   - Install macOS dependencies via brew"
	@echo "  deps-linux - Install Linux dependencies via paru"
	@echo "  backup     - Backup existing dotfiles"
	@echo "  symlinks   - Create all symlinks"
	@echo "  nvim       - Setup Neovim configuration"
	@echo "  hypr       - Setup Hyprland configuration"
	@echo "  ghostty    - Setup Ghostty terminal"
	@echo "  shell      - Setup shell configuration"
	@echo "  tmux       - Setup tmux configuration"
	@echo "  git        - Setup git configuration"
	@echo "  clean      - Remove symlinks and restore backups"

install: all

deps:
ifeq ($(UNAME_S),Darwin)
	@$(MAKE) deps-mac
else ifeq ($(UNAME_S),Linux)
	@$(MAKE) deps-linux
else
	@echo "❌ Unsupported operating system: $(UNAME_S)"
	@exit 1
endif

deps-mac:
	@echo "🍺 Installing macOS dependencies..."
	@command -v brew >/dev/null 2>&1 || { \
		echo "Installing Homebrew..."; \
		/bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
	}
	@brew update
	@for pkg in $(MAC_PACKAGES); do \
		if ! brew list $$pkg >/dev/null 2>&1; then \
			echo "Installing $$pkg..."; \
			brew install $$pkg; \
		else \
			echo "✅ $$pkg already installed"; \
		fi; \
	done
	@echo "🍺 macOS dependencies installed!"

deps-linux:
	@echo "🐧 Installing Linux dependencies..."
	@command -v paru >/dev/null 2>&1 || { \
		echo "Installing paru AUR helper..."; \
		sudo pacman -S --needed base-devel git; \
		git clone https://aur.archlinux.org/paru.git /tmp/paru; \
		cd /tmp/paru && makepkg -si; \
	}
	@paru -Syu --noconfirm
	@for pkg in $(LINUX_PACKAGES); do \
		if ! paru -Qi $$pkg >/dev/null 2>&1; then \
			echo "Installing $$pkg..."; \
			paru -S --noconfirm $$pkg; \
		else \
			echo "✅ $$pkg already installed"; \
		fi; \
	done
	@echo "🐧 Linux dependencies installed!"

backup:
	@echo "📦 Creating backup of existing dotfiles..."
	@mkdir -p $(BACKUP_DIR)
	@for file in $(HOME_FILES); do \
		if [ -f $(HOME)/$$file ] || [ -L $(HOME)/$$file ]; then \
			echo "Backing up $$file"; \
			cp -P $(HOME)/$$file $(BACKUP_DIR)/; \
		fi; \
	done
	@for dir in $(CONFIG_DIRS); do \
		if [ -d $(CONFIG_DIR)/$$dir ] || [ -L $(CONFIG_DIR)/$$dir ]; then \
			echo "Backing up .config/$$dir"; \
			cp -rP $(CONFIG_DIR)/$$dir $(BACKUP_DIR)/; \
		fi; \
	done
	@echo "📦 Backup created at $(BACKUP_DIR)"

symlinks: backup
	@echo "🔗 Creating symlinks..."
	@mkdir -p $(CONFIG_DIR)
	
	# Symlink home directory files
	@for file in $(HOME_FILES); do \
		if [ -f $(DOTFILES_DIR)/$$file ]; then \
			echo "Linking $$file"; \
			rm -f $(HOME)/$$file; \
			ln -sf $(DOTFILES_DIR)/$$file $(HOME)/$$file; \
		fi; \
	done
	
	# Symlink .config directories
	@for dir in $(CONFIG_DIRS); do \
		if [ -d $(DOTFILES_DIR)/.config/$$dir ]; then \
			echo "Linking .config/$$dir"; \
			rm -rf $(CONFIG_DIR)/$$dir; \
			ln -sf $(DOTFILES_DIR)/.config/$$dir $(CONFIG_DIR)/$$dir; \
		fi; \
	done
	
	# Handle special nvim case (both old and new configs exist)
	@if [ -d $(DOTFILES_DIR)/.config/nvim-old ]; then \
		echo "Linking .config/nvim-old"; \
		rm -rf $(CONFIG_DIR)/nvim-old; \
		ln -sf $(DOTFILES_DIR)/.config/nvim-old $(CONFIG_DIR)/nvim-old; \
	fi
	
	# Handle lua config in root
	@if [ -d $(DOTFILES_DIR)/lua ]; then \
		echo "Linking nvim lua config"; \
		rm -rf $(CONFIG_DIR)/nvim; \
		ln -sf $(DOTFILES_DIR) $(CONFIG_DIR)/nvim; \
	fi
	
	@echo "🔗 Symlinks created!"

nvim:
	@echo "⚡ Setting up Neovim..."
	@mkdir -p $(CONFIG_DIR)/nvim
	
	# Check if we have a LazyVim setup (lua/ dir in root)
	@if [ -d $(DOTFILES_DIR)/lua ]; then \
		echo "Found LazyVim configuration"; \
		rm -rf $(CONFIG_DIR)/nvim; \
		ln -sf $(DOTFILES_DIR) $(CONFIG_DIR)/nvim; \
	elif [ -d $(DOTFILES_DIR)/.config/nvim-old ]; then \
		echo "Found legacy Neovim configuration"; \
		rm -rf $(CONFIG_DIR)/nvim; \
		ln -sf $(DOTFILES_DIR)/.config/nvim-old $(CONFIG_DIR)/nvim; \
	fi
	
	# Install vim-plug if using legacy config
	@if [ -f $(CONFIG_DIR)/nvim/lua/core/lazy.lua ]; then \
		echo "LazyVim will auto-install on first run"; \
	fi
	
	@echo "⚡ Neovim configuration linked!"
	@echo "💡 Run 'nvim' and install plugins with :Lazy"

hypr:
	@echo "🖥️  Setting up Hyprland..."
	@if [ -d $(DOTFILES_DIR)/.config/hypr ]; then \
		rm -rf $(CONFIG_DIR)/hypr; \
		ln -sf $(DOTFILES_DIR)/.config/hypr $(CONFIG_DIR)/hypr; \
		echo "🖥️  Hyprland configuration linked!"; \
	else \
		echo "❌ Hyprland config not found"; \
	fi

ghostty:
	@echo "👻 Setting up Ghostty terminal..."
	@if [ -d $(DOTFILES_DIR)/.config/ghostty ]; then \
		rm -rf $(CONFIG_DIR)/ghostty; \
		ln -sf $(DOTFILES_DIR)/.config/ghostty $(CONFIG_DIR)/ghostty; \
		echo "👻 Ghostty configuration linked!"; \
	else \
		echo "❌ Ghostty config not found"; \
	fi

shell:
	@echo "🐚 Setting up shell configuration..."
	@rm -f $(HOME)/.zshrc $(HOME)/.aliases $(HOME)/.functions
	@ln -sf $(DOTFILES_DIR)/.zshrc $(HOME)/.zshrc
	@ln -sf $(DOTFILES_DIR)/.aliases $(HOME)/.aliases
	@ln -sf $(DOTFILES_DIR)/.functions $(HOME)/.functions
	@ln -sf $(DOTFILES_DIR)/.p10k.zsh $(HOME)/.p10k.zsh
	
	# Install znap plugin manager if not present
	@if [ ! -d $(HOME)/Repos/znap ]; then \
		echo "Installing znap plugin manager..."; \
		mkdir -p $(HOME)/Repos; \
		git clone --depth 1 https://github.com/marlonrichert/zsh-snap.git $(HOME)/Repos/znap; \
	fi
	
	@echo "🐚 Shell configuration linked!"
	@echo "💡 Restart your shell: exec zsh"

tmux:
	@echo "🖥️  Setting up tmux..."
	@rm -f $(HOME)/.tmux.conf
	@ln -sf $(DOTFILES_DIR)/.tmux.conf $(HOME)/.tmux.conf
	
	# Install TPM (Tmux Plugin Manager)
	@if [ ! -d $(HOME)/.tmux/plugins/tpm ]; then \
		echo "Installing TPM (Tmux Plugin Manager)..."; \
		git clone https://github.com/tmux-plugins/tpm $(HOME)/.tmux/plugins/tpm; \
	fi
	
	@echo "🖥️  tmux configuration linked!"
	@echo "💡 Install plugins: prefix + I (default: Ctrl-a + I)"

git:
	@echo "📝 Setting up Git configuration..."
	@if [ -f $(DOTFILES_DIR)/.gitconfig ]; then \
		rm -f $(HOME)/.gitconfig; \
		ln -sf $(DOTFILES_DIR)/.gitconfig $(HOME)/.gitconfig; \
	fi
	@if [ -f $(DOTFILES_DIR)/.gitignore ]; then \
		rm -f $(HOME)/.gitignore; \
		ln -sf $(DOTFILES_DIR)/.gitignore $(HOME)/.gitignore; \
	fi
	@echo "📝 Git configuration linked!"

clean:
	@echo "🧹 Cleaning up symlinks..."
	@for file in $(HOME_FILES); do \
		if [ -L $(HOME)/$$file ]; then \
			echo "Removing $(HOME)/$$file"; \
			rm -f $(HOME)/$$file; \
		fi; \
	done
	@for dir in $(CONFIG_DIRS); do \
		if [ -L $(CONFIG_DIR)/$$dir ]; then \
			echo "Removing $(CONFIG_DIR)/$$dir"; \
			rm -f $(CONFIG_DIR)/$$dir; \
		fi; \
	done
	
	# Restore from most recent backup if it exists
	@LATEST_BACKUP=$$(ls -td $(HOME)/.dotfiles_backup_* 2>/dev/null | head -1); \
	if [ -n "$$LATEST_BACKUP" ]; then \
		echo "Restoring from $$LATEST_BACKUP"; \
		cp -r $$LATEST_BACKUP/* $(HOME)/; \
		cp -r $$LATEST_BACKUP/.config/* $(CONFIG_DIR)/ 2>/dev/null || true; \
	fi
	
	@echo "🧹 Cleanup complete!"

# Development targets
dev-nvim:
	@echo "🔧 Setting up development Neovim config..."
	@nvim --headless "+Lazy! sync" +qa
	@echo "✅ Neovim plugins synchronized"

dev-test:
	@echo "🧪 Testing configuration..."
	@zsh -c 'echo "Testing zsh config..." && exit'
	@nvim --version
	@tmux -V
	@echo "✅ Basic configuration test passed"

# Help with dependencies
show-deps:
	@echo "📋 System Dependencies:"
	@echo "macOS (brew): $(MAC_PACKAGES)"
	@echo "Linux (paru): $(LINUX_PACKAGES)"

show-paths:
	@echo "📁 Configuration Paths:"
	@echo "Dotfiles: $(DOTFILES_DIR)"
	@echo "Config:   $(CONFIG_DIR)"
	@echo "Backup:   $(BACKUP_DIR)"
	@echo "Files:    $(HOME_FILES)"
	@echo "Dirs:     $(CONFIG_DIRS)"
#
#
# SHELL 		= /bin/bash
# TIMESTAMP = $(shell date --iso-8601=seconds)
# NVIM_DIRS = $(shell find ~/.config ~/.local ~/.cache -name nvim -type d)
# ASTRO_REPO = https://github.com/AstroNvim/AstroNvim 
# astronvim:
# 	# @mv ~/.config/nvim ~/.config/nvim-$(TIMESTAMP)
# 	# @mv ~/.local/share/nvim ~/.local/share/nvim-$(TIMESTAMP)
# 	@for dir in $(NVIM_DIRS); do \
# 		bdir=$$dir-backup-$(TIMESTAMP); \
# 	  mv $$dir $$bdir; \
# 	done
# 	git clone --depth 1 $(ASTRO_REPO) ~/.config/nvim; \
# 	grep 'github.com' ~/.ssh/known_hosts || \
# 	  	(ssh-keyscan github.com | tee -a ~/.ssh/known_hosts); \
# 	git clone git@github.com:nailshard/astrouser.git ~/.config/nvim/lua/user \
# 	  || git clone https://github.com/nailshard/astrouser.git \
# 	    ~/.config/nvim/lua/user; \
# 	# @echo "$(TIMESTAMP): Done!" | tee -a make.log
# links:
# 	@for f in $(shell find ./ -name ".*" -type f); do \
# 		[[ -e $$HOME/$$f ]] && echo mv $$HOME/{$$f,$$f-backup-$(TIMESTAMP)}; \
# 		echo ln -sf $$PWD/$$f $$HOME/$$f; \
# 		echo ls -la $$HOME/$$f; \
# 	done
# 	ln -sf $$PWD/.config/nvim $$HOME/.config/nvim
# 	ln -s $$PWD/.zshrc $$HOME/.zshrc
# PYTHON_VERSION ?= 3.12.2
# VENV_NAME ?= myenv
# PROJECT_DIR ?= $(CURDIR)/$(VENV_NAME)
#
# pyenv-setup:
# 	@echo "🔧 Setting up Python $(PYTHON_VERSION) via pyenv"
# 	pyenv install -s $(PYTHON_VERSION)
# 	pyenv virtualenv $(PYTHON_VERSION) $(VENV_NAME)
# 	@echo "📁 Creating project directory: $(PROJECT_DIR)"
# 	mkdir -p $(PROJECT_DIR)
# 	@echo "⚙️  Initializing virtualenv in project dir"
# 	echo "pyenv activate $(VENV_NAME)" > $(PROJECT_DIR)/.venv-activate
# 	@echo "✅ Done! To activate, run: 'pyenv activate $(VENV_NAME)'"
#
# pyenv-wrapper-setup:
# 	@echo "🔌 Configuring pyenv-virtualenvwrapper plugin"
# 	@echo 'export PYENV_VIRTUALENVWRAPPER_PREFER_PYVENV="true"' >> ~/.bashrc
# 	@echo 'eval "$$(pyenv init -)"' >> ~/.bashrc
# 	@echo 'eval "$$(pyenv virtualenv-init -)"' >> ~/.bashrc
# 	@echo 'export WORKON_HOME="$$HOME/.virtualenvs"' >> ~/.bashrc
# 	@echo 'source "$$(pyenv root)/plugins/pyenv-virtualenvwrapper/etc/bashrc"' >> ~/.bashrc
# 	@echo "💡 Restart your shell or run 'source ~/.bashrc'"
# all: nvim links
