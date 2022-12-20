colorschemes = { 'nightfox', 'tokyonight-night', 'terafox', 'nordfox' }

-- string starts with
function string.starts(String,Start)
   return string.sub(String,1,string.len(Start))==Start
end

-- Find the current colorscheme
local current_colorscheme = vim.g.colors_name
local current_colorscheme_index = 0
for i, colorscheme in ipairs(colorschemes) do
  if string.starts(colorscheme, current_colorscheme) then
    current_colorscheme_index = i
  end
end

-- Cycle through the colorschemes
current_colorscheme_index = current_colorscheme_index + 1
if current_colorscheme_index > #colorschemes then
  current_colorscheme_index = 1
end
vim.cmd('colorscheme ' .. colorschemes[current_colorscheme_index])
