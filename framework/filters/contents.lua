-- Keep framework layout wrappers while exposing headings to Pandoc's native TOC.
-- Native contents only include headings at the document's block level.
local layouts = {
  ['blog-article'] = true, ['blog-source'] = true,
  ['research-overview'] = true, ['research-directions'] = true,
  ['research-direction'] = true, ['research-copy'] = true, ['research-body'] = true,
  ['teaching-list'] = true, ['teaching-course'] = true,
  ['course-content'] = true, ['course-heading-row'] = true
}

return {{Div = function(el)
  for _, class in ipairs(el.classes) do
    if layouts[class] then
      local shell = pandoc.write(pandoc.Pandoc({pandoc.Div({}, el.attr)}), 'html')
      local blocks = pandoc.List({pandoc.RawBlock('html', shell:match('^(<div[^>]*>)'))})
      blocks:extend(el.content)
      blocks:insert(pandoc.RawBlock('html', '</div>'))
      return blocks
    end
  end
end}}
