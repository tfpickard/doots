-- Function to toggle diagnostics visibility
local diagnostics_visible = true
function ToggleDiagnostics()
	diagnostics_visible = not diagnostics_visible
	if diagnostics_visible then
		vim.diagnostic.show()
	else
		vim.diagnostic.hide()
	end
end

-- Function to display LSP status in the status line
function LspStatus()
	local clients = vim.lsp.get_active_clients()
	if next(clients) == nil then
		return "No LSP"
	end
	local buf_ft = vim.api.nvim_buf_get_option(0, "filetype")
	for _, client in ipairs(clients) do
		local filetypes = client.config.filetypes
		if filetypes and vim.fn.index(filetypes, buf_ft) ~= -1 then
			return client.name
		end
	end
	return "No LSP"
end

vim.api.nvim_create_autocmd("LspAttach", {
	group = vim.api.nvim_create_augroup("UserLspConfig", {}),
	callback = function()
		local wk = require("which-key")

		wk.add({
			{ "<leader>l", group = "+LSP" },
			{ "<leader>ld", vim.lsp.buf.definition, desc = "Definition" },
			{ "<leader>lD", vim.lsp.buf.declaration, desc = "Declaration" },
			{ "<leader>lR", vim.lsp.buf.references, desc = "References" },
			{ "<leader>li", vim.lsp.buf.implementation, desc = "Implementations" },
			{ "<leader>lt", vim.lsp.buf.type_definition, desc = "Type Definition" },
			{ "<leader>ls", vim.lsp.buf.signature_help, desc = "Signature Help" },
			{ "<leader>lh", vim.lsp.buf.hover, desc = "Hover Documentation" },
			{ "<leader>la", vim.lsp.buf.code_action, desc = "Code Action" },
			{ "<leader>lf", vim.lsp.buf.format, desc = "Format" },
			{ "<leader>lj", vim.diagnostic.goto_next, desc = "Next Diagnostic" },
			{ "<leader>lk", vim.diagnostic.goto_prev, desc = "Prev Diagnostic" },
			{ "<leader>lF", vim.diagnostic.open_float, desc = "Float Diagnostic" },
			{ "<leader>lr", vim.lsp.buf.rename, desc = "Rename" },
			{ "<leader>lt", ToggleDiagnostics, desc = "Toggle Diagnostics" },
		})
	end,
})

