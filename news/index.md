---
title: News
nav:
  order: 5
  tooltip: Lab news and updates
---

{% capture col1 %}

### {% include icon.html icon="fa-solid fa-newspaper" %}News and updates

{% include list.html data="news" component="news" %}

{% endcapture %}

{% include cols.html col1=col1 %}
