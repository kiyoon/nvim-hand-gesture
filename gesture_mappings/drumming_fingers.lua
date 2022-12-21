local mode = vim.api.nvim_get_mode().mode
if mode == 'n' then
  vim.cmd[[startinsert]]
elseif mode == 'i' then
  vim.cmd[[call copilot#Suggest()]]
end
