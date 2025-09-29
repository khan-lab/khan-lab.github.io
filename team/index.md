---
title: Team
nav:
  order: 3
  tooltip: Meet our team
---

# {% include icon.html icon="fa-solid fa-users" %}Meet Our Team

We are building a dedicated team of responsible researchers to advance the frontier of computational biology and genomics.
We are hiring at [all levels](/join/). Please send your CV with a cover email explaining your interest and fit.

{% include section.html %}

{% include list.html data="members" component="portrait" filter="role == 'principal-investigator'" %}

{% include list.html data="members" component="portrait" filter="role != 'principal-investigator' and alumni != true" %}

{% include section.html background="images/banner.jpg" dark=true %}

#### <center>We strive to build an inclusive environment for research and recognize the value of diversity in the process of scientific creativity and discovery.</center>

{%
  include button.html
  icon="fa-solid fa-handshake-angle"
  text="Join the Team"
  link="join"
  style="button"
%}
{% include section.html %}

## Our Allumni

{% include list.html data="members" component="portrait-alumni" filter="alumni == true" style="small" %}

{% include section.html %}

## Our Collaborators

{% include cols.html col1=col1 col2=col2 %}

{% capture col1 %}
{% include figure.html image="images/collaborators/uio.jpg"  height="250px" %}
{% endcapture %}

{% capture col2 %}
{% include figure.html image="images/collaborators/stanford.png" height="250px" %}
{% endcapture %}

{% capture col3 %}
{% include figure.html image="images/collaborators/nyuad.png"  height="250px" %}
{% endcapture %}

{% include cols.html col1=col1 col2=col2 col3=col3 %}
