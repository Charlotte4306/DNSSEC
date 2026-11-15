// Focused browser regression: inferred relay/BIND hops must never become live evidence.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = process.env.DNSSEC_REPO || path.resolve(__dirname, '..');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    for (const folder of ['dashboard', 'ui_preview']) {
      const page = await browser.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.clock.install();
      const htmlPath = folder === 'dashboard' ? 'dashboard/templates/index.html' : 'ui_preview/index.html';
      const html = fs.readFileSync(path.join(root, htmlPath), 'utf8')
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*>/gi, '');
      await page.setContent(html);
      await page.addStyleTag({content: fs.readFileSync(path.join(root, folder, 'static/css/replay.css'), 'utf8')});
      await page.addScriptTag({content: fs.readFileSync(path.join(root, folder, 'static/js/replay.js'), 'utf8')});
      await page.evaluate(() => {
        window.seenWires = [];
        new MutationObserver(records => {
          for (const {target} of records) if (target.classList.contains('is-live')) window.seenWires.push(target.id);
        }).observe(document.querySelector('.rp-wires'), {subtree:true, attributes:true, attributeFilter:['class']});
      });
      let sequence = 0;
      async function event(kind, data, branch) {
        await page.evaluate(e => window.dispatchEvent(new CustomEvent('dnssec:event', {detail:e})),
          {kind, data, branch, sequence: ++sequence, run_id:'relay-regression'});
        await page.clock.runFor(3000);
      }
      assert.match(await page.locator('.replay-note').textContent(), /chưa có telemetry từng hop/);
      await event('mode.changed', {attack:true});
      assert.equal(await page.locator('#rp-attacker').evaluate(n => getComputedStyle(n).animationIterationCount), '2');
      await event('dns.started', {name:'www.demo.test'}, 'plain');
      await event('dns.response', {rcode:'NOERROR', ad:false, answers:['172.30.53.90']}, 'plain');
      assert.match(await page.locator('#rp-plain').textContent(), /172\.30\.53\.90/);
      assert.doesNotMatch(await page.locator('#rp-attacker').textContent(), /giữ RRSIG|\.80 -> \.90/);
      assert.doesNotMatch(await page.locator('#rp-bind').textContent(), /< A/);
      await event('dns.response', {rcode:'SERVFAIL', ad:false, answers:[]}, 'secure');
      assert.match(await page.locator('#replay-caption').textContent(), /xem log xác thực/);
      assert.doesNotMatch(await page.locator('#replay-caption').textContent(), /Chữ ký không khớp/);
      const wires = await page.evaluate(() => window.seenWires);
      assert(wires.includes('rp-cp') && wires.includes('rp-cs'), 'observed client/resolver links must animate');
      assert(!wires.some(id => ['rp-pa','rp-sa','rp-ab'].includes(id)), 'unobserved upstream links must stay neutral');
      await page.emulateMedia({reducedMotion:'reduce'});
      assert.equal(await page.locator('#rp-attacker').evaluate(n => getComputedStyle(n).animationName), 'none');
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`PASS ${folder}: observed links only, no invented upstream logs, finite/reduced motion`);
    }
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
