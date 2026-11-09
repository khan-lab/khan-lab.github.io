-- Inline research and news bodies retain their source-file context.
local targets

local function inline_body(el)
  local origin = (el.attributes['data-inline-origin'] or el.attributes['data-research-origin'])
  if not origin then return nil end
  local id = el.attributes['data-inline-id'] or el.attributes['data-research-id']
  if not targets then
    local file = assert(io.open(quarto.project.directory .. '/_generated/inline-targets.json', 'r'))
    targets = quarto.json.decode(file:read('*a'))
    file:close()
  end
  local headers, minimum = {}, 7
  el:walk({Header = function(h)
    headers[h.identifier] = id .. '-' .. h.identifier
    minimum = math.min(minimum, h.level)
  end})
  local function rebase(target, image)
    if target:match('^[%a][%w+%.%-]*:') or target:sub(1, 2) == '//' then return target end
    if target:sub(1, 1) == '#' then
      return headers[target:sub(2)] and '#' .. headers[target:sub(2)] or target
    end
    local path, suffix = target:match('^([^?#]*)(.*)$')
    if path == '' then return target end
    local combined = path:sub(1, 1) == '/' and path or (origin:match('^(.*)/') or '') .. '/' .. path
    local parts = {}
    for part in combined:gmatch('[^/]+') do
      if part == '..' then
        if #parts > 0 then table.remove(parts) end
      elseif part ~= '.' then
        table.insert(parts, part)
      end
    end
    local absolute = '/' .. table.concat(parts, '/')
    local destination = not image and targets[absolute] or nil
    if destination then
      if destination.inline then
        local query = suffix:match('^(%?[^#]*)') or ''
        local fragment = suffix:match('#(.*)$')
        local base = destination.url:match('^([^#]*)')
        return base .. query .. '#' .. destination.id .. (fragment and '-' .. fragment or '')
      end
      return destination.url .. suffix
    end
    return absolute .. suffix
  end
  local function rebase_html(el)
    if el.format ~= 'html' then return nil end
    -- Authored HTML links/images need the same source context as Markdown.
    el.text = el.text:gsub('<[%a][^>]*>', function(tag)
      return tag:gsub('([%w_:%.%-]+)(%s*=%s*)(["\'])(.-)%3', function(name, equals, quote, value)
        local key = name:lower()
        if key == 'href' or key == 'src' then
          value = rebase(value, key == 'src')
        end
        return name .. equals .. quote .. value .. quote
      end)
    end)
    return el
  end
  el = el:walk({
    RawInline = rebase_html,
    RawBlock = rebase_html,
    Header = function(h)
      h.level = math.min(6, h.level + 3 - minimum)
      h.identifier = headers[h.identifier]
      return h
    end,
    Link = function(link)
      link.target = rebase(link.target, false)
      return link
    end,
    Image = function(image)
      image.src = rebase(image.src, true)
      return image
    end
  })
  local record = targets['/' .. origin]
  if el.classes:includes('news-body') and record and record.more_url and record.more_url ~= '' then
    local href, already_inline = record.more_url, false
    local function details_only(p)
      if #p.content == 1 and p.content[1].t == 'Link' and p.content[1].target == href then
        local label = pandoc.utils.stringify(p.content[1].content):lower()
        return label == 'more' or label == 'read more' or label == 'further details'
      end
      return false
    end
    el:walk({Para = function(p)
      if details_only(p) then return end
      p:walk({Link = function(link)
        if link.target == href then already_inline = true end
      end})
    end})
    if not already_inline then
      local index, final_paragraph = 0, nil
      el:walk({Para = function(p)
        index = index + 1
        local first = p.content[1]
        local source_only = #p.content == 1 and first.t == 'Link' and
          pandoc.utils.stringify(first.content):lower():match('^original ')
        local image_only = #p.content == 1 and (first.t == 'Image' or
          (first.t == 'RawInline' and first.text:match('^<img')))
        if #p.content > 0 and not source_only and not image_only and not details_only(p) then final_paragraph = index end
      end})
      -- Without a narrative paragraph, leave the authored destination intact.
      if final_paragraph then
        index = 0
        el = el:walk({Para = function(p)
          index = index + 1
          if index == final_paragraph then
            p.content:insert(pandoc.Space())
            p.content:insert(pandoc.Link('More', href, '', pandoc.Attr('', {'news-more'}, {['aria-label'] = 'More about ' .. record.title})))
            return p
          end
          if details_only(p) then return {} end
        end})
      end
    else
      el = el:walk({Para = function(p)
        if details_only(p) then return {} end
      end})
    end
  end
  el.attributes['data-inline-origin'] = nil
  el.attributes['data-inline-id'] = nil
  el.attributes['data-research-origin'] = nil
  el.attributes['data-research-id'] = nil
  return el
end

return {{Div = inline_body}}
