<%
// A custom description field preserves images that Quarto removes from its standard listing-description field.
// Quarto uses Lodash templates: <%= interpolates, <%- escapes.
const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
%>

```{=html}
<div class="list quarto-listing-default">
<% for (const item of items) { %>
<article class="quarto-post news-entry<% if (item['is-latest']) { %> news-latest<% } %>" id="<%= html(item['entry-id']) %>" <%= metadataAttrs(item) %>>
<div class="metadata"><time class="listing-date" datetime="<%= html(item['entry-date']) %>"><%= html(item.date) %></time></div>
<div class="body">
<h2 class="no-anchor listing-title"><% if (item['detail-page']) { %><a href="<%= html(item['entry-href']) %>"><%= html(item['entry-title']) %></a><% } else { %><%= html(item['entry-title']) %><% } %></h2>
<div class="listing-entry-description">
```

<% if (!item['detail-page'] && item['entry-body'].trim()) { %>
<%= item['entry-fence'] %> {.news-body data-inline-origin="<%= html(item['entry-source']) %>" data-inline-id="<%= html(item['entry-id']) %>"}

<%= item['entry-body'] %>

<%= item['entry-fence'] %>
<% } else { %>
```{=html}
<p><%= html(item['entry-description']) %><% if (item['detail-page'] || item['more-url']) { %> <a class="news-more" href="<%= html(item['detail-page'] ? item['entry-href'] : item['more-url']) %>" aria-label="More about <%= html(item['entry-title']) %>">More</a><% } %></p>
```
<% } %>

```{=html}
</div>
<% if (item['entry-image']) { %><img class="news-image" src="<%= html(item['entry-image']) %>" alt="<%= html(item['entry-image-alt']) %>" loading="lazy"><% } %>
</div>
</article>
<% } %>
</div>
```
