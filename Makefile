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
	# ln -s $$PWD/.zshrc $$HOME/.zshrc
all: nvim links
