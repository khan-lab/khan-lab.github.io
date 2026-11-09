# CBCRG website

Source for the [Computational Biology & Cancer Regulatory Genomics Lab](https://khanlab.bio/) at MBZUAI, built with [ResearchLabFolio](https://github.com/khan-lab/researchlabfolio).

## Edit and preview

Install the sibling CLI, then run:

```sh
python -m pip install -e ../researchlabfolio-cli
rlf check
rlf preview
rlf build
```

Edit identity in `lab.yml`, records in `content/`, page text in `pages/` and images in `assets/`. Output is `_site/`.

This repository owns ongoing lab content. The template's CBCRG example is a separate demo snapshot.

[Documentation](https://khan-lab.github.io/researchlabfolio/) · [Publishing guide](https://khan-lab.github.io/researchlabfolio/guides/publishing.html)

Deployment is manual through GitHub Actions and requires `PAGES_ENABLED=true`.
