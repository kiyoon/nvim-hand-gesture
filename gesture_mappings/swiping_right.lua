local mode = vim.api.nvim_get_mode().mode
if mode == 'n' then
elseif mode == 'i' then
  vim.cmd[[call copilot#Next()]]
end
