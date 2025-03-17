---
title: Team
nav:
  order: 3
  tooltip: Meet our team
---

# {% include icon.html icon="fa-solid fa-users" %}Meet Our Team
We are a dedicated team of responsible researchers that want to push the frontier of computational cancer genomics. We strive to build an inclusive environment for research, and recognize the value of diversity in the process of discovery.

{% include section.html %}

{% include list.html data="members" component="portrait" filter="role == 'pi'" %}
{% include list.html data="members" component="portrait" filter="role != 'pi'" %}

{% include section.html background="images/background.jpg" dark=true %}

#### We are hiring at all levels: Research Associates, Postdocs, PhD and Master's students, and Visiting Researchers. Please send your CV with a cover email explaining your interest.

{%
  include button.html
  icon="fa-solid fa-handshake-angle"
  text="Join the Team"
  link="join"
  style="button"
%}

{% include section.html %}


{% include section.html %}

<!-- 
## Funding

{% capture content %}
[![MBZUAI](/images/mbzuai_logo.png)](https://mbzuai.ac.ae)

{% endcapture %}

{% include grid.html style="square" content=content %}
-->
