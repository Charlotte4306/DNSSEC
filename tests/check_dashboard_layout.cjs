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
    const run = async phase => {
      await page.locator(`input[value=${phase}]`).check();
      if (phases.length) assert.equal(await page.locator('iframe').count(),0,'old preview removed on selection change');
      await page.locator('#run').click();
      assert.equal(await page.locator('input[value=attack]').isDisabled(),true);
      assert.equal(await page.locator('#results').getAttribute('aria-busy'),'true');
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
    await run('baseline');
    await page.frameLocator('#secure-panel iframe').getByRole('heading',{name:'Website hợp lệ',exact:true}).waitFor();
    assert.equal(await page.locator('iframe').count(),2);
    const attack = await run('attack');
    await page.frameLocator('#plain-panel iframe').getByRole('heading',{name:/website giả lập/i}).waitFor();
    assert.equal(await page.locator('#secure-panel iframe').count(),0);
    assert.equal(attack.results.secure.http.attempted,false);
    assert.equal(attack.results.secure.evidence.no_http_observed,true);
    assert.equal(attack.results.plain.http.connected_ip,'172.30.53.90');
    assert.equal(await page.locator('#plain-panel iframe').getAttribute('sandbox'),'');
    assert.equal(await page.locator('#plain-panel iframe').getAttribute('src'),attack.results.plain.http.preview_url);
    const panelBottom = await page.locator('#secure-panel').evaluate(el=>el.getBoundingClientRect().bottom);
    assert.ok(panelBottom<=768, `Results exceed 1366x768 viewport: ${panelBottom}`);
    await page.screenshot({path:path.join(out,'dashboard-live-attack.png'),fullPage:true});
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
    await page.locator('#evidence summary').click();
    await page.locator('#restore').click();
    await page.waitForFunction(id => {
      try {return JSON.parse(document.querySelector('#json').textContent).run_id === id;} catch {return false;}
    }, attack.run_id);
    await page.frameLocator('#plain-panel iframe').getByRole('heading',{name:/website giả lập/i}).waitFor();
    await page.setViewportSize({width:390,height:844});
    await page.locator('#evidence').evaluate(el=>el.open=false);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(out,'dashboard-live-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1366,height:768});
    // An external mode change is real, not intercepted. Poll must invalidate the old preview.
    const changed = await fetch(base+'/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'recovery'})});
    assert.equal(changed.status,200);
    await page.waitForFunction(()=>document.querySelector('#results').classList.contains('stale'), null, {timeout:15000});
    assert.equal(await page.locator('iframe').count(),0);
    await run('recovery');
    await page.frameLocator('#secure-panel iframe').getByRole('heading',{name:'Website hợp lệ',exact:true}).waitFor();
    // From here only: explicit intercepted API failures exercise UI handling, not live acceptance.
    await page.route('**/api/run', route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'TEST_UNAVAILABLE',message:'Test: lab unavailable'}})}));
    await page.locator('#run').click();
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('Test: lab unavailable'));
    assert.equal(await page.locator('iframe').count(),0);
    assert.equal(await page.locator('#json').textContent(),'{}');
    await page.waitForTimeout(5500);
    assert.match(await page.locator('#notice').textContent(),/Test: lab unavailable/);
    await page.unroute('**/api/run');
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
    console.log(JSON.stringify({result:'PASS',realPhases:phases,panelBottom,checks:['same-origin-Flask','no-mock-loader','initial-empty','busy-controls','real-HTTP-preview-sandbox','SERVFAIL-no-HTTP-no-preview','proof-A-RRSIG','download','restore-after-reload-and-proof','external-revision-stale','mobile-no-overflow','API-503-no-fallback','unhealthy-disabled','offline-boot','no-JS-errors','no-external-requests'],screenshots:out},null,2));
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
