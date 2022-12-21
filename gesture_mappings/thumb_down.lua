local mode = vim.api.nvim_get_mode().mode
if mode == 'n' then
  local nt_view = require'nvim-tree.view'
  if nt_view.is_visible() then
    -- if nvim-tree is visible, scroll nvim-tree
    -- This may be too interruptive..
    local nt_api = require'nvim-tree.api'
    nt_api.tree.focus()
    vim.cmd[[normal! jzz]]
  else
    -- go down and keep cursor in the middle
    -- This may be too interruptive..
    vim.cmd[[normal! jzz]]
  end
elseif mode == 'i' then
  -- execute only once although it's in persistent mode
  if vim.g.hand_gesture_persistent_frame == 1 then
    vim.cmd[[call copilot#Dismiss()]]
  end
end
