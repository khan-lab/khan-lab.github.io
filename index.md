---
---
## We develop and use cutting-edge **open-source** tools, methods, and resources to *analyze*, *integrate*, and *interpret* large-scale **diverse multi-omics** cancer data; and to understand **gene regulation** and decipher the role of the non-coding **regulatory genome** to advance **precision medicine**.

{% include section.html %}

## Our vision and mission
> ##### "**Science and everyday life cannot and should not be separated**." *— Rosalind Franklin*

{% capture text %}

Our research bridges computational biology, (epi)genomics, machine learning, and data science to understand gene regulation in diseases such as cancer. We publish high-impact research papers in leading journals across diverse topics from genomics, epigenomic, machine learning, cancer genomics, and science policy.

{%
  include button.html
  link="publications"
  text="Explore our latest research"
  icon="fa-solid fa-arrow-right"
  flip=true
%}

{% endcapture %}

{%
  include feature.html
  image="images/home/mbzuai_2.jpg"
  link="publications"
  title="We bridge biology, multi-omics, AI, and data science"
  text=text
%}

{% capture text %}

We strongly believe in global access to open and reproducible science. Our tools, software, and resources are openly licensed and freely available for all to use and build upon.

{%
  include button.html
  link="tools"
  text="Access our open-source tools"
  icon="fa-solid fa-arrow-right"
  flip=true
%}

{% endcapture %}

{%
  include feature.html
  image="images/home/open-infrastructure.jpeg"
  link="tools"
  title="Open science and reproducibility is our foundation"
  flip=true
  style="bare"
  text=text
%}

{% capture text %}

We are building a dedicated team of responsible researchers to advance the frontier of computational cancer genomics. We strive to build an inclusive environment for research and recognize the value of diversity in the process of scientific creativity and discovery.

{%
  include button.html
  link="join"
  text="Be part of the team"
  icon="fa-solid fa-arrow-right"
  flip=true

%}

{% endcapture %}

{%
  include feature.html
  image="images/home/team.jpeg"
  link="join"
  title="Training the next generation of scientists"
  text=text
%}

{% include section.html %}

{% capture col1 %}
## Lab latest news
  <ul>
  {% assign sorted_news = site.data.news | sort: "date" | reverse %}
    {% for post in sorted_news limit:3 %}
      <li>
        <strong>{{ post.title }}</strong> – <span> <i> {{ post.date | date: "%B %d, %Y" }} </i></span>
        <br/> {{ post.description }} 
        {% if post.url %}
                <a href="{{ post.url }}">More details...</a>
        {% endif %}
      </li>
    {% endfor %}
  </ul>
  <a href="/news/">See all news →</a>

{% endcapture %}


{% include cols.html col1=col1 %}