return {
	{
		"williamboman/mason.nvim",
		opts = {
			ui = {
				icons = {
					package_installed = "✓",
					package_pending = "➜",
					package_uninstalled = "✗",
				},
			},
		},
	},
	{
		"williamboman/mason-lspconfig.nvim",
		opts = {
			-- Language servers to install
			ensure_installed = {
				"bashls", -- Bash/Zsh/Shell
				"clangd", -- C/C++
				"cmake",
				"neocmake", -- CMake
				"cssls", -- CSS
				"dockerls",
				"docker_compose_language_service", -- Docker & Docker Compose
				"html", -- HTML
				"lemminx", -- INI
				"ts_ls", -- JavaScript/TypeScript
				"jsonls", -- JSON
				"texlab", -- LaTeX
				"lua_ls", -- Lua
				"marksman", -- Markdown
				"pyright", -- Python
				"rust_analyzer", -- Rust
				"taplo", -- TOML
				"yamlls", -- YAML
			},
			automatic_installation = true,
		},
	},
	{
		"WhoIsSethDaniel/mason-tool-installer.nvim",
		opts = {
			-- Formatters and linters to install
			ensure_installed = {
				-- formatters
				"shfmt", -- Bash/Zsh/Shell
				"clang-format", -- C/C++
				-- "cmake-format",           -- CMake
				"prettier", -- CSS
				-- "dockfmt",                -- Docker & Docker Compose
				"prettier", -- HTML
				-- "ini-fmt",                -- INI
				"prettier",
				"biome", -- JavaScript/TypeScript
				"prettier",
				"jq", -- JSON
				"latexindent", -- LaTeX
				"stylua", -- Lua
				-- "indent",                 -- Make
				"prettier",
				"mdformat", -- Markdown
				"black",
				"isort",
				"ruff", -- Python
				"rustfmt", -- Rust
				"taplo", -- TOML
				"prettier",
				"yamlfix", -- YAML

				-- linters
				"shellcheck", -- Bash/Zsh/Shell
				-- "clang-tidy",
				-- "cppcheck", -- C/C++
				"cmakelint", -- CMake
				"stylelint", -- CSS
				"hadolint", -- Docker & Docker Compose
				"htmlhint", -- HTML
				-- "ini-lint", -- INI
				"eslint",
				"biome", -- JavaScript/TypeScript
				"jsonlint", -- JSON
				-- "chktex", -- LaTeX
				"luacheck", -- Lua
				"checkmake", -- Make
				"markdownlint", -- Markdown
				"ruff",
				"pylint",
				"flake8",
				"mypy", -- Python
				-- "clippy", -- Rust
				"taplo", -- TOML
				"yamllint", -- YAML
			},
		},
	},
	{
		"neovim/nvim-lspconfig",
		config = function()
			local lspconfig = require("lspconfig")

			-- Configure diagnostic symbols for the sign column (gutter)
			local signs = { Error = " ", Warn = " ", Hint = "󰠠 ", Info = " " }
			for type, icon in pairs(signs) do
				local hl = "DiagnosticSign" .. type
				vim.fn.sign_define(hl, { text = icon, texthl = hl, numhl = "" })
			end

			-- ### SET KEYMAPS TO ATTACH TO LSPs ###

			-- Use LspAttach autocommand to map the following keys after
			-- the language server attaches to the current buffer
			vim.api.nvim_create_autocmd("LspAttach", {
				group = vim.api.nvim_create_augroup("UserLspConfig", {}),
				callback = function()
					local wk = require("which-key")

					wk.add({
						{ "<leader>l", group = "+LSP" },
						{ "<leader>ld", vim.lsp.buf.definition, desc = "Definition" },
						{ "<leader>lD", vim.lsp.buf.declaration, desc = "Declaration" },
						{ "<leader>lR", vim.lsp.buf.references, desc = "References" },
						{ "<leader>li", vim.lsp.buf.implementation, desc = "Implementations" },
						{ "<leader>lt", vim.lsp.buf.type_definition, desc = "Type Definition" },
						{ "<leader>ls", vim.lsp.buf.signature_help, desc = "Signature Help" },
						{ "<leader>lh", vim.lsp.buf.hover, desc = "Hover Documentation" },
						{ "<leader>la", vim.lsp.buf.code_action, desc = "Code Action" },
						{ "<leader>lf", vim.lsp.buf.format, desc = "Format" },
						{ "<leader>lj", vim.diagnostic.goto_next, desc = "Next Diagnostic" },
						{ "<leader>lk", vim.diagnostic.goto_prev, desc = "Prev Diagnostic" },
						{ "<leader>lF", vim.diagnostic.open_float, desc = "Float Diagnostic" },
						{ "<leader>lr", vim.lsp.buf.rename, desc = "Rename" },
					})
				end,
			})

			-- ### CONFIGURE LSPs ###

			-- Set LSP capabilities
			local lsp_capabilities = require("cmp_nvim_lsp").default_capabilities()

			-- LSP Setup: clangd
			lspconfig.clangd.setup({
				capabilities = lsp_capabilities,
				cmd = {
					"clangd",
					"--background-index",
					"--clang-tidy",
					"--all-scopes-completion",
					"--completion-style=detailed",
					"--header-insertion-decorators",
					"--header-insertion=iwyu",
					"--fallback-style=google",
					"--pch-storage=memory",
					"--offset-encoding=utf-16",
				},
				init_options = {
					usePlaceholders = true,
					completeUnimported = true,
					clangdFileStatus = true,
				},
			})

			-- LSP Setup: cmake
			lspconfig.cmake.setup({
				capabilities = lsp_capabilities,
			})

			-- LSP Setup: lua_ls
			lspconfig.lua_ls.setup({
				capabilities = lsp_capabilities,
				settings = {
					Lua = {
						diagnostics = {
							globals = { "vim" },
						},
						completion = {
							callSnippet = "Replace",
						},
					},
				},
			})
		end,
	},
}
