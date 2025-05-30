vim.g.mapleader = "\\"
vim.g.maplocalleader = " "

require("core.options")
require("core.lazy")
require("core.keymaps")

-- Remember last cursor position
vim.api.nvim_create_autocmd("BufReadPost", {
  pattern = "*",
  callback = function()
    local row, col = unpack(vim.api.nvim_buf_get_mark(0, '"'))
    if row > 0 and row <= vim.api.nvim_buf_line_count(0) then
      vim.api.nvim_win_set_cursor(0, {row, col})
    end
  end,
})

vim.opt.cursorline = true
vim.opt.cursorcolumn = true
vim.o.winbar = "%{%v:lua.require('core.winbar-config').set_winbar()%}"
