local mode = vim.api.nvim_get_mode().mode
if mode == 'n' then
  -- peek definition
  vim.api.nvim_input('\\df')
elseif mode == 'i' then
end
