/* Optional public-portal QA; browser dependencies live under .scratch/browser. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(path.resolve('.scratch/browser/node_modules/playwright'));
const {AxeBuilder}=require(path.resolve('.scratch/browser/node_modules/@axe-core/playwright'));
(async()=>{
 const origin=process.env.LABFOLIO_DOCS_ORIGIN||'http://127.0.0.1:8767';
 const base=origin+'/researchlabfolio/',root='_site-docs';
 const widths=(process.env.LABFOLIO_DOCS_WIDTHS||'1280,390,320').split(',').map(Number);
 assert.ok(widths.length&&widths.every(width=>[1280,390,320].includes(width)));
 const browser=await chromium.launch({channel:'chrome'}),results=[],network=[],errors=[];
 const files=fs.readdirSync(root,{recursive:true}).filter(p=>p.endsWith('.html')&&!p.startsWith('demo'+path.sep)&&!p.startsWith('examples'+path.sep));
 try{for(const colorScheme of ['light','dark'])for(const width of widths){
  const context=await browser.newContext({viewport:{width,height:1000},colorScheme,reducedMotion:'reduce'});
  await context.route('**/*',r=>{
   if(r.request().url().startsWith(origin))return r.continue();
   if(r.request().url()==='https://embed.altmetric.com/assets/embed.js')return r.fulfill({contentType:'application/javascript',body:''});
   network.push(r.request().url());return r.abort();
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  page.on('response',r=>{if(r.status()>=400)network.push(r.status()+' '+r.url());});
  // Full guide coverage on desktop; representative responsive/reference pages on mobile.
  const targets=width===1280?files:['index.html','gallery.html','getting-started/fork.html','getting-started/cli.html','guides/migration.html','guides/publishing.html','reference/schema.html','reference/commands.html'];
  for(const file of targets){
   assert.equal((await page.goto(base+file.replaceAll(path.sep,'/'))).status(),200);
   await page.evaluate(()=>document.fonts.ready);
   assert.equal(await page.locator('h1').count(),1);assert.equal(await page.locator('main').count(),1);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'No overflow: '+file+' '+width);
   if(file==='gallery.html'){
    assert.equal(await page.locator('.docs-card img').count(),8);
    assert.ok(await page.locator('.docs-card img').evaluateAll(images=>images.every(img=>!!img.alt)));
    await page.getByRole('tab',{name:'Dark',exact:true}).click();
    assert.equal(await page.locator('.tab-pane.active .docs-card img').count(),4);
    await page.getByRole('tab',{name:'Light',exact:true}).click();
   }
   if(file==='index.html'){
    await page.locator('main').getByRole('link',{name:'Start with a GitHub fork',exact:true}).click();await page.waitForURL('**/getting-started/fork.html');
    await page.goto(base+file);
   }
   if(file==='reference/commands.html'){
    const block=page.locator('pre.text').first();
    if(await block.evaluate(el=>el.scrollWidth>el.clientWidth+1)){
     await block.focus();await page.keyboard.press('ArrowRight');
     await page.waitForFunction(el=>el.scrollLeft>0,await block.elementHandle(),{timeout:2000});
     await block.evaluate(el=>el.blur());
    }
   }
   const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
   assert.deepEqual(axe.violations,[],file+' '+width+' '+colorScheme);
   results.push({file,width,colorScheme,passed:true});
   fs.writeFileSync('.scratch/logs/docs-browser-progress.json',JSON.stringify({results,network,errors},null,2));
   if([1280,390].includes(width)&&['index.html','gallery.html','getting-started/fork.html'].includes(file))await page.screenshot({path:`.scratch/screenshots/docs-${colorScheme}-${width}-${file.replace('.html','.png')}`,fullPage:true});
  }
  await page.goto(base+'index.html');await page.locator('#quarto-search button').click();
  const search=page.locator('.aa-Input');await search.fill('alumni');await page.waitForSelector('.aa-Item');
  assert.ok(await page.locator('.aa-Item').count()>0,'Native search returns indexed references');await page.keyboard.press('Escape');
  for(const [file,selector,count] of [['demo/index.html','h1',1],['examples/cbcrg/people/aziz-khan.html','.profile-publications .paper',5]]){
   await page.goto(base+file);assert.equal(await page.locator(selector).count(),count);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  }
  await context.close();
 }
 assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
 fs.writeFileSync('.scratch/logs/docs-browser-results.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify({pages:results.length,searchChecks:widths.length*2,nestedDemoChecks:widths.length*4,violations:0,networkErrors:network,consoleErrors:errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
