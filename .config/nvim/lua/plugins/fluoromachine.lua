return {
	{
		"maxmx03/fluoromachine.nvim",
		lazy = false,
		priority = 1000,
		config = function()
			local fm = require("fluoromachine")

			fm.setup({
				theme = "fluoromachine",
				brightness = 0.2,
				glow = true,
				transparent = false,

				styles = {
					functions = { italic = true, bold = true },
					keywords = { italic = true },
					constants = { bold = true },
					comments = {},
					-- functions = {},
					variables = {},
					numbers = {},
					-- constants = {},
					parameters = {},
					-- keywords = {},
					types = {},
				},
				colors = {},
				overrides = {
					CursorLine = { bg = "#301934" }, -- deep violet
					CursorColumn = { bg = "#301934" },
					CursorLineNr = { fg = "#ff00cc", bold = true }, -- hot magenta

					Visual = { bg = "#ff0066", fg = "#000000" }, -- laser pink select
					Search = { bg = "#00ffff", fg = "#000000", bold = true }, -- cyan zap
					IncSearch = { bg = "#ffcc00", fg = "#000000", bold = true }, -- gold flash

					LineNr = { fg = "#ff66cc" }, -- soft pink
					SignColumn = { bg = "NONE" }, -- transparent vibes
				},

				plugins = {
					bufferline = true,
					cmp = true,
					dashboard = true,
					editor = true,
					gitsign = true,
					hop = true,
					ibl = true,
					illuminate = true,
					lazy = true,
					minicursor = true,
					ministarter = true,
					minitabline = true,
					ministatusline = true,
					navic = true,
					neogit = true,
					neotree = true,
					noice = true,
					notify = true,
					lspconfig = true,
					syntax = true,
					telescope = true,
					treesitter = true,
					tree = true,
					wk = true,
				},
			})

			vim.cmd.colorscheme("fluoromachine")
		end,
	},
}
