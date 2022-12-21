local mode = vim.api.nvim_get_mode().mode
if mode == 'n' then
  vim.api.nvim_command('NvimTreeClose')
elseif mode == 'i' then
  vim.cmd[[call copilot#Previous()]]
end
