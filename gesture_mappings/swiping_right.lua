local mode = vim.api.nvim_get_mode().mode
if mode == 'n' then
  local buf = vim.api.nvim_get_current_buf()
  -- open nvim tree
  vim.api.nvim_command('NvimTreeOpen')
  -- focus on the original buffer (uninterrupted workflow)
  vim.api.nvim_set_current_buf(buf)
elseif mode == 'i' then
  vim.cmd[[call copilot#Next()]]
end
