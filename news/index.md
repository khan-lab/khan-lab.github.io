---
title: News
---

# {% include icon.html icon="fa-solid fa-newspaper" %}Lab News and Updates


<ul>
    {% assign sorted_news = site.data.news | sort: "date" | reverse %}
    {% for post in sorted_news %}
      <li>
        <span> <strong>{{ post.title }}</strong> –  
        <i> {{ post.date | date: "%B %d, %Y" }} </i> </span>
        <br>
        <i>{{ post.description }} </i>
        {{ post.url }}
      </li>
    {% endfor %}
</ul>


