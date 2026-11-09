/* Optional browser QA. Install tools under .scratch/browser; see documentation/reference/testing.qmd. */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.resolve('.scratch/browser/node_modules/playwright'));
const { AxeBuilder } = require(path.resolve('.scratch/browser/node_modules/@axe-core/playwright'));
const assert = require('assert/strict');

(async () => {
  const colorScheme = process.env.LABFOLIO_TEST_COLOR_SCHEME || 'light';
  assert.ok(['light', 'dark'].includes(colorScheme));
  const screenshotDir = colorScheme === 'dark' ? '.scratch/screenshots/dark' : '.scratch/screenshots';
  const resultSuffix = colorScheme === 'dark' ? '-dark' : '';
  fs.mkdirSync(screenshotDir, {recursive: true});
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const results = [];
  const consoleErrors = [];
  const networkErrors = [];
  const optionalBadgeRequests = [];
  const cbcrgCitations = JSON.parse(fs.readFileSync('examples/cbcrg/_site/assets/publications.json'));
  const origins = process.env.LABFOLIO_TEST_ORIGIN || 'http://127.0.0.1:8765';
  async function checkTimeline(rail, date) {
    assert.equal(await rail.evaluate(el => getComputedStyle(el).borderLeftWidth), '1px');
    assert.ok(await date.evaluate(el => {
      const marker = getComputedStyle(el, '::before');
      return marker.content !== 'none' && marker.borderRadius === '50%' && parseFloat(marker.width) === 10;
    }), 'Timeline has a circular date marker');
    const markers = await rail.evaluate(el => {
      const railX = el.getBoundingClientRect().x + parseFloat(getComputedStyle(el).borderLeftWidth) / 2;
      return [...el.querySelectorAll(el.classList.contains('news-rows') ? 'article > time' : '.metadata')].map(date => {
        const rect = date.getBoundingClientRect();
        const style = getComputedStyle(date, '::before');
        const transform = new DOMMatrix(style.transform);
        return {
          dx: Math.abs(rect.x + parseFloat(style.left) + transform.m41 + parseFloat(style.width) / 2 - railX),
          dy: Math.abs(parseFloat(style.top) + transform.m42 + parseFloat(style.height) / 2 - rect.height / 2),
          filled: style.backgroundColor === style.borderTopColor,
          latest: date.closest('article').classList.contains('news-latest')
        };
      });
    });
    assert.equal(markers.filter(marker => marker.latest).length, 1);
    for (const marker of markers) {
      assert.ok(marker.dx <= .5 && marker.dy <= .5, 'Marker is centered on the rail and date');
      assert.equal(marker.filled, marker.latest, 'Only the actual latest news marker is filled');
    }
  }
  async function checkInlineMore(links) {
    for (const link of await links.all()) {
      assert.ok(await link.evaluate(el => el.parentElement.tagName === 'P' &&
        el.parentElement.textContent.trim().length > el.textContent.trim().length &&
        getComputedStyle(el).display === 'inline' && el.previousSibling.nodeName !== 'BR'), 'More follows description text in the same paragraph');
    }
  }
  async function checkResourceActions(cards) {
    for (const card of await cards.all()) {
      assert.ok(await card.evaluate(el => {
        const style = getComputedStyle(el), box = el.getBoundingClientRect();
        const last = el.querySelector('.resource-link:last-child').getBoundingClientRect();
        const header = el.querySelector('.resource-header');
        const headerBox = header.getBoundingClientRect();
        const contentBottom = el.lastElementChild.getBoundingClientRect().bottom;
        const insetRight = parseFloat(style.paddingRight) + parseFloat(style.borderRightWidth);
        const insetBottom = parseFloat(style.paddingBottom) + parseFloat(style.borderBottomWidth);
        return el.firstElementChild === header && header.contains(el.querySelector('.resource-links')) &&
          getComputedStyle(el).alignSelf === 'start' && parseFloat(style.paddingBottom) <= 20 &&
          Math.abs(parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)) < 1 &&
          Math.abs(box.right - last.right - insetRight) < 1 &&
          Math.abs(headerBox.top + headerBox.height / 2 - last.top - last.height / 2) < 1 &&
          Math.abs(box.bottom - contentBottom - insetBottom) < 1;
      }), 'Resource icons share the type row; compact cards fit content with balanced padding');
      for (const action of await card.locator('.resource-link').all()) {
        assert.ok(await action.getAttribute('aria-label'));
        assert.ok(await action.getAttribute('title'));
        assert.equal(await action.locator('.resource-link-caption').isVisible(), false);
        const box = await action.boundingBox();
        assert.ok(Math.abs(box.width - 32) < 1 && Math.abs(box.height - 32) < 1);
      }
    }
  }
  const sections = ['', 'research/', 'people/', 'publications/', 'software/', 'news/', 'blog/', 'join/', 'contact/'];
  try {
    for (const [site, base] of [['generic', '/_site/'], ['cbcrg', '/examples/cbcrg/_site/']]) {
      for (const [device, viewport] of [['desktop', {width:1440, height:1000}], ['mobile', {width:390, height:844}]]) {
        const context = await browser.newContext({viewport, reducedMotion: 'reduce', colorScheme});
        // Verify the sites need no external network resources while browsing.
        await context.route('**/*', route => {
          if (route.request().url().startsWith(origins)) return route.continue();
          // Test the optional-provider-unavailable state without depending on live scores.
          if (route.request().url() === 'https://embed.altmetric.com/assets/embed.js') {
            optionalBadgeRequests.push(route.request().url());
            return route.fulfill({contentType: 'application/javascript', body: ''});
          }
          networkErrors.push(route.request().url());
          return route.abort();
        });
        const page = await context.newPage();
        page.on('pageerror', err => consoleErrors.push(String(err)));
        page.on('response', response => { if(response.status() >= 400) networkErrors.push(`${response.status()} ${response.url()}`); });
        const profilePath = site === 'generic' ? 'people/alex-researcher.html' : 'people/aziz-khan.html';
        let homepageWidth;
        for (const section of [...sections, 'teaching/', profilePath]) {
          const response = await page.goto(origins + base + (section || 'index.html'));
          assert.equal(response.status(), 200);
          if (site === 'cbcrg') {
            assert.equal(await page.locator('a[href*="khan-lab/khan-lab.github.io/blob/"]').count(), 0, 'Migration evidence stays out of public page links');
            assert.equal(await page.locator('.source-link, .paper-link-source').count(), 0);
            assert.ok(!(await page.locator('main').innerText()).includes('Original news record'));
          }
          await page.evaluate(() => document.fonts.ready);
          assert.ok(await page.locator('body').evaluate((el, scheme) => el.classList.contains('quarto-' + scheme), colorScheme));
          const themeSwitch = page.locator('.quarto-color-scheme-toggle');
          assert.ok(await themeSwitch.isVisible());
          const switchBounds = await themeSwitch.boundingBox();
          const searchBounds = await page.locator('#quarto-search').boundingBox();
          assert.ok(searchBounds.x - switchBounds.x - switchBounds.width >= -1 && searchBounds.x - switchBounds.x - switchBounds.width <= 16, 'Theme switch is beside search');
          assert.ok(Math.abs(switchBounds.y + switchBounds.height / 2 - searchBounds.y - searchBounds.height / 2) < 3);
          await page.locator('img').evaluateAll(async images => {
            images.forEach(img => img.loading = 'eager');
            await Promise.all(images.map(img => img.decode().catch(() => {})));
          });
          assert.ok(await page.getByRole('navigation', {name: 'Footer links'}).isVisible());
          const guide = page.locator('.footer-guide');
          assert.equal(await guide.getAttribute('href'), 'https://khan-lab.github.io/researchlabfolio/');
          assert.equal(await guide.innerText(), 'Documentation');
          assert.ok(await page.locator('.footer-identity').innerText());
          assert.equal(await page.locator('.footer-source').getAttribute('href'), 'https://github.com/khan-lab/researchlabfolio');
          assert.equal(await page.locator('.footer-source .bi-github[aria-hidden="true"]').count(), 1);
          const piFooter = page.locator('.footer-pi-profile');
          const footerLogo = page.locator('.footer-brand-logo');
          assert.equal(await footerLogo.count(), site === 'cbcrg' ? 1 : 0);
          if (site === 'cbcrg') {
            assert.ok(await footerLogo.getAttribute('alt'));
            assert.ok(await footerLogo.evaluate(el => {
              const bounds = el.getBoundingClientRect(), parent = el.parentElement.getBoundingClientRect();
              const previous = el.previousElementSibling.getBoundingClientRect();
              return el.complete && el.naturalWidth > 0 && bounds.width > 0 && bounds.height > 0 && bounds.top >= previous.bottom && Math.abs(bounds.right - parent.right) <= 1;
            }), 'Footer logo is right aligned below the links/icons');
          }
          assert.equal(await piFooter.count(), site === 'generic' ? 1 : 0);
          if (site === 'generic') {
            assert.equal(await piFooter.locator('.footer-pi-label').count(), 0);
            assert.ok(!(await piFooter.innerText()).includes('Alex Researcher'));
            const footerNav = await page.locator('.footer-links').boundingBox();
            const iconRow = await piFooter.boundingBox();
            const footerMain = await page.locator('.footer-main').boundingBox();
            assert.ok(iconRow.y >= footerNav.y + footerNav.height, 'Footer PI icons appear below the page links');
            assert.ok(Math.abs(iconRow.x + iconRow.width - footerMain.x - footerMain.width) < 2, 'Footer PI icons align to the far right');
            for (const [label, destination] of [['GitHub', 'https://github.com/'], ['Google Scholar', 'https://scholar.google.com/'], ['ORCID', 'https://orcid.org/']]) {
              const icon = piFooter.getByRole('link', {name: label, exact: true});
              assert.equal(await icon.getAttribute('href'), destination);
              assert.equal(await icon.getAttribute('title'), label);
            }
          }
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
          assert.equal(overflow, false, `${site} ${device} ${section}: horizontal overflow`);
          const contentWidth = await page.locator('main').evaluate(el => el.getBoundingClientRect().width);
          if (!section) homepageWidth = contentWidth;
          else assert.ok(Math.abs(contentWidth - homepageWidth) < 2, `${site} ${device} ${section}: matches homepage width`);
          const brokenImages = await page.locator('img').evaluateAll(images => images.filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src));
          assert.deepEqual(brokenImages, [], 'Broken images');
          if (!section) {
            await checkTimeline(page.locator('.news-rows'), page.locator('.news-rows time').first());
            assert.equal(await page.locator('.news-rows .news-more').count(), 3);
            await checkInlineMore(page.locator('.news-rows .news-more'));
            for (const description of await page.locator('.home-news .news-description').all()) {
              assert.ok(await description.evaluate(el => el.getBoundingClientRect().height <= 2 * parseFloat(getComputedStyle(el).lineHeight) + 1), 'Homepage news previews fit within two lines');
              const paragraph = await description.boundingBox();
              const more = await description.locator('.news-more').boundingBox();
              assert.ok(more.y + more.height <= paragraph.y + paragraph.height + 1, 'More stays visible within the two-line preview');
            }
            for (const researchLink of await page.locator('.home-research-list h3 a:not(.anchorjs-link)').all()) {
              assert.ok((await researchLink.getAttribute('href')).includes('research/#'), 'Default research previews target overview rows');
            }
            for (const newsLink of await page.locator('.home-news .news-rows h3 a:not(.anchorjs-link)').all()) {
              assert.ok((await newsLink.getAttribute('href')).includes('news/#'), 'Default news previews target inline entries');
            }
            assert.equal(await page.locator('h1').count(), 1);
            assert.equal(await page.locator('.hero-main h1#home-title').count(), 1, 'Headline stays inside the hero beside its figure');
            assert.equal(await page.locator('.home-overview, .home-affiliation, .home-lead').count(), 0, 'No affiliation or PI panel beneath the figure by default');
            assert.equal(await page.locator('.home-facts').count(), 0, 'Metrics are opt-in rather than automatic collection counts');
            assert.equal(await page.locator('.hero-main > .home-lab-name').innerText(), site === 'cbcrg' ? 'Computational Biology and Cancer Regulatory Genomics Lab' : 'Example Research Lab', 'Full lab name appears above the heading');
            if (site === 'cbcrg') {
              assert.equal(await page.locator('.home-statements .home-statement').count(), 2);
              assert.equal(await page.locator('.home-statements-pair').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), device === 'desktop' ? 2 : 1);
              assert.ok(await page.getByRole('heading', {name: 'Our mission', exact: true}).isVisible());
              assert.ok(await page.getByRole('heading', {name: 'Our vision', exact: true}).isVisible());
              assert.equal(await page.locator('.home-quote blockquote').innerText(), '“Science and everyday life cannot and should not be separated.”');
              assert.equal(await page.locator('.home-quote figcaption').innerText(), '— Rosalind Franklin');
              assert.equal(await page.locator('#home-title').innerText(), 'Deciphering the cancer genome and epigenome.');
              assert.ok((await page.locator('.home-hero-figure img').getAttribute('src')).endsWith('assets/demo/research-summary.svg'));
              assert.equal(await page.locator('.home-hero-figure figcaption').count(), 0, 'CBCRG hero has no Research themes caption');
            }
            assert.ok(await page.locator('.hero-main').evaluate(el => el.firstElementChild.classList.contains('home-lab-name')));
            assert.ok(await page.locator('.home-hero-figure img').isVisible());
            assert.deepEqual(await page.locator('.hero-actions a').allTextContents(), ['Join the lab', 'Publications']);
            if (await page.locator('.home-recruitment-with-image').count()) {
              const joinCopy = await page.locator('.home-recruitment-content').boundingBox();
              const joinPhoto = await page.locator('.home-recruitment-photo').boundingBox();
              if (device === 'desktop') assert.ok(Math.abs(joinPhoto.width / (joinPhoto.width + joinCopy.width) - .6) < .002, 'Recruitment photo uses 60% of desktop column space');
              else assert.ok(joinPhoto.y >= joinCopy.y + joinCopy.height, 'Recruitment photo stacks below copy on mobile');
            }
            const hero = await page.locator('.hero-main').boundingBox();
            const figure = await page.locator('.home-hero-figure').boundingBox();
            assert.ok(device === 'desktop' ? figure.x >= hero.x + hero.width : figure.y >= hero.y + hero.height, 'Hero figure adapts to the screen');
            if (device === 'desktop') assert.ok(Math.abs(figure.width - hero.width) < 1, 'Hero gives text and figure equal width');
            assert.ok(await page.locator('.home-hero-figure img').evaluate(img => {
              const box = img.getBoundingClientRect();
              return getComputedStyle(img).maxHeight === 'none' && Math.abs(box.height - box.width * img.naturalHeight / img.naturalWidth) < 2;
            }), 'Hero figure fills its column at its natural aspect ratio without a height cap');
            assert.ok(await page.locator('.home-hero').evaluate(el => {
              const s = getComputedStyle(el);
              return parseFloat(s.marginTop) === 0 && parseFloat(s.marginBottom) === 0 && parseFloat(s.paddingTop) <= 24 && parseFloat(s.paddingBottom) <= 24;
            }), 'Hero has compact space above its content and before the bottom divider');
            const news = await page.locator('.home-news').boundingBox();
            const resources = await page.locator('.home-resources').boundingBox();
            assert.ok(news.y < resources.y, 'Recent activity is near the research introduction');
            const tools = page.locator('.home-resource');
            assert.equal(await tools.count(), 3);
            assert.equal(await tools.locator('h3 a:not(.anchorjs-link)').count(), 0, 'Homepage resource names remain plain text');
            assert.equal(await tools.locator('.resource-website .bi-globe2').count(), await tools.count());
            assert.equal(await tools.locator('.resource-code').count(), 3);
            await checkResourceActions(tools);
            assert.equal(await page.locator('.home-publications .paper h2').count(), 0, 'Paper headings nest under the publication section');
            assert.equal(await page.locator('.home-person:visible').count(), 3);
            assert.equal(await page.locator('.home-person').count(), site === 'cbcrg' ? 8 : 9, 'All current members are eligible for the homepage selection');
            if (site === 'cbcrg') {
              assert.equal(await page.locator('.home-publications .paper-compact').count(), 3);
              assert.equal(await page.locator('.home-publications .paper-link-code').count(), 3);
              assert.equal(await page.locator('.home-publications .paper-link-data').count(), 3);
              assert.equal(await page.locator('.home-publications .paper-link-pdf').count(), 3);
              assert.equal(await page.locator('.home-publications .paper-link-preprint').count(), 2);
              for (const paper of await page.locator('.home-publications .paper').all()) {
                if (device === 'desktop') assert.ok((await paper.boundingBox()).height < 140, 'Homepage publication previews stay compact');
                assert.equal(await paper.evaluate(el => getComputedStyle(el).backgroundColor), 'rgba(0, 0, 0, 0)', 'Homepage papers are compact rows without filled boxes');
                const links = await paper.locator('.paper-actions .paper-links').boundingBox();
                const metric = await paper.locator('.paper-actions .paper-altmetric').boundingBox();
                assert.ok(metric.x >= links.x + links.width, 'Altmetric sits beside the publication actions');
                assert.ok(Math.abs(metric.y + metric.height / 2 - links.y - links.height / 2) < 1, 'Altmetric and publication actions share the same vertical center');
                assert.equal(await paper.locator('.altmetric-details').count(), 0, 'No text caption is added beneath the donut');
                assert.ok(await paper.locator('.paper-link-doi').isVisible(), 'Citation actions remain usable without the badge provider');
              }
            }
          }
          if (section === 'publications/' || !section) {
            for (const action of await page.locator('.paper-link').all()) {
              assert.ok(await action.getAttribute('title'));
              assert.ok(await action.getAttribute('aria-label'));
              assert.equal(await action.locator('i[aria-hidden="true"]').count(), 1);
              assert.equal(await action.locator('.paper-link-caption').textContent(), await action.getAttribute('title'));
            }
            assert.equal(await page.locator('.altmetric-embed').count(), site === 'cbcrg' ? (!section ? 3 : cbcrgCitations.filter(p => p.DOI).length) : 0);
          }
          if (site === 'generic' && !section) {
            assert.equal(await page.locator('.home-publications .paper').count(), 3);
            assert.ok((await page.locator('.hero .lede').innerText()).includes('fictional'));
          }
          if (section === 'publications/' && site === 'generic') {
            assert.equal(await page.locator('[data-publications] .paper').count(), 8);
            assert.ok((await page.locator('main').innerText()).includes('not publications by the fictional'));
            await page.locator('#paper-featured').click();
            assert.equal(await page.locator('[data-publications] .paper:visible').count(), 3);
            await page.locator('#paper-featured').click();
            await page.locator('#paper-type').selectOption('preprint');
            assert.equal(await page.locator('[data-publications] .paper:visible').count(), 2);
            await page.locator('#paper-type').selectOption('');
          }
          if (section === 'publications/' && site === 'cbcrg') {
            assert.equal(await page.locator('[id="work-f32ba2e7b2e6bf90"] .paper-authors strong.paper-lab-author').first().textContent(), 'Aziz Khan');
            assert.notEqual(await page.locator('.publication-filters').getAttribute('open'), null, 'Search and filters start expanded');
            assert.ok(await page.locator('#paper-search').isVisible());
            const scholar = page.locator('.publication-toolbar-actions .pi-scholar');
            assert.equal(await scholar.getAttribute('href'), 'https://scholar.google.com/citations?user=m23RfrcAAAAJ&sortby=pubdate');
            const buttonBounds = await page.locator('#paper-featured').boundingBox();
            const scholarBounds = await scholar.boundingBox();
            assert.ok(scholarBounds.x >= buttonBounds.x + buttonBounds.width, 'PI Google Scholar link sits next to Featured only');
            for (const paper of await page.locator('[data-publications] .paper').all()) {
              assert.ok(await paper.evaluate(el => el.firstElementChild.classList.contains('paper-year')), 'Year starts each publication');
              assert.ok(await paper.locator('.paper-year').evaluate(el => Number(getComputedStyle(el).fontWeight) >= 600));
              const links = await paper.locator('.paper-actions .paper-links').boundingBox();
              const badge = paper.locator('.paper-actions .paper-altmetric');
              const metric = await badge.count() ? await badge.boundingBox() : null;
              if (metric) assert.ok(metric.x >= links.x + links.width - 1, 'Publication actions sit beside the Altmetric donut');
            }
          }
          if (site === 'cbcrg' && !section) {
            assert.equal(await page.locator('[id="work-f32ba2e7b2e6bf90"] summary strong.paper-lab-author').textContent(), 'Aziz Khan', 'Lab author is retained in the compact DCIS preview');
            const directions = await page.locator('.home-research-list h3').allTextContents();
            assert.equal(directions.length, 3);
            assert.ok(!directions.includes('Diverse pangenomes and personal genomes'), 'Diverse-genomes direction remains off Home');
            for (const title of ['AI for regulatory genomics', 'Gene regulation and non-coding mutations in cancer', 'Open-source tools, methods and resources']) {
              assert.ok(directions.some(text => text.includes(title)), 'Homepage includes ' + title);
            }
          }
          if (section === 'research/') {
            const summary = await page.locator('.research-summary').boundingBox();
            const firstDirection = await page.locator('.research-direction').first().boundingBox();
            assert.ok(summary.y + summary.height <= firstDirection.y, 'Research summary precedes the directions');
            if (site === 'cbcrg') assert.ok((await page.locator('.research-summary').innerText()).includes('non-coding genome'));
            const overviewFigure = page.locator('.research-summary-figure');
            assert.equal(await overviewFigure.count(), site === 'cbcrg' ? 1 : 0);
            if (site === 'cbcrg') {
              const figure = await overviewFigure.boundingBox();
              assert.equal(await page.locator('#diverse-genomes .research-heading').innerText(), 'Diverse pangenomes and personal genomes', 'Unfeatured direction remains on Research');
              const column = await page.locator('.research-directions').boundingBox();
              assert.ok((await overviewFigure.locator('img').getAttribute('src')).endsWith('assets/demo/research-summary.svg'));
              assert.ok(await overviewFigure.locator('img').getAttribute('alt'));
              assert.equal(await overviewFigure.locator('figcaption').count(), 0);
              assert.equal(await page.locator('.research-direction .research-summary-figure').count(), 0, 'Shared figure belongs to the complete direction list');
              assert.ok(device === 'desktop' ? figure.x >= column.x + column.width : figure.y + figure.height <= column.y, 'Shared figure sits beside all directions, or above them on mobile');
              if (device === 'desktop') assert.ok(Math.abs(figure.width - column.width) < 1 && Math.abs(figure.y - column.y) < 1, 'Direction list and figure use equal-width top-aligned columns');
              assert.ok(summary.y + summary.height <= figure.y, 'Full-width summary remains above the figure and directions');
              const mainWidth = await page.locator('main').evaluate(el => el.getBoundingClientRect().width);
              assert.ok(Math.abs(mainWidth - summary.width) < 1, 'Summary paragraph keeps the full page width above directions');
            }
            const directions = page.locator('.research-direction');
            assert.equal(await directions.count(), site === 'cbcrg' ? 4 : 3);
            const bounds = await directions.evaluateAll(items => items.map(item => {
              const box = item.getBoundingClientRect();
              return {x: box.x, y: box.y, width: box.width, height: box.height, radius: parseFloat(getComputedStyle(item).borderRadius)};
            }));
            for (let i = 0; i < bounds.length; i++) {
              assert.ok(bounds[i].radius > 0, 'Research rows retain soft corners');
              if (i) {
                assert.ok(bounds[i].y >= bounds[i-1].y + bounds[i-1].height, 'One research direction per row');
                assert.ok(Math.abs(bounds[i].x-bounds[0].x) < 1 && Math.abs(bounds[i].width-bounds[0].width) < 1);
              }
            }
            assert.equal(await directions.locator('.research-heading a:not(.anchorjs-link)').count(), 0, 'Separate research pages are disabled by default');
            assert.ok(await directions.locator('.research-body').count() > 0, 'Authored research prose is available inline');
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-research.png`, fullPage: true});
          }
          if (section === 'news/') {
            assert.equal(await page.evaluate(() => window['quarto-listings']['listing-lab-news'].items.length), site === 'cbcrg' ? 22 : 9, 'Native pagination retains the full news pool');
            assert.equal(await page.locator('.news-entry .listing-title a:not(.anchorjs-link)').count(), 0, 'Individual news pages are off by default');
            assert.ok(await page.locator('.news-body').count() > 0, 'News content remains available inline');
            const item = page.locator('.quarto-post:visible').first();
            await checkTimeline(page.locator('.news-page .list.quarto-listing-default'), item.locator('.metadata'));
            await checkInlineMore(page.locator('.news-entry .news-more'));
            if (site === 'cbcrg') {
              assert.equal(await item.locator('.news-more').count(), 1, 'Source details link appears inline once');
              assert.ok(await item.locator('.news-body i').count() > 0, 'Authored inline HTML formatting is preserved');
              assert.ok(!(await item.locator('.news-body').innerText()).includes('<i>'), 'News HTML is rendered once');
            }
            const date = await item.locator('.listing-date').boundingBox();
            const title = await item.locator('.listing-title').boundingBox();
            assert.ok(date.y + date.height <= title.y, 'News date is above the title');
            assert.ok(Math.abs(date.x - title.x) < 2, 'News date and title share the same left edge');
            assert.ok(await item.locator('.listing-title').evaluate(el => parseFloat(getComputedStyle(el).fontSize) <= 20));
            assert.ok(await item.locator('.listing-entry-description').evaluate(el => parseFloat(getComputedStyle(el).fontSize) <= 16));
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-news.png`, fullPage: true});
            const filter = page.locator('.quarto-listing-filter input');
            await filter.pressSequentially(site === 'cbcrg' ? 'Sabanci' : 'Welcome');
            await page.waitForFunction(() => [...document.querySelectorAll('.quarto-post')].filter(el => el.offsetWidth || el.offsetHeight || el.getClientRects().length).length === 1);
            assert.equal(await page.locator('.quarto-post:visible').count(), 1, 'Native news filtering still works');
            await filter.fill('');
            await filter.press('Backspace');
            await page.waitForTimeout(200);
            if (site === 'cbcrg') {
              await page.goto(origins + base + 'news/#2025-02-01-new-lab-new-continent-and-new-beginnings');
              await page.waitForURL('**/news/#2025-02-01-new-lab-new-continent-and-new-beginnings');
              await page.waitForFunction(() => document.getElementById('2025-02-01-new-lab-new-continent-and-new-beginnings').offsetHeight > 0);
              assert.ok(await page.locator('[id="2025-02-01-new-lab-new-continent-and-new-beginnings"]').isVisible(), 'Canonical news anchor reveals its entry on a later page');
            }
          }
          if (section === 'people/') {
            assert.equal(await page.locator('.person-summary').count(), 0, 'Directory biographies are omitted');
            const memberCards = page.locator('.person-card');
            for (const member of await memberCards.all()) {
              const actions = member.locator('.person-links');
              if (await actions.count()) {
                const role = await member.locator('.person-position').boundingBox();
                const actionRow = await actions.boundingBox();
                assert.ok(actionRow.y >= role.y + role.height, 'External actions sit below the member title');
                for (const icon of await actions.locator('.profile-link').all()) {
                  assert.ok(await icon.getAttribute('title'));
                  assert.equal(await icon.getAttribute('aria-label'), await icon.getAttribute('title'));
                  assert.ok(['Google Scholar', 'ORCID', 'GitHub', 'Email'].includes(await icon.getAttribute('title')));
                  const button = await icon.boundingBox();
                  assert.ok(Math.abs(button.width - 32) < 1 && Math.abs(button.height - 32) < 1, 'Directory actions use compact 32px boxes');
                }
              }
            }
            const directoryPi = memberCards.filter({has: page.getByRole('link', {name: site === 'generic' ? 'Alex Researcher' : 'Aziz Khan', exact: true})});
            assert.equal(await directoryPi.locator('.person-links .profile-link').count(), 4);

            const columns = await page.locator('.people-grid').first().evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length);
            assert.equal(columns, device === 'desktop' ? 2 : 1, 'People directory must adapt its columns to the viewport');
            const alumni = page.locator('.alumni-entry');
            assert.equal(await page.locator('.person-education').count(), 0, 'Education is hidden in the directory by default');
            assert.equal(await alumni.count(), 2);
            const memberNameSize = await memberCards.locator('h3').first().evaluate(el => parseFloat(getComputedStyle(el).fontSize));
            assert.ok(await alumni.locator('h3').evaluateAll((headings, size) => headings.every(el => parseFloat(getComputedStyle(el).fontSize) < size), memberNameSize), 'Alumni names are smaller than current-member names');
            assert.equal(await alumni.locator('.person-avatar').count(), 2, 'Alumni portraits or initials are visible by default');
            assert.equal(await alumni.locator('.person-links').count(), 0);
            assert.equal(await alumni.locator('.person-info h3 a:not(.anchorjs-link)').count(), 0, 'Alumni names do not link to profiles by default');
            assert.equal(await alumni.locator('.person-summary').count(), 0);
            assert.ok(await alumni.evaluateAll(entries => entries.every(el => getComputedStyle(el).display === 'grid')));
            assert.equal(await page.locator('.alumni-list').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), device === 'desktop' ? 2 : 1);
            if (site === 'generic') {
              assert.equal(await page.locator('.people-grid .person-initials').count(), 9, 'Current members without portraits retain initials');
              assert.equal(await alumni.locator('.person-education').count(), 0);
              assert.equal(await alumni.locator('.alumni-years').count(), 2);
              for (const line of await alumni.locator('.alumni-destination').all()) assert.ok((await line.innerText()).startsWith('Now:'));
            } else {
              assert.equal(await page.locator('.people-grid .person-avatar').count(), await memberCards.count(), 'Every current member keeps a portrait or initials');
              assert.equal(await page.locator('.person-avatar img').first().evaluate(el => getComputedStyle(el).borderRadius), '50%');
              assert.ok(await page.locator('.person-avatar img').evaluateAll(images => images.every(img => getComputedStyle(img).filter === 'grayscale(1)')), 'Current-member headshots retain the configured filter');
            }
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-people.png`, fullPage: true});
          }
          if (section === 'software/') {
            assert.ok(await page.getByRole('searchbox', {name: 'Search resources'}).isVisible());
            const resourceList = page.locator('[data-resources]');
            const listButton = page.getByRole('button', {name: 'List', exact: true});
            const gridButton = page.getByRole('button', {name: 'Grid', exact: true});
            assert.equal(await resourceList.getAttribute('data-view'), 'grid');
            assert.equal(await gridButton.getAttribute('aria-pressed'), 'true');
            const total = await page.locator('[data-resources] .resource').count();
            await page.locator('#resource-search').fill('no-resource-matches-this');
            assert.equal(await page.locator('[data-resources] .resource:visible').count(), 0);
            assert.ok(await page.locator('#resource-empty').isVisible());
            await listButton.click();
            assert.equal(await resourceList.getAttribute('data-view'), 'list');
            assert.equal(await page.locator('[data-resources] .resource:visible').count(), 0, 'Switching views preserves active filters');
            assert.ok(await page.locator('#resource-empty').isVisible());
            await page.locator('#resource-search').fill('');
            assert.equal(await page.locator('[data-resources] .resource:visible').count(), total);
            if (site === 'cbcrg') {
              await page.locator('#resource-type').selectOption('database');
              const matches = await page.locator('[data-resources] .resource[data-type=database]').count();
              assert.equal(await page.locator('[data-resources] .resource:visible').count(), matches);
              await page.locator('#resource-search').fill('jaspar');
              assert.ok(await page.locator('[data-resources] .resource:visible').count() > 0);
              await page.locator('#resource-search').fill('');
              await page.locator('#resource-type').selectOption('');
            }
            assert.ok(await resourceList.evaluate(el => {
              const box = el.getBoundingClientRect();
              const cards = [...el.querySelectorAll('.resource')].map(card => card.getBoundingClientRect());
              return cards.every((card, i) => Math.abs(card.width - box.width) < 1 && (!i || card.top >= cards[i - 1].bottom));
            }), 'List view has one full-width resource per row');
            assert.equal(await listButton.getAttribute('aria-pressed'), 'true');
            const listAxe = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
            assert.deepEqual(listAxe.violations, [], 'List view accessibility');
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-resources-list.png`, fullPage: true});
            await page.reload();
            assert.equal(await resourceList.getAttribute('data-view'), 'list', 'View preference survives reload');
            await gridButton.focus();
            await page.keyboard.press('Space');
            assert.equal(await resourceList.getAttribute('data-view'), 'grid', 'Keyboard can restore grid view');
            assert.equal(await gridButton.getAttribute('aria-pressed'), 'true');
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-resources.png`, fullPage: true});
            assert.equal(await page.locator('.lab-card').evaluateAll(cards => cards.every(card => {
              const style = getComputedStyle(card);
              return style.borderTopWidth === style.borderBottomWidth && style.borderTopColor === style.borderBottomColor;
            })), true, 'Cards have a neutral outline without a colored top stripe');
            const cards = page.locator('.resource');
            await checkResourceActions(cards);
            assert.equal(await cards.locator('.source-link').count(), 0, 'Resource provenance is metadata rather than a visitor-facing action');
            assert.equal(await cards.locator('h2 a:not(.anchorjs-link)').count(), 0, 'Resource names are plain text; actions below carry the links');
            assert.equal(await page.locator('.resource-website').count(), await cards.count(), 'Every resource has an explicit website action');
            assert.equal(await page.locator('.resource-website .bi-globe2').count(), await cards.count());
            if (site === 'cbcrg') {
              assert.equal(await page.locator('.resource-code').count(), 13);
              assert.ok(await page.locator('.resource-code .bi-github').count() > 0);
              assert.equal(await page.locator('#unibind .resource-code .bi-git').count(), 1, 'Non-GitHub repositories use a generic Git icon');
            } else {
              assert.equal(await page.locator('.resource-code').count(), 5, 'Only resources with repositories show code links');
            }
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-resources.png`, fullPage: true});
          }
          if (device === 'desktop' && ['software/', 'people/'].includes(section)) {
            const resources = section === 'software/';
            const grid = page.locator(resources ? '.lab-grid' : '.people-grid').first();
            const itemCount = resources ? await page.locator('.resource').count() : 2;
            for (const width of [1024, 1280, 1366]) {
              await page.setViewportSize({width, height: 1000});
              const columns = await grid.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').filter(track => parseFloat(track) > 0).length);
              const expected = resources ? Math.min(itemCount, 3) : 2;
              assert.equal(columns, expected, `${site} ${width}px ${section}: laptop column count`);
              assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${site} ${width}px ${section}: overflow`);
              if (width === 1280) {
                assert.ok(await page.locator('main').evaluate(el => el.getBoundingClientRect().width > 1000), 'Laptop pages use the wider content area');
                await page.screenshot({path: `${screenshotDir}/${site}-laptop-${resources ? 'resources' : 'people'}.png`});
              }
            }
            await page.setViewportSize(viewport);
          }
          if (section === 'join/') {
            assert.match(await page.locator('h1').innerText(), /^Join/i);
            assert.equal((await context.request.get(origins + base + 'opportunities/')).status(), 404);
            assert.equal((await context.request.get(origins + base + 'pages/opportunities.html')).status(), 404);
          }
          if (section === 'blog/') {
            if (site === 'generic') {
              assert.equal(await page.locator('.blog-post-row').count(), 3);
              assert.ok(await page.locator('#blog-search').isVisible());
              await page.locator('#blog-category').selectOption('methods');
              assert.equal(await page.locator('.blog-post-row:visible').count(), 2);
              await page.locator('#blog-tag').selectOption('notebooks');
              assert.equal(await page.locator('.blog-post-row:visible').count(), 1);
              await page.locator('#blog-search').fill('no-matching-post');
              assert.ok(await page.locator('#blog-empty').isVisible());
              await page.locator('#blog-search').fill('');
              await page.locator('#blog-category').selectOption('');
              await page.locator('#blog-tag').selectOption('');
            } else {
              assert.ok(await page.locator('.blog-post-row').count() > 0);
              assert.ok(await page.locator('#blog-search').isVisible());
              assert.ok(await page.getByRole('link', {name: 'Introducing ResearchLabFolio', exact: true}).isVisible());
            }
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-blog.png`, fullPage: true});
            if (site === 'generic') {
              await page.locator('.blog-post-row h2 a').first().click();
              await page.locator('.blog-authors').waitFor({state: 'visible'});
              assert.ok(new URL(page.url()).pathname.startsWith(base + 'blog/') && page.url().endsWith('.html'));
              assert.equal(await page.locator('.blog-authors').count(), 1);
              assert.ok(await page.locator('#quarto-citation').isVisible());
              assert.equal(await page.locator('.blog-citation-links a[download]').count(), 2);
              assert.ok(await page.locator('meta[name="citation_title"]').count());
              assert.deepEqual(await page.locator('img').evaluateAll(images => images.filter(img => img.complete && img.naturalWidth === 0).map(img => img.src)), []);
              await page.locator('.blog-back a').click();
              await page.waitForURL('**/blog/');
            }
          }
          if (section === profilePath) {
            if (site === 'generic') {
              assert.equal(await page.locator('.profile-publications').count(), 0, 'Demo reading list is not attributed to fictional members');
              assert.equal(await page.locator('.profile-blog .blog-post-row').count(), 2);
              assert.equal(await page.locator('.profile-teaching .profile-course-list li').count(), 1);
            } else {
              assert.equal(await page.locator('.profile-publications .paper').count(), 5);
              const allPapers = new URL(await page.locator('.profile-view-all a').getAttribute('href'), page.url());
              assert.ok(allPapers.pathname.endsWith('/publications/'));
              assert.equal(allPapers.searchParams.get('member'), 'aziz-khan');
              assert.equal(await page.locator('.profile-publications #work-f32ba2e7b2e6bf90').count(), 1, 'Verified DCIS paper appears once on the PI profile');
              assert.equal(await page.locator('.profile-blog').count(), 1);
              assert.ok(await page.locator('.profile-blog').getByRole('link', {name: 'Introducing ResearchLabFolio', exact: true}).isVisible());
              assert.equal(await page.locator('.profile-teaching .profile-course-list li').count(), 7);
              assert.equal(await page.getByRole('heading', {name: 'Teaching courses and workshops', exact: true}).count(), 0, 'Courses have one structured source');
            }
            const portrait = page.locator('.profile-portrait');
            const image = portrait.locator(site === 'generic' ? '.person-initials' : 'img');
            assert.equal(await image.evaluate(el => getComputedStyle(el).borderRadius), '50%');
            const portraitBounds = await portrait.boundingBox();
            const headingBounds = await page.locator('.profile-heading').boundingBox();
            assert.ok(portraitBounds.x + portraitBounds.width <= headingBounds.x, 'Portrait remains left of the name and role');
            assert.equal(await page.locator('h1').count(), 1, 'Profile has one name heading');
            assert.ok(await page.locator('.profile-role').isVisible());
            for (const icon of await page.locator('.profile-heading .profile-link').all()) {
              const bounds = await icon.boundingBox();
              assert.ok(Math.abs(bounds.width - 32) < 1 && Math.abs(bounds.height - 32) < 1, 'Profile actions match the 32px directory actions');
              const glyph = icon.locator('i, svg');
              assert.ok(await glyph.evaluate(el => el.tagName.toLowerCase() === 'svg'
                ? getComputedStyle(el).width === '18px' && getComputedStyle(el).height === '18px'
                : getComputedStyle(el).fontSize === getComputedStyle(document.documentElement).fontSize), 'Profile glyphs match directory sizing');
            }
            if (site === 'cbcrg') {
              const icons = page.locator('.profile-heading .profile-link');
              assert.equal(await icons.count(), 6, 'Profile destinations appear once under the name/role');
              for (const icon of await icons.all()) {
                assert.ok(await icon.getAttribute('title'), 'Icons retain native hover labels');
                assert.equal(await icon.getAttribute('aria-label'), await icon.getAttribute('title'));
                assert.equal(await icon.locator('i, svg').count(), 1);
              }
              const iconBounds = await icons.first().boundingBox();
              const roleBounds = await page.locator('.profile-role').boundingBox();
              assert.ok(iconBounds.y >= roleBounds.y + roleBounds.height, 'Icon row sits below the name and role');
              await icons.first().focus();
              assert.equal(await icons.first().evaluate(el => document.activeElement === el && getComputedStyle(el).outlineStyle !== 'none'), true, 'Icon links have visible keyboard focus');
            } else {
              assert.equal(await page.locator('.profile-heading .profile-link').count(), 5, 'Demo PI profile shows GitHub, Scholar, ORCID, website and email actions');
            }
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-profile.png`, fullPage: true});
          }
          if (section === 'teaching/') {
            assert.equal(await page.locator('.teaching-course').count(), site === 'generic' ? 2 : 7);
            if (site === 'generic') {
              assert.equal(await page.locator('#reproducible-research .course-offerings li').count(), 2);
              assert.equal(await page.locator('#reproducible-research .course-term').first().innerText(), 'Fall 2026');
              assert.equal(await page.locator('#reproducible-research .course-instructors a').count(), 2);
            } else {
              assert.equal(await page.locator('.course-offerings li').count(), 8);
              assert.equal(await page.locator('#bios259-reproducible-science .course-offerings li').count(), 2);
              assert.equal(await page.locator('#res799-research-methods .course-links a').count(), 0);
            }
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-teaching.png`, fullPage: true});
          }
          const axe = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
          results.push({site, device, page: section || 'index.html', violations: axe.violations.map(v => ({id: v.id, impact: v.impact, description: v.description, nodes: v.nodes.map(n => n.target)}))});
          fs.writeFileSync(`.scratch/logs/browser-progress${resultSuffix}.json`, JSON.stringify({results, consoleErrors, networkErrors}, null, 2));
          if (!section || section.includes('people') || section.includes('publications')) {
            await page.screenshot({path: `${screenshotDir}/${site}-${device}-${section ? section.replace(/\/$/, '').replaceAll('/', '-') : 'home'}.png`, fullPage: true});
          }
        }
        await page.goto(origins + base + 'index.html');
        await page.keyboard.press('Tab');
        const focused = await page.evaluate(() => ({tag: document.activeElement.tagName, outline: getComputedStyle(document.activeElement).outlineStyle}));
        assert.notEqual(focused.tag, 'BODY');
        if (device === 'mobile') {
          const button = page.locator('.navbar-toggler');
          await button.focus();
          await page.keyboard.press('Enter');
          await page.waitForTimeout(350);
          assert.equal(await button.getAttribute('aria-expanded'), 'true');
          await page.getByRole('link', {name:'People', exact: true}).click();
          await page.waitForURL('**/people/');
        }
        if (site === 'cbcrg') {
          await page.goto(origins + base + 'publications/');
          assert.equal(await page.locator('[data-publications] article:visible').count(), cbcrgCitations.length);
          const featured = page.getByRole('button', {name: 'Featured only'});
          await featured.focus();
          await page.keyboard.press('Space');
          assert.equal(await featured.getAttribute('aria-pressed'), 'true');
          assert.equal(await page.locator('[data-publications] article:visible').count(), await page.locator('[data-publications] article[data-featured="true"]').count());
          await page.keyboard.press('Space');
          assert.equal(await featured.getAttribute('aria-pressed'), 'false');
          assert.ok(await page.locator('#paper-search').isVisible(), 'Expanded filters are immediately usable');
          await page.locator('#paper-search').fill('JASPAR');
          assert.equal(await page.locator('[data-publications] article:visible').count(), cbcrgCitations.filter(p => p.title.toLowerCase().includes('jaspar')).length);
          await page.locator('#paper-search').fill('no-matching-paper');
          assert.equal(await page.locator('[data-publications] article:visible').count(), 0);
          assert.equal(await page.locator('#paper-empty').isVisible(), true);
          await page.locator('#paper-search').fill('');
          await page.locator('#paper-type').selectOption('preprint');
          assert.equal(await page.locator('[data-publications] article:visible').count(), cbcrgCitations.filter(p => p.type === 'document').length);
          await featured.click();
          assert.equal(await page.locator('[data-publications] article:visible').count(), 0, 'Featured and type filters combine');
          await featured.click();
          await page.locator('#paper-type').selectOption('');
          await page.locator('#paper-year').selectOption('2025');
          assert.equal(await page.locator('[data-publications] article:visible').count(), cbcrgCitations.filter(p => p.issued['date-parts'][0][0] === 2025).length);
          await page.locator('#paper-year').selectOption('');
          const citations = await page.evaluate(async () => (await fetch('../assets/publications.json')).json());
          const consortium = citations.find(p => p.author.length > 12);
          await page.locator('#paper-search').fill(consortium.author[8].literal);
          assert.equal(await page.locator(`[data-publications] #${consortium.id}`).isVisible(), true, 'Search includes authors omitted from the preview');
          await page.goto(origins + base + 'people/');
          await page.waitForURL('**/people/');
        }
        // Inline directions have canonical anchors without compatibility pages.
        const direction = site === 'cbcrg' ? 'ai-regulatory-genomics' : 'discovery';
        await page.goto(origins + base + 'research/#' + direction);
        assert.ok(await page.locator('#' + direction).isVisible(), 'Research anchor reveals its inline row');
        assert.equal((await context.request.get(origins + base + 'pages/people.html')).status(), 404);
        assert.equal((await context.request.get(origins + base + 'content/research/' + direction + '.html')).status(), 404);
        // Native Quarto search remains usable with all external requests blocked.
        await page.goto(origins + base + 'index.html');
        await page.locator('#quarto-search button').click();
        const search = page.locator('.aa-Input');
        await search.fill(site === 'cbcrg' ? 'Khan' : 'Alex');
        await page.waitForTimeout(700);
        assert.ok(await page.locator('.aa-Item').count() > 0, 'Native search returned no results');
        await context.close();
      }
    }
    const selection = await browser.newContext({colorScheme});
    await selection.route('**/*', route => route.request().url().startsWith(origins)
      ? route.continue() : route.fulfill({contentType: 'application/javascript', body: ''}));
    // Force two shuffle outcomes to test refresh behavior without flaky probability assertions.
    await selection.addInitScript(() => {
      const seed = Number(sessionStorage.getItem('labfolio-qa-seed') || 0);
      Math.random = () => seed;
    });
    const sample = await selection.newPage();
    await sample.goto(origins + '/examples/cbcrg/_site/index.html');
    const firstSelection = await sample.locator('.home-person:visible').evaluateAll(items => items.map(item => item.getAttribute('href')));
    assert.equal(firstSelection.length, 3);
    assert.equal(new Set(firstSelection).size, 3, 'Member selection has no duplicates');
    await sample.evaluate(() => sessionStorage.setItem('labfolio-qa-seed', '0.999999'));
    await sample.reload();
    const nextSelection = await sample.locator('.home-person:visible').evaluateAll(items => items.map(item => item.getAttribute('href')));
    assert.equal(nextSelection.length, 3);
    assert.notDeepEqual([...firstSelection].sort(), [...nextSelection].sort(), 'Refresh can select a different group from the full current team');
    await selection.close();
    const disabled = await browser.newContext({javaScriptEnabled:false});
    const fallback = await disabled.newPage();
    await fallback.goto(origins + '/examples/cbcrg/_site/publications/');
    assert.equal(await fallback.locator('[data-publications] article').count(), cbcrgCitations.length);
    assert.equal(await fallback.locator('#paper-featured').isVisible(), false, 'Inactive JavaScript control stays hidden');
    await fallback.locator('.paper-authors summary').first().click();
    assert.notEqual(await fallback.locator('details.paper-authors').first().getAttribute('open'), null, 'Full author lists work without JavaScript');
    await fallback.goto(origins + '/examples/cbcrg/_site/software/');
    assert.equal(await fallback.locator('[data-resources] .resource:visible').count(), 13);
    assert.equal(await fallback.locator('.resource-filters').isVisible(), false);
    assert.equal(await fallback.locator('.resource-view-switch').isVisible(), false);
    assert.equal(await fallback.locator('[data-resources]').getAttribute('data-view'), 'grid');
    await fallback.goto(origins + '/examples/cbcrg/_site/index.html');
    const staticPeople = await fallback.locator('.home-person:visible').allTextContents();
    assert.equal(staticPeople.length, 3, 'Three member previews remain usable without JavaScript');
    await fallback.reload();
    assert.deepEqual(await fallback.locator('.home-person:visible').allTextContents(), staticPeople, 'No-JavaScript fallback remains stable');
    await disabled.close();
    const summary = {pages:results.length, violations:results.reduce((n,p) => n+p.violations.length,0), consoleErrors, networkErrors, optionalBadgeRequests: optionalBadgeRequests.length, results};
    fs.writeFileSync(`.scratch/logs/browser-results${resultSuffix}.json`, JSON.stringify(summary, null, 2));
    console.log(JSON.stringify({pages:summary.pages, violations:summary.violations, consoleErrors, networkErrors, optionalBadgeRequests:summary.optionalBadgeRequests}, null, 2));
    assert.equal(summary.violations, 0, 'Accessibility violations; inspect browser-results.json');
    assert.deepEqual(consoleErrors, []);
    assert.deepEqual(networkErrors, []);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
