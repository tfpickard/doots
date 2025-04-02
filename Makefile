SHELL 		= /bin/bash
TIMESTAMP = $(shell date --iso-8601=seconds)
NVIM_DIRS = $(shell find ~/.config ~/.local ~/.cache -name nvim -type d)
ASTRO_REPO = https://github.com/AstroNvim/AstroNvim 
astronvim:
	# @mv ~/.config/nvim ~/.config/nvim-$(TIMESTAMP)
	# @mv ~/.local/share/nvim ~/.local/share/nvim-$(TIMESTAMP)
	@for dir in $(NVIM_DIRS); do \
		bdir=$$dir-backup-$(TIMESTAMP); \
	  mv $$dir $$bdir; \
	done
	git clone --depth 1 $(ASTRO_REPO) ~/.config/nvim; \
	grep 'github.com' ~/.ssh/known_hosts || \
	  	(ssh-keyscan github.com | tee -a ~/.ssh/known_hosts); \
	git clone git@github.com:nailshard/astrouser.git ~/.config/nvim/lua/user \
	  || git clone https://github.com/nailshard/astrouser.git \
	    ~/.config/nvim/lua/user; \
	# @echo "$(TIMESTAMP): Done!" | tee -a make.log
links:
	@for f in $(shell find ./ -name ".*" -type f); do \
		[[ -e $$HOME/$$f ]] && echo mv $$HOME/{$$f,$$f-backup-$(TIMESTAMP)}; \
		echo ln -sf $$PWD/$$f $$HOME/$$f; \
		echo ls -la $$HOME/$$f; \
	done
	ln -sf $$PWD/.config/nvim $$HOME/.config/nvim
	ln -s $$PWD/.zshrc $$HOME/.zshrc
PYTHON_VERSION ?= 3.12.2
VENV_NAME ?= myenv
PROJECT_DIR ?= $(CURDIR)/$(VENV_NAME)

pyenv-setup:
	@echo "🔧 Setting up Python $(PYTHON_VERSION) via pyenv"
	pyenv install -s $(PYTHON_VERSION)
	pyenv virtualenv $(PYTHON_VERSION) $(VENV_NAME)
	@echo "📁 Creating project directory: $(PROJECT_DIR)"
	mkdir -p $(PROJECT_DIR)
	@echo "⚙️  Initializing virtualenv in project dir"
	echo "pyenv activate $(VENV_NAME)" > $(PROJECT_DIR)/.venv-activate
	@echo "✅ Done! To activate, run: 'pyenv activate $(VENV_NAME)'"

pyenv-wrapper-setup:
	@echo "🔌 Configuring pyenv-virtualenvwrapper plugin"
	@echo 'export PYENV_VIRTUALENVWRAPPER_PREFER_PYVENV="true"' >> ~/.bashrc
	@echo 'eval "$$(pyenv init -)"' >> ~/.bashrc
	@echo 'eval "$$(pyenv virtualenv-init -)"' >> ~/.bashrc
	@echo 'export WORKON_HOME="$$HOME/.virtualenvs"' >> ~/.bashrc
	@echo 'source "$$(pyenv root)/plugins/pyenv-virtualenvwrapper/etc/bashrc"' >> ~/.bashrc
	@echo "💡 Restart your shell or run 'source ~/.bashrc'"
all: nvim links
