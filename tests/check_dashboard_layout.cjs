// Real UI -> Flask -> Docker -> DNS -> HTTP. Failure interception is isolated below.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const out = process.env.LAYOUT_ARTIFACTS || path.join(require('node:os').tmpdir(), 'dnssec-live-review');
fs.mkdirSync(out, {recursive:true});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function availablePort() {
  const socket = net.createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  return port;
}
(async () => {
  let browser, server, base, serverLogs = '', failure;
  const phases = [];
  try {
    const port = await availablePort(); base = `http://127.0.0.1:${port}`;
    const python = process.env.LAB_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    server = spawn(python, ['dashboard/app.py', '--port', String(port)], {cwd:root, windowsHide:true, stdio:['ignore','pipe','pipe']});
    server.stdout.on('data', data => {serverLogs += data;});
    server.stderr.on('data', data => {serverLogs += data;});
    server.on('error', error => {serverLogs += error.message;});
    let started = false;
    for (let i=0; i<60; i++) {
      try { const r = await fetch(base); if (r.ok) {started=true;break;} } catch {}
      if (server.exitCode !== null) break;
      await delay(250);
    }
    assert.ok(started, 'API server failed to start: ' + serverLogs);
    const healthResponse = await fetch(base + '/api/health');
    assert.equal(healthResponse.status,200, 'Docker lab must be healthy before live UI tests');
    browser = await chromium.launch({headless:true, executablePath:process.env.EDGE_PATH || path.join(process.env['ProgramFiles(x86)'] || 'C:/Program Files (x86)', 'Microsoft/Edge/Application/msedge.exe')});
    const page = await browser.newPage({viewport:{width:1366,height:768}});
    page.setDefaultTimeout(20000);
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => requests.push(request.url()));
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#run').disabled);
    assert.equal(await page.locator('iframe').count(),0);
    assert.equal(await page.evaluate(() => typeof window.MockData),'undefined');
    // Motion must be decorative: exploring scenarios never mutates the lab.
    let motionPosts=0;
    page.on('request', request=>{if(request.method()==='POST')motionPosts++;});
    await page.waitForFunction(()=>document.querySelector('#intro-title').classList.contains('seen'));
    await page.waitForTimeout(1000);
    await page.screenshot({path:path.join(out,'dashboard-motion-hero.png')});
    await page.locator('#scenarios').evaluate(el=>el.scrollIntoView({behavior:'instant',block:'start'}));
    await page.locator('[data-preview-mode=attack]').hover();
    await page.waitForFunction(()=>document.querySelector('.scenario-visual').dataset.preview==='attack');
    assert.equal(await page.locator('#preview-plain').textContent(),'.90');
    assert.equal(await page.locator('#preview-secure').textContent(),'SERVFAIL');
    assert.equal(await page.locator('input[value=baseline]').isChecked(),true);
    await page.locator('[data-preview-mode=recovery]').focus();
    assert.equal(await page.locator('.scenario-visual').getAttribute('data-preview'),'recovery');
    await page.locator('[data-preview-mode=attack]').hover();
    await page.waitForTimeout(650);
    await page.locator('#scenarios').screenshot({path:path.join(out,'dashboard-motion-scenarios.png')});
    assert.equal(motionPosts,0,'hover/focus/scroll did not send POST');
    await page.locator('#motion-toggle').click();
    assert.equal(await page.locator('html').getAttribute('data-motion'),'off');
    await page.reload();
    assert.equal(await page.locator('html').getAttribute('data-motion'),'off');
    await page.locator('#motion-toggle').click();
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.waitForFunction(()=>document.documentElement.dataset.motion==='off');
    assert.equal(await page.locator('#motion-toggle').isDisabled(),true);
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.waitForFunction(()=>document.documentElement.dataset.motion==='on');
    await page.locator('.nav-lab').click();
    await page.waitForFunction(()=>document.querySelector('#lab').getBoundingClientRect().top<160);
    await page.locator('[data-node-note]').nth(2).focus();
    assert.equal(await page.locator('#node-tip').isVisible(),true);
    assert.match(await page.locator('#node-tip').textContent(),/Secure/);
    await page.locator('.nav-lab').focus();
    assert.equal(await page.locator('#node-tip').isHidden(),true);
    await page.waitForFunction(()=>!document.querySelector('#run').disabled);
    const run = async phase => {
      await page.locator(`input[value=${phase}]`).check();
      if (phases.length) assert.equal(await page.locator('iframe').count(),0,'old preview removed on selection change');
      await page.locator('#run').click();
      assert.equal(await page.locator('input[value=attack]').isDisabled(),true);
      assert.equal(await page.locator('#results').getAttribute('aria-busy'),'true');
      if (phase==='baseline') {
        await page.waitForFunction(()=>sessionStorage.getItem('dnssec-active-job'));
        const pendingJob=await page.evaluate(()=>sessionStorage.getItem('dnssec-active-job'));
        const postCount=motionPosts;
        await page.reload();
        await page.waitForFunction(id=>sessionStorage.getItem('dnssec-active-job')===id,pendingJob);
        assert.equal(motionPosts,postCount,'reloading an active job does not POST again');
      }
      await page.waitForFunction(() => {
        try { return JSON.parse(document.querySelector('#json').textContent).source === 'live'; } catch {return false;}
      }, null, {timeout:130000});
      await page.waitForFunction(() => !document.querySelector('#run').disabled, null, {timeout:20000});
      const data = JSON.parse(await page.locator('#json').textContent());
      assert.equal(data.consistent,true);
      assert.match(data.run_id,/^[a-f0-9-]{36}$/);
      assert.equal(data.results.plain.evidence.http_corroborated,true);
      assert.equal(data.evidence.http_access.length, phase === 'attack' ? 1 : 2);
      phases.push({phase,run_id:data.run_id,requests:data.evidence.http_access.length});
      console.log('PASS live UI ' + JSON.stringify(phases.at(-1)));
      return data;
    };
    await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.evaluate(()=>document.fonts.check('800 16px "Nunito"')),true);
    assert.equal(await page.locator('.kawaii-banner').count(),1);
    assert.equal(await page.evaluate(()=>document.fonts.check('400 16px "Be Vietnam Pro"')),true);
    assert.equal(await page.evaluate(()=>document.fonts.check('400 16px "Xanh Mono"')),true);
    await run('baseline');
    await page.frameLocator('#secure-panel iframe').getByRole('heading',{name:'Website hợp lệ',exact:true}).waitFor();
    assert.equal(await page.locator('iframe').count(),2);
    await page.evaluate(()=>{
      window.observedPulses=0;
      new MutationObserver(changes=>changes.forEach(change=>change.addedNodes.forEach(node=>{if(node.nodeName==='circle')window.observedPulses++;}))).observe(document.querySelector('.topology svg'),{childList:true});
    });
    let interruptedPoll=false;
    await page.route('**/api/jobs/*?after=*',route=>{
      if (!interruptedPoll) {interruptedPoll=true;return route.abort();}
      return route.continue();
    });
    const attack = await run('attack');
    assert.equal(interruptedPoll,true,'poll disconnect exercised');
    assert.ok(await page.evaluate(()=>window.observedPulses>0),'real worker events trigger finite pulses');
    await page.unroute('**/api/jobs/*?after=*');
    await page.frameLocator('#plain-panel iframe').getByRole('heading',{name:/website giả lập/i}).waitFor();
    assert.equal(await page.locator('#secure-panel iframe').count(),0);
    assert.equal(attack.results.secure.http.attempted,false);
    assert.equal(attack.results.secure.evidence.no_http_observed,true);
    assert.equal(attack.results.plain.http.connected_ip,'172.30.53.90');
    assert.equal(await page.locator('#plain-panel iframe').getAttribute('sandbox'),'');
    assert.equal(await page.locator('#plain-panel iframe').getAttribute('src'),attack.results.plain.http.preview_url);
    await page.locator('#lab').evaluate(el=>el.scrollIntoView({behavior:'instant',block:'start'}));
    const headingTop = await page.locator('#lab-title').evaluate(el=>el.getBoundingClientRect().top);
    const headerBottom = await page.locator('.masthead').evaluate(el=>el.getBoundingClientRect().bottom);
    assert.ok(headingTop>=headerBottom,'lab heading is not hidden behind sticky header');
    const panelBottom = await page.locator('#secure-panel').evaluate(el=>el.getBoundingClientRect().bottom);
    await page.screenshot({path:path.join(out,'dashboard-layout-measured.png')});
    assert.ok(panelBottom<=768, `Results exceed 1366x768 viewport: ${panelBottom}`);
    await page.screenshot({path:path.join(out,'dashboard-live-attack.png'),fullPage:true});
    await page.locator('#lab').evaluate(el=>el.scrollIntoView({behavior:'instant',block:'start'}));
    await page.screenshot({path:path.join(out,'dashboard-motion-lab.png')});
    assert.equal(await page.locator('#http-secure').evaluate(el=>el.classList.contains('connected')),false,'SERVFAIL never lights HTTP path');
    assert.equal(await page.locator('#http-plain').getAttribute('class'),'connected');
    const events = await page.locator('#event-timeline li').count();
    assert.match(await page.locator('#event-timeline li summary').first().textContent(),/\d{2}:\d{2}:\d{2}[.,]\d{3}/,'full event timestamp includes hours, minutes, seconds and milliseconds');
    const jobID = await page.evaluate(()=>sessionStorage.getItem('dnssec-last-job'));
    const progress = await (await fetch(base+'/api/jobs/'+jobID)).json();
    assert.equal(progress.status,'completed');
    assert.equal(progress.events.length,events);
    assert.equal(new Set(progress.events.map(e=>e.sequence)).size,events);
    assert.equal(progress.events.some(e=>e.branch==='secure'&&e.kind==='http.connected'),false);
    assert.equal(progress.events.some(e=>e.branch==='plain'&&e.kind==='http.connected'),true);
    const emptyCursor = await (await fetch(base+'/api/jobs/'+jobID+'?after='+progress.cursor)).json();
    assert.deepEqual(emptyCursor.events,[]);
    await page.locator('#secure-panel button').click();
    await page.locator('#proof').click();
    await page.locator('#proof-result:not([hidden])').waitFor();
    const proof = JSON.parse(await page.locator('#proof-json').textContent());
    assert.equal(proof.proof.rrsig_unchanged,true);
    assert.equal(proof.revision,attack.scenario_revision);
    assert.deepEqual(proof.proof.records.authority.answers,['172.30.53.80']);
    assert.deepEqual(proof.proof.records.tamper.answers,['172.30.53.90']);
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#download').click();
    assert.equal((await downloadPromise).suggestedFilename(),attack.run_id+'.json');
    await page.reload();
    await page.waitForFunction(() => !document.querySelector('#restore').disabled);
    assert.equal(await page.locator('#event-timeline li').count(),events,'reload replays once');
    await page.locator('#evidence > summary').click();
    await page.locator('#restore').click();
    await page.waitForFunction(id => {
      try {return JSON.parse(document.querySelector('#json').textContent).run_id === id;} catch {return false;}
    }, attack.run_id);
    await page.frameLocator('#plain-panel iframe').getByRole('heading',{name:/website giả lập/i}).waitFor();
    await page.setViewportSize({width:390,height:844});
    await page.locator('#evidence').evaluate(el=>el.open=false);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(out,'dashboard-live-mobile.png'),fullPage:true});
    await page.locator('#plain-panel iframe').scrollIntoViewIfNeeded();
    await page.frameLocator('#plain-panel iframe').getByRole('heading',{name:/website giả lập/i}).waitFor();
    await page.waitForTimeout(250);
    await page.locator('#lab').screenshot({path:path.join(out,'dashboard-motion-mobile-lab.png'),style:'.masthead,.skip-link{visibility:hidden!important}'});
    await page.locator('#story').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>document.querySelector('#intro-title').classList.contains('seen'));
    await page.waitForTimeout(1000);
    await page.locator('#story').screenshot({path:path.join(out,'dashboard-motion-mobile-hero.png')});
    await page.setViewportSize({width:1366,height:768});
    // An external mode change is real, not intercepted. Poll must invalidate the old preview.
    const changed = await fetch(base+'/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'recovery'})});
    assert.equal(changed.status,200);
    await page.waitForFunction(()=>document.querySelector('#results').classList.contains('stale'), null, {timeout:15000});
    assert.equal(await page.locator('iframe').count(),0);
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.waitForFunction(()=>document.documentElement.dataset.motion==='off');
    await page.evaluate(()=>window.observedPulses=0);
    const recoveredRun=await run('recovery');
    assert.equal(await page.evaluate(()=>window.observedPulses),0,'reduced motion keeps event data with no SVG pulse');
    await page.emulateMedia({reducedMotion:'no-preference'});
    assert.match(await page.locator('#recovery-note').textContent(),new RegExp(attack.run_id));
    assert.match(await page.locator('#recovery-note').textContent(),new RegExp(recoveredRun.run_id));
    assert.equal(await page.locator('#recovery-table tbody tr').count(),4);
    await page.frameLocator('#secure-panel iframe').getByRole('heading',{name:'Website hợp lệ',exact:true}).waitFor();
    // From here only: explicit intercepted API failures exercise UI handling, not live acceptance.
    await page.route('**/api/jobs', route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'TEST_UNAVAILABLE',message:'Test: lab unavailable'}})}));
    await page.locator('#run').click();
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('Test: lab unavailable'));
    assert.equal(await page.locator('iframe').count(),0);
    assert.equal(await page.locator('#json').textContent(),'{}');
    await page.waitForTimeout(5500);
    assert.match(await page.locator('#notice').textContent(),/Test: lab unavailable/);
    await page.unroute('**/api/jobs');
    await page.route('**/api/health', route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({source:'live',ready:false,services:{}})}));
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>document.querySelector('#lab-status').textContent==='Lab chưa sẵn sàng');
    assert.equal(await page.locator('#run').isDisabled(),true);
    await page.unroute('**/api/health');
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>!document.querySelector('#run').disabled);
    const offline = await browser.newPage();
    await offline.route('**/api/**', route=>route.abort());
    await offline.goto(base);
    await offline.waitForFunction(()=>document.querySelector('#lab-status').textContent==='Chưa kết nối được lab');
    assert.equal(await offline.locator('#run').isDisabled(),true);
    assert.equal(await offline.locator('iframe').count(),0);
    assert.equal(await offline.evaluate(()=>typeof window.MockData),'undefined');
    await offline.close();
    assert.deepEqual(errors,[]);
    assert.ok(requests.every(url=>url.startsWith(base) || url.startsWith('data:') || url==='about:blank'),requests.join('\n'));
    assert.ok(!requests.some(url=>url.includes('mock-data')));
    console.log(JSON.stringify({result:'PASS',realPhases:phases,panelBottom,checks:['real-job-events','active-job-reload-no-POST','poll-disconnect-reconnect','cursor-dedup','recovery-run-comparison','local-Vietnamese-fonts','scroll-reveal','hover-without-POST','keyboard-preview','motion-preference-persisted','system-reduced-motion','node-focus-tooltip','direct-lab-navigation','same-origin-Flask','no-mock-loader','initial-empty','busy-controls','real-HTTP-preview-sandbox','SERVFAIL-no-HTTP-no-preview','proof-A-RRSIG','download','restore-after-reload-and-proof','external-revision-stale','mobile-no-overflow','API-503-no-fallback','unhealthy-disabled','offline-boot','no-JS-errors','no-external-requests'],screenshots:out},null,2));
  } catch(error) {failure=error;console.error(error);}
  finally {
    if(browser) await browser.close();
    if(base && server && server.exitCode===null) {
      try {
        for(let i=0;i<30;i++) {
          const state = await (await fetch(base+'/api/state')).json();
          if(!state.busy) break;
          await delay(500);
        }
        const recovered = await fetch(base+'/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'recovery'})});
        if(!recovered.ok) throw new Error('Recovery failed: '+recovered.status);
        console.log('Cleanup: restored normal relay mode and flushed both resolvers.');
      } catch(error) {console.error('Cleanup failure:',error.message);failure=failure||error;}
      server.kill();
    }
    if(failure) {console.error(serverLogs.slice(-5000));process.exitCode=1;}
  }
})();
