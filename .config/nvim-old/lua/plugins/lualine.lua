return {
	"nvim-lualine/lualine.nvim",
	dependencies = { "nvim-tree/nvim-web-devicons" },
	config = function()
		local lazy_status = require("lazy.status")
		local theme = "fluoromachine"

		require("lualine").setup({
			options = {
				theme = theme,
				globalstatus = true,
				component_separators = { left = "⏽", right = "⏽" },
				section_separators = { left = "", right = "" },
				disabled_filetypes = { "alpha", "dashboard", "NvimTree" },
			},
			sections = {
				lualine_a = {
					{
						function()
							local mode_map = {
								n = "☿ NORMAL",
								i = "☾ INSERT",
								v = "♄ VISUAL",
								V = "♄ V-LINE",
								c = "♃ CMD",
								t = "☉ TERM",
							}
							return mode_map[vim.fn.mode()] or "🜨"
						end,
						color = { fg = "#F8F8F2", gui = "bold" },
					},
				},

				lualine_b = {
					{
						"diagnostics",
						sources = { "nvim_diagnostic" },
						symbols = {
							error = "🜁 ",
							warn = "🜃 ",
							info = "🜄 ",
							hint = "🜂 ",
						},
						diagnostics_color = {
							error = { fg = "#FF6E6E" },
							warn = { fg = "#FF9E64" },
							info = { fg = "#9CDCFE" },
							hint = { fg = "#C3E88D" },
						},
					},
					{
						"diff",
						symbols = {
							added = " ", -- nf-fa-plus_square
							modified = " ", -- nf-fa-edit
							removed = " ", -- nf-fa-minus_square
						},
						diff_color = {
							added = { fg = "#A6E3A1" },
							modified = { fg = "#F9E2AF" },
							removed = { fg = "#F38BA8" },
						},
					},
					{
						"fileformat",
						symbols = {
							unix = "",
							dos = "",
							mac = "",
						},
					},
				},

				lualine_c = {
					{
						"filename",
						path = 3,
						symbols = { modified = " ●", readonly = " 🔒", unnamed = "[No Name]" },
					},
					{
						function()
							return "📁 " .. vim.fn.fnamemodify(vim.fn.getcwd(), ":t")
						end,
						color = { fg = "#89DCEB", gui = "bold" },
					},
				},

				lualine_x = {
					{
						lazy_status.updates,
						cond = lazy_status.has_updates,
						color = { fg = "#FFA066" },
					},
					"searchcount",
					"encoding",
					"branch",
					"filetype",
				},

				lualine_y = {
					{
						function()
							return os.date("⏳ %H:%M")
						end,
						color = { fg = "#CBA6F7" },
					},
					"progress",
				},

				lualine_z = {
					{
						function()
							local mem = math.floor(vim.loop.resident_set_memory() / 1024 / 1024)
							return "🧠 " .. mem .. "MB"
						end,
						color = { fg = "#FAB387" },
					},
					"location",
				},
			},
			tabline = {},
			extensions = {},
		})
	end,
}
--
-- return {
-- 	"nvim-lualine/lualine.nvim",
-- 	config = function()
-- 		local theme = "fluoromachine"
-- 		local lazy_status = require("lazy.status") -- to configure pending updates
-- 		require("lualine").setup({
-- 			options = {
-- 				theme = theme,
-- 				globalstatus = true,
-- 			},
-- 			tabline = {},
-- 			sections = {
-- 				lualine_a = { "mode" },
-- 				lualine_b = {
-- 					{
-- 						"fileformat",
-- 						symbols = {
-- 							unix = "", -- U+f30a from Nerd Fonts: "nf-linux-tux"
-- 							dos = "", -- U+e70f
-- 							mac = "", -- U+e711
-- 						},
-- 					},
-- 				},
-- 				lualine_c = {
-- 					{
-- 						"filename",
-- 						path = 3,
-- 					},
-- 				},
-- 				lualine_x = {
-- 					{
-- 						lazy_status.updates,
-- 						cond = lazy_status.has_updates,
-- 						color = { fg = "#FFA066" }, -- from kanagawa theme
-- 					},
-- 					"searchcount",
-- 					"encoding",
-- 					"branch",
-- 					"filetype",
-- 				},
-- 				lualine_y = { "progress" },
-- 				lualine_z = { "location" },
-- 			},
-- 		})
-- 	end,
-- }
