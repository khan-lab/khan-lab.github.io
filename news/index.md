---
title: News
nav:
  order: 5
  tooltip: Lab news and updates
---


{% capture col1 %}
###  {% include icon.html icon="fa-solid fa-newspaper" %}News and updates

{% include list.html data="news" component="news" %}

{% endcapture %}

<!-- 
{% capture col2 %}
###  {% include icon.html icon="fa-brands fa-bluesky" %}[BlueSky](https://bsky.app/profile/khanlab.bio) feeds

<div class="news-card" style="align: left">   
<script type="module" src="https://cdn.jsdelivr.net/npm/bsky-embed/dist/bsky-embed.es.js" async></script>

  <bsky-embed
    username="khanlab.bio"
    mode=""
    limit="3"
    link-target="_blank"
    link-image="true"
    load-more="false"
    disable-styles="false"
    custom-styles=".border-slate-300 { border-color: gray; text-align: left}"
    date-format='{"type":"absolute","locale":"en","options":{"weekday":"long","year":"numeric","month":"long","day":"numeric"}}'
  >
</bsky-embed>
</div>

{% endcapture %}

--->

{% include cols.html col1=col1 col2=col2 %}




