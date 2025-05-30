-- Provides syntax highlighting for the ghostty config file
-- No additional dependencies required, Zilchmasta was kind enough to let me
-- know about this in discord
-- https://discord.com/channels/1005603569187160125/1300462095946485790/1300534513788653630

local is_mac = vim.loop.os_uname().sysname == "Darwin"
local plugin_dir = is_mac and "/Applications/Ghostty.app/Contents/Resources/vim/vimfiles/" or "/usr/share/nvim/site"

return {
	"ghostty",
	dir = plugin_dir,
	lazy = false,
}
