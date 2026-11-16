const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');const base=process.env.LAB_URL||'http://127.0.0.1:18766';
const out=process.env.LAYOUT_ARTIFACTS||path.join(require('node:os').tmpdir(),'dnssec-terminal');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({channel:'msedge'});try{
  const old=execFileSync('git',['-c','safe.directory='+root.replaceAll('\\','/'),'show','HEAD:dashboard/templates/index.html'],{cwd:root,encoding:'utf8'});
  const current=fs.readFileSync(path.join(root,'dashboard/templates/index.html'),'utf8');
  const contents=s=>s.match(/<main\b[^>]*>([\s\S]*?)<\/main>/)[1].replaceAll('\r\n','\n');
  assert.equal(contents(current),contents(old),'all previous overview contents must remain identical');
  const page=await browser.newPage({viewport:{width:1366,height:768}});page.setDefaultTimeout(30000);
  const errors=[];let posts=0;page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts++;});
  await page.goto(base);await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  assert(await page.locator('#story').isVisible());assert.equal(await page.locator('#results-view').count(),0);
  await page.screenshot({path:path.join(out,'overview-original.png')});
  await page.locator('.terminal-nav').click();assert(await page.locator('#overview-view').isHidden());assert(await page.locator('#terminal-view').isVisible());assert.equal(posts,0);
  async function command(text){const count=await page.locator('.terminal-entry').count();await page.locator('#terminal-input').fill(text);await page.locator('#terminal-input').press('Enter');await page.waitForFunction(n=>document.querySelectorAll('.terminal-entry').length===n,count+1);await page.waitForFunction(()=>!document.querySelector('#terminal-input').readOnly);return page.locator('.terminal-entry').last().textContent();}
  assert.match(await command('help'),/\+cdflag/);assert.equal(posts,0,'help is local');
  assert.match(await command('dig @authority demo.test DNSKEY +dnssec'),/DNSKEY/);
  assert.match(await command('dig @secure student-17.demo.test AAAA +dnssec +tcp'),/status: NXDOMAIN/);
  const count=posts;await page.locator('#terminal-input').press('ArrowUp');assert.equal(await page.locator('#terminal-input').inputValue(),'dig @secure student-17.demo.test AAAA +dnssec +tcp');await page.locator('#terminal-input').press('ArrowDown');assert.equal(await page.locator('#terminal-input').inputValue(),'');assert.equal(posts,count);
  assert.match(await command('logs secure --tail 3'),/secure-/);
  assert.match(await command('dig @8.8.8.8 demo.test A'),/Resolver phải/);
  await page.screenshot({path:path.join(out,'terminal-typed-desktop.png')});
  await page.locator('.terminal-heading a').click();await page.waitForFunction(()=>document.documentElement.dataset.screen==='overview');assert(await page.locator('#terminal-view').isHidden());assert(await page.locator('#lab').isVisible());
  const run=async(action)=>{
    await page.locator(`input[value=${action}]`).check();await page.locator('#run').click();
    await page.waitForFunction(()=>{try{return JSON.parse(document.querySelector('#json').textContent).source==='live';}catch{return false;}},null,{timeout:130000});
    await page.waitForFunction(()=>!document.querySelector('#run').disabled);
    return JSON.parse(await page.locator('#json').textContent());
  };
  const attack=await run('attack');assert.equal(attack.results.secure.dns.rcode,'SERVFAIL');assert.equal(attack.results.secure.http.attempted,false);assert.equal(attack.results.plain.http.connected_ip,'172.30.53.90');
  assert(await page.locator('#results').isVisible());assert(await page.locator('#lab').isVisible());
  await page.locator('.terminal-nav').click();assert.match(await command('dig @secure www.demo.test A +dnssec'),/status: SERVFAIL/);
  assert.match(await command('dig @plain www.demo.test A +short'),/172\.30\.53\.90/);
  assert.equal(JSON.parse(await page.locator('#json').textContent()).run_id,attack.run_id);
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#terminal-submit').disabled);assert(await page.locator('#terminal-view').isVisible());
  await command('help');await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'terminal mobile overflow');await page.screenshot({path:path.join(out,'terminal-mobile.png'),fullPage:true});
  await page.locator('.terminal-heading a').click();await page.waitForFunction(()=>document.documentElement.dataset.screen==='overview');assert(await page.locator('#terminal-view').isHidden());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overview mobile overflow');
  await page.setViewportSize({width:1366,height:768});const recovery=await run('recovery');assert.equal(recovery.results.secure.dns.ad,true);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'PASS',overview:'original markup preserved',attack:attack.run_id,recovery:recovery.run_id,screenshots:out}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});


