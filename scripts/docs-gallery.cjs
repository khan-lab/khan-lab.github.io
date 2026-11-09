/* Optional maintainer capture. Dependencies are installed only under .scratch/browser. */
const path=require('path'), fs=require('fs'), crypto=require('crypto');
const {chromium}=require(path.resolve('.scratch/browser/node_modules/playwright'));
const {AxeBuilder}=require(path.resolve('.scratch/browser/node_modules/@axe-core/playwright'));
const assert=require('assert/strict');
(async()=>{
 const origin=process.env.LABFOLIO_DOCS_ORIGIN||'http://127.0.0.1:8766';
 const browser=await chromium.launch({channel:'chrome'}),files=[];
 const temp='.scratch/screenshots/docs-gallery',target='documentation/assets/gallery';
 fs.mkdirSync(temp,{recursive:true});fs.mkdirSync(target,{recursive:true});
 try{for(const palette of ['forest','ocean','plum','terracotta'])for(const colorScheme of ['light','dark']){
  const context=await browser.newContext({viewport:{width:1280,height:1000},colorScheme,reducedMotion:'reduce'});
  await context.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.fulfill({contentType:'application/javascript',body:''}));
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  const response=await page.goto(`${origin}/.scratch/builds/public-demos/gallery-${palette}/source/_site/index.html`);
  assert.equal(response.status(),200);await page.evaluate(()=>document.fonts.ready);
  await page.locator('img').evaluateAll(async images=>{images.forEach(img=>img.loading='eager');await Promise.all(images.map(img=>img.decode()));});
  assert.equal(await page.locator('h1').count(),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.ok(await page.locator('body').evaluate((el,scheme)=>el.classList.contains('quarto-'+scheme),colorScheme));
  const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();assert.deepEqual(axe.violations,[]);assert.deepEqual(errors,[]);
  const name=`${palette}-${colorScheme}.png`;await page.screenshot({path:temp+'/'+name});
  fs.copyFileSync(temp+'/'+name,target+'/'+name);
  files.push({file:name,palette,appearance:colorScheme,sha256:crypto.createHash('sha256').update(fs.readFileSync(target+'/'+name)).digest('hex')});
  await context.close();
 }
 fs.writeFileSync(target+'/provenance.json',JSON.stringify({method:'Local Chrome screenshots of isolated real Quarto builds; external badges unavailable',viewport:{width:1280,height:1000},theme_sha256:crypto.createHash('sha256').update(fs.readFileSync('styles/theme.scss')).digest('hex'),files},null,2)+'\n');
 console.log(JSON.stringify({captures:files.length,accessibilityViolations:0,passed:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
