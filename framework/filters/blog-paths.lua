-- Published posts move to /blog/ while Markdown keeps its authored context.
local targets

local function source_body(el)
  local origin = el.attributes['data-blog-origin']
  if not origin then return nil end
  if not targets then
    local file = assert(io.open(quarto.project.directory .. '/_generated/inline-targets.json', 'r'))
    targets = quarto.json.decode(file:read('*a'))
    file:close()
  end
  local function rebase(value, image)
    if value:match('^[%a][%w+%.%-]*:') or value:sub(1, 2) == '//' or value:sub(1, 1) == '#' then return value end
    local path, suffix = value:match('^([^?#]*)(.*)$')
    if path == '' then return value end
    local combined = path:sub(1, 1) == '/' and path or origin .. '/' .. path
    local parts = {}
    for part in combined:gmatch('[^/]+') do
      if part == '..' then
        if #parts > 0 then table.remove(parts) end
      elseif part ~= '.' then table.insert(parts, part) end
    end
    local absolute = '/' .. table.concat(parts, '/')
    if not image then
      local destination = targets[absolute]
      if destination then
        if destination.inline then
          local query = suffix:match('^(%?[^#]*)') or ''
          local fragment = suffix:match('#(.*)$')
          return destination.url:match('^([^#]*)'):gsub('%.qmd$', '.html') .. query .. '#' .. destination.id .. (fragment and '-' .. fragment or '')
        end
        return destination.url:gsub('%.qmd$', '.html') .. suffix
      end
      absolute = absolute:gsub('^/content/blog/([^/]+)%.qmd$', '/blog/%1.qmd')
      absolute = absolute:gsub('^/content/blog/([^/]+)%.html$', '/blog/%1.html')
      absolute = absolute:gsub('^/pages/opportunities%.', '/pages/join.')
      absolute = absolute:gsub('^/pages/([^/]+)%.qmd$', '/%1/index.qmd')
      absolute = absolute:gsub('^/pages/([^/]+)%.html$', '/%1/')
      -- Quarto does not consistently resolve .qmd links with query strings.
      absolute = absolute:gsub('%.qmd$', '.html')
    end
    return absolute .. suffix
  end
  local function html_links(raw)
    if raw.format ~= 'html' then return nil end
    raw.text = raw.text:gsub('<[%a][^>]*>', function(tag)
      return tag:gsub('([%w_:%.%-]+)(%s*=%s*)(["\'])(.-)%3', function(name, equals, quote, value)
        local key = name:lower()
        if key == 'href' or key == 'src' then value = rebase(value, key == 'src') end
        return name .. equals .. quote .. value .. quote
      end)
    end)
    return raw
  end
  el = el:walk({
    CodeBlock = function(block) block.attributes['tabindex'] = '0'; return block end,
    Link = function(link) link.target = rebase(link.target, false); return link end,
    Image = function(image) image.src = rebase(image.src, true); return image end,
    RawInline = html_links,
    RawBlock = html_links
  })
  el.attributes['data-blog-origin'] = nil
  return el
end

return {{Div = source_body}}
