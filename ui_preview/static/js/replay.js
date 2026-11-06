"use strict";
(() => {
  const scene = document.querySelector(".replay-scene");
  if (!scene) return;
  const svgns = "http://www.w3.org/2000/svg";
  const layer = document.querySelector("#rp-machines");
  const packets = document.querySelector("#rp-packets");
  const marks = document.querySelector("#rp-bubbles");
  const caption = document.querySelector("#replay-caption");
  const badge = document.querySelector("#replay-mode");
  const playButton = document.querySelector("#replay-play");
  const wires = {};
  document.querySelectorAll(".rp-wires path").forEach(p => { wires[p.id.slice(3)] = p; });
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const moving = () => document.documentElement.dataset.motion !== "off" && !reduced.matches;

  const COLOR = { query: "#93d5ff", signed: "#7fdcaa", tampered: "#ff8ec7", http: "#b39af2", httpBad: "#e0668c" };
  const REAL_MS = 200, DEMO_MS = 90;
  const LANE = {
    plain: { client: "clientP", out: "cp", mid: "pa", toNet: "hpc" },
    secure: { client: "clientS", out: "cs", mid: "sa", toNet: "hsc" },
  };
  const NET = { good: "hng", fake: "hnf" };
  const PLAN = {
    clientP: { x: 40, y: 28, w: 236, h: 164, cap: 3, kind: "laptop", label: "Máy khách · không DNSSEC", sub: "trình duyệt + curl" },
    plain: { x: 320, y: 40, w: 236, h: 152, cap: 3, kind: "monitor", label: "Resolver thường", sub: "unbound plain · .40" },
    bind: { x: 900, y: 40, w: 292, h: 152, cap: 3, kind: "server", label: "Server DNS", sub: "BIND · zone đã ký" },
    attacker: { x: 600, y: 186, w: 240, h: 168, cap: 3, kind: "laptop", label: "Máy tấn công", sub: "relay sửa đáp án · .20" },
    good: { x: 900, y: 214, w: 292, h: 132, cap: 2, kind: "server", label: "Web thật", sub: "172.30.53.80" },
    clientS: { x: 40, y: 316, w: 236, h: 164, cap: 3, kind: "laptop", label: "Máy khách · có DNSSEC", sub: "trình duyệt + curl" },
    secure: { x: 320, y: 330, w: 236, h: 152, cap: 3, kind: "monitor", label: "Resolver DNSSEC", sub: "unbound secure · .30" },
    fake: { x: 900, y: 368, w: 292, h: 132, cap: 2, kind: "server", label: "Web giả", sub: "172.30.53.90" },
  };
  const screens = {};
  const nodeOf = name => document.querySelector("#rp-" + name);

  function el(tag, attrs, text) {
    const node = document.createElementNS(svgns, tag);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function shape(p) {
    if (p.kind === "laptop") {
      const lid = p.h - 52;
      return { body: lid, screen: [p.x + 11, p.y + 11, p.w - 22, lid - 25], deck: p.y + lid };
    }
    if (p.kind === "monitor") {
      const bez = p.h - 56;
      return { body: bez, screen: [p.x + 11, p.y + 11, p.w - 22, bez - 27], stand: p.y + bez };
    }
    const bez = p.h - 34;
    return { body: bez, screen: [p.x + 11, p.y + 11, p.w - 22, bez - 44], chin: p.y + bez - 32 };
  }
  function buildMachines() {
    Object.entries(PLAN).forEach(([name, p]) => {
      const g = el("g", { class: "rp-node rp-" + name + " rp-kind-" + p.kind, id: "rp-" + name });
      const s = shape(p), [sx, sy, sw, sh] = s.screen;
      if (p.kind === "laptop") {
        g.append(el("path", { class: "rp-deck", d: `M${p.x - 10} ${s.deck} h${p.w + 20} l-16 18 h-${p.w - 12} z` }));
        g.append(el("rect", { class: "rp-keys", x: p.x + 26, y: s.deck + 4, width: p.w - 52, height: 5, rx: 2.5 }));
        g.append(el("rect", { class: "rp-track", x: p.x + p.w / 2 - 18, y: s.deck + 11, width: 36, height: 4, rx: 2 }));
      } else if (p.kind === "monitor") {
        g.append(el("rect", { class: "rp-neck", x: p.x + p.w / 2 - 11, y: s.stand - 2, width: 22, height: 14 }));
        g.append(el("rect", { class: "rp-foot", x: p.x + p.w / 2 - 42, y: s.stand + 10, width: 84, height: 9, rx: 4.5 }));
      } else {
        for (let i = 0; i < 3; i++) g.append(el("rect", { class: "rp-vent", x: p.x + 16, y: s.chin + i * 7, width: p.w * .46, height: 3.4, rx: 1.7 }));
        g.append(el("circle", { class: "rp-led", cx: p.x + p.w - 34, cy: s.chin + 6, r: 3.2 }));
        g.append(el("circle", { class: "rp-led alt", cx: p.x + p.w - 21, cy: s.chin + 6, r: 3.2 }));
      }
      g.append(el("rect", { class: "rp-bezel", x: p.x, y: p.y, width: p.w, height: s.body, rx: p.kind === "server" ? 13 : 15 }));
      if (p.kind !== "server") g.append(el("circle", { class: "rp-cam", cx: p.x + p.w / 2, cy: p.y + 5.5, r: 1.7 }));
      g.append(el("rect", { class: "rp-screen", x: sx, y: sy, width: sw, height: sh, rx: 10 }));
      if (p.kind !== "server") g.append(el("rect", { class: "rp-brand", x: p.x + p.w / 2 - 15, y: p.y + s.body - 9, width: 30, height: 3.4, rx: 1.7 }));
      const rows = [], stepY = sh / (p.cap + .35);
      for (let i = 0; i < p.cap; i++) {
        const line = el("text", { class: "rp-line rp-dim", x: sx + 10, y: sy + stepY * (i + 1) }, "");
        rows.push(line); g.append(line);
      }
      g.append(el("text", { class: "rp-label", x: p.x + p.w / 2, y: p.y + p.h - 20 }, p.label));
      g.append(el("text", { class: "rp-sub", x: p.x + p.w / 2, y: p.y + p.h - 5 }, p.sub));
      layer.append(g);
      screens[name] = { els: rows, texts: [], cap: p.cap, bubble: [p.x + p.w - 16, p.y + p.h - 14] };
    });
  }
  buildMachines();

  function render(name) {
    const s = screens[name];
    s.els.forEach((line, i) => {
      const entry = s.texts[i];
      line.setAttribute("class", "rp-line rp-" + (entry ? entry.tone : "dim"));
      line.textContent = entry ? entry.text : "";
      if (entry && !entry.done) line.append(el("tspan", { class: "rp-caret" }, "▌"));
    });
  }
  function log(name, text, tone) {
    const s = screens[name];
    if (!s) return;
    s.texts.forEach(e => { e.done = true; });
    if (s.texts.length >= s.cap) s.texts.shift();
    const entry = { text: moving() ? "" : text, tone, done: !moving() };
    s.texts.push(entry);
    render(name);
    if (!moving()) return;
    const per = Math.max(6, Math.min(15, 260 / text.length));
    let i = 0;
    const tick = () => {
      if (entry.done) return;
      i += 1;
      entry.text = text.slice(0, i);
      render(name);
      if (i >= text.length) { entry.done = true; render(name); }
      else setTimeout(tick, per);
    };
    setTimeout(tick, 40);
  }
  function mark(name, tone) {
    if (!tone) return;
    const node = nodeOf(name);
    if (!node) return;
    node.classList.remove("is-hot", "is-good", "is-bad");
    node.classList.add("is-" + tone);
  }
  function bubble(name, text, tone) {
    const s = screens[name];
    if (!s) return;
    const g = el("g", { class: "rp-bubble " + tone });
    const rx = Math.max(13, text.length * 3.6 + 7), cx = s.bubble[0] + 12 - rx;
    g.append(el("ellipse", { cx, cy: s.bubble[1], rx, ry: 13 }));
    g.append(el("text", { x: cx, y: s.bubble[1] + 4 }, text));
    marks.append(g);
    if (moving()) setTimeout(() => { if (g.parentNode) g.remove(); }, 1700);
  }
  function travel(wire, color, reverse, ms) {
    const path = wires[wire];
    if (!path) return;
    path.classList.add("is-live");
    if (!moving()) { setTimeout(() => path.classList.remove("is-live"), 200); return; }
    const dot = el("circle", { class: "rp-packet", r: 9, fill: color, "aria-hidden": "true" });
    packets.append(dot);
    const length = path.getTotalLength(), began = performance.now();
    const done = () => { dot.remove(); path.classList.remove("is-live"); };
    const failsafe = setTimeout(done, ms + 500);
    const step = now => {
      const f = Math.min(1, (now - began) / ms), p = path.getPointAtLength(length * (reverse ? 1 - f : f));
      dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y);
      if (f < 1) requestAnimationFrame(step);
      else { clearTimeout(failsafe); done(); }
    };
    requestAnimationFrame(step);
  }
  function clearScene() {
    gen++;
    packets.replaceChildren();
    marks.replaceChildren();
    Object.values(wires).forEach(w => w.classList.remove("is-live"));
    Object.keys(PLAN).forEach(name => {
      screens[name].texts = [];
      render(name);
      const node = nodeOf(name);
      node.classList.remove("is-hot", "is-good", "is-bad");
      if (name === "attacker") node.classList.remove("is-on");
    });
  }
  let gen = 0, lastSeq = -1, nextFree = 0, recorded = [], lastMode = "";

  function run(step) {
    if (step.text) caption.textContent = step.text;
    if (step.attacker !== undefined) nodeOf("attacker").classList.toggle("is-on", step.attacker);
    if (step.mark) Object.entries(step.mark).forEach(([name, tone]) => mark(name, tone));
    if (step.bubble) bubble(step.bubble.name, step.bubble.text, step.bubble.tone);
    (step.log || []).forEach(([name, text, tone]) => log(name, text, tone));
    let offset = 0;
    (step.hops || []).forEach(hop => {
      setTimeout(() => { if (gen === step.gen) travel(hop.wire, hop.color, hop.reverse, hop.ms); }, offset);
      offset += hop.ms;
    });
  }
  function play(steps, mode) {
    lastMode = mode;
    badge.textContent = mode === "live" ? "Phát lại sự kiện thật" : "Minh họa kịch bản";
    badge.className = "replay-mode " + (mode === "live" ? "is-live" : "is-demo");
    const own = gen;
    const base = Math.max(performance.now(), nextFree);
    let clock = base;
    steps.forEach(step => {
      step.gen = own;
      const hopTime = step.hops ? step.hops.reduce((sum, hop) => sum + hop.ms, 0) : 0;
      clock += step.wait ?? Math.max(260, hopTime + 140);
      const at = clock - base;
      if (at <= 0) run(step);
      else setTimeout(() => { if (own === gen) run(step); }, at);
    });
    nextFree = clock + 60;
  }
  function syncButton() {
    playButton.textContent = recorded.length ? "Phát lại lần đo" : "Xem mô phỏng";
    playButton.setAttribute("aria-label", recorded.length
      ? "Phát lại " + recorded.length + " mốc của lần đo vừa rồi"
      : "Chạy mô phỏng minh họa cho kịch bản đang chọn");
  }

  function hops(branch, reverse, color) {
    const lane = LANE[branch];
    const chase = [{ wire: lane.mid, color, reverse: !reverse, ms: DEMO_MS }, { wire: "ab", color, reverse, ms: DEMO_MS }];
    const entry = { wire: lane.out, color, reverse, ms: REAL_MS };
    return reverse ? [...chase, entry] : [entry, ...chase];
  }
  function netHops(branch, target) {
    const color = target === "fake" ? COLOR.httpBad : COLOR.http;
    return [{ wire: LANE[branch].toNet, color, ms: 300 }, { wire: NET[target], color, ms: 260 }];
  }

  function fromEvent(e) {
    const data = e.data || {}, branch = e.branch === "secure" ? "secure" : "plain";
    const lane = LANE[branch], client = lane.client, secure = branch === "secure";
    if (e.kind === "mode.changed") {
      const on = data.attack === true;
      return { mode: "live", steps: [{ attacker: on, mark: { attacker: on ? "bad" : "good" }, log: [["attacker", on ? "> tamper --enable" : "> tamper --disable", on ? "bad" : "ok"]], text: on ? "Máy tấn công bật sửa bản ghi A." : "Máy tấn công chuyển tiếp nguyên bản." }] };
    }
    if (e.kind === "dns.started") {
      return { mode: "live", steps: [{ mark: { [client]: "hot", [branch]: "hot" }, log: [[client, "> www.demo.test", "prompt"], [branch, "> query A", "prompt"]], hops: hops(branch, false, COLOR.query), text: `Máy khách ${secure ? "có" : "không"} DNSSEC hỏi www.demo.test.` }] };
    }
    if (e.kind === "dns.response") {
      const failed = data.rcode === "SERVFAIL", answers = data.answers || [];
      const fake = answers.some(a => a.includes(".90"));
      const color = failed || fake ? COLOR.tampered : COLOR.signed;
      const lines = [[branch, failed ? "< SERVFAIL" : `< A ${fake ? "172.30.53.90" : "172.30.53.80"}`, failed || fake ? "bad" : "ok"]];
      if (!failed) lines.push(["bind", "< A 172.30.53.80 + RRSIG", "ok"]);
      if (fake) lines.push(["attacker", "A .80 -> .90 (giữ RRSIG)", "bad"]);
      const text = failed ? "Chữ ký không khớp → SERVFAIL, resolver không trả IP."
        : fake ? "Máy khách không DNSSEC nhận .90."
        : secure ? "RRSIG hợp lệ, cờ AD bật." : "Máy khách nhận 172.30.53.80.";
      return { mode: "live", steps: [{ attacker: fake || undefined, mark: { [branch]: failed || fake ? "bad" : "good", bind: "good" }, log: lines, hops: hops(branch, true, color), bubble: { name: branch, text: failed ? "✗" : secure ? "AD ✓" : "A", tone: failed ? "no" : "ok" }, text }] };
    }
    if (e.kind === "validation.observed") {
      return { mode: "live", steps: [{ mark: { secure: data.ad ? "good" : "bad" }, log: [["secure", data.ad ? "AD=1 · anchor khớp" : "AD=0 · từ chối", data.ad ? "ok" : "bad"]], bubble: { name: "secure", text: data.ad ? "AD=1" : "AD=0", tone: data.ad ? "ok" : "no" }, text: `Resolver secure báo AD=${data.ad ? 1 : 0}, ${data.rcode || "—"}.` }] };
    }
    if (e.kind === "http.connected" || e.kind === "http.request_sent") {
      const fake = data.ip === "172.30.53.90", target = fake ? "fake" : "good";
      return { mode: "live", steps: [{ mark: { [client]: "hot", [target]: "hot" }, log: [[client, "> curl www.demo.test", "prompt"]], hops: netHops(branch, target), text: fake ? "Máy khách gửi HTTP tới Web giả .90." : "Máy khách gửi HTTP tới Web thật .80." }] };
    }
    if (e.kind === "http.response") {
      const fake = /training-fake/.test(JSON.stringify(data)), target = fake ? "fake" : "good";
      return { mode: "live", steps: [{ mark: { [target]: fake ? "bad" : "good" }, log: [[target, `< 200 · ${fake ? "training-fake" : "legitimate"}`, fake ? "bad" : "ok"], [client, "< 200 OK", fake ? "bad" : "ok"]], bubble: { name: target, text: "200", tone: fake ? "no" : "ok" }, text: fake ? "Trang giả đã tải — DNS bị sửa nhưng web vẫn hiện bình thường." : "Trang thật tải xong, đúng site_id." }] };
    }
    if (e.kind === "http.skipped") {
      return { mode: "live", steps: [{ mark: { [client]: "bad" }, log: [[client, "! không có IP hợp lệ", "bad"]], bubble: { name: client, text: "∅", tone: "no" }, text: "DNS bị từ chối → máy khách không gửi HTTP." }] };
    }
    if (e.kind === "proof.observed") {
      return { mode: "live", steps: [{ bubble: { name: "bind", text: "A+RRSIG", tone: "ok" }, log: [["bind", "proof: A + RRSIG", "prompt"]], text: "Thu bản ghi A và RRSIG từ authority và relay." }] };
    }
    if (e.kind === "job.completed") {
      return { mode: "live", steps: [{ text: "Xong phép đo — bằng chứng lưu theo run_id." }] };
    }
    return null;
  }
  function onEvent(e) {
    if (e.sequence <= lastSeq || lastMode === "demo") { clearScene(); recorded = []; }
    lastSeq = e.sequence;
    recorded.push(e);
    if (recorded.length > 80) recorded.shift();
    const view = fromEvent(e);
    if (view) play(view.steps, view.mode);
    syncButton();
  }
  window.addEventListener("dnssec:event", event => onEvent(event.detail));

  const ask = branch => [{
    mark: { [LANE[branch].client]: "hot", [branch]: "hot" },
    log: [[LANE[branch].client, "> www.demo.test", "prompt"], [branch, "> query A", "prompt"]],
    hops: hops(branch, false, COLOR.query),
    text: branch === "plain" ? "Máy khách trên hỏi qua resolver không DNSSEC." : "Máy khách dưới hỏi qua resolver có DNSSEC.",
  }];
  const web = (branch, target) => [{
    mark: { [LANE[branch].client]: "hot", [target]: "hot" },
    log: [[LANE[branch].client, "> curl www.demo.test", "prompt"], [target, `< 200 · ${target === "fake" ? "training-fake" : "legitimate"}`, target === "fake" ? "bad" : "ok"], [LANE[branch].client, "< 200 OK", target === "fake" ? "bad" : "ok"]],
    hops: netHops(branch, target),
    bubble: { name: target, text: "200", tone: target === "fake" ? "no" : "ok" },
    text: target === "fake" ? "Máy khách trên vào Web giả mà không thấy gì." : `Máy khách ${branch === "plain" ? "trên" : "dưới"} vào Web thật.`,
  }];
  const script = {
    baseline: [
      { attacker: false, mark: { attacker: "good" }, log: [["attacker", "> tamper --disable", "ok"], ["bind", "zone demo.test (signed)", "prompt"]], text: "Relay tắt chế độ sửa, zone đã ký sẵn sàng." },
      ...ask("plain"),
      { mark: { plain: "good", bind: "good" }, log: [["bind", "< A 172.30.53.80 + RRSIG", "ok"], ["plain", "< A 172.30.53.80", "ok"]], hops: hops("plain", true, COLOR.signed), bubble: { name: "plain", text: "A", tone: "ok" }, text: "Plain không đọc chữ ký, vẫn đưa đúng IP." },
      ...web("plain", "good"),
      ...ask("secure"),
      { mark: { secure: "good", bind: "good" }, log: [["secure", "AD=1 · anchor khớp", "ok"]], hops: hops("secure", true, COLOR.signed), bubble: { name: "secure", text: "AD ✓", tone: "ok" }, text: "Secure đối chiếu RRSIG với trust anchor." },
      ...web("secure", "good"),
    ],
    attack: [
      { attacker: true, mark: { attacker: "bad" }, log: [["attacker", "> tamper --enable", "bad"], ["bind", "< A .80 + RRSIG", "ok"]], text: "Máy tấn công đổi A sang .90, giữ nguyên RRSIG." },
      ...ask("plain"),
      { mark: { plain: "bad", attacker: "bad" }, log: [["attacker", "A .80 -> .90 (giữ RRSIG)", "bad"], ["plain", "< A 172.30.53.90", "bad"]], hops: hops("plain", true, COLOR.tampered), bubble: { name: "plain", text: "A→.90", tone: "no" }, text: "Plain nhận .90 vì không kiểm chữ ký." },
      ...web("plain", "fake"),
      ...ask("secure"),
      { mark: { secure: "bad" }, log: [["secure", "< SERVFAIL", "bad"], ["secure", "RRSIG KHÔNG khớp A=.90", "bad"]], hops: hops("secure", true, COLOR.tampered), bubble: { name: "secure", text: "✗", tone: "no" }, text: "Chữ ký không khớp IP → secure trả SERVFAIL." },
      { mark: { clientS: "bad" }, log: [["clientS", "! không có IP hợp lệ", "bad"]], bubble: { name: "clientS", text: "∅", tone: "no" }, text: "Máy khách dưới không gửi HTTP." },
    ],
    recovery: [
      { attacker: false, mark: { attacker: "good" }, log: [["attacker", "> tamper --disable", "ok"], ["plain", "> flush cache", "prompt"]], text: "Tắt sửa phản hồi, xóa cache hai resolver." },
      ...ask("plain"),
      { mark: { plain: "good" }, log: [["bind", "< A 172.30.53.80 + RRSIG", "ok"], ["plain", "< A 172.30.53.80", "ok"]], hops: hops("plain", true, COLOR.signed), bubble: { name: "plain", text: "A", tone: "ok" }, text: "Plain nhận lại đúng 172.30.53.80." },
      ...ask("secure"),
      { mark: { secure: "good" }, log: [["secure", "AD=1 · anchor khớp", "ok"]], hops: hops("secure", true, COLOR.signed), bubble: { name: "secure", text: "AD ✓", tone: "ok" }, text: "RRSIG hợp lệ trở lại." },
      ...web("plain", "good"),
      ...web("secure", "good"),
    ],
  };
  const chosenScenario = () => {
    const radio = document.querySelector("input[name=scenario]:checked");
    return radio && script[radio.value] ? radio.value : "baseline";
  };
  function showDemo(mode) {
    clearScene(); lastSeq = -1; nextFree = 0;
    play(script[mode], "demo");
  }
  Object.keys(script).forEach(mode => {
    const row = document.querySelector(`[data-preview-mode="${mode}"]`);
    const radio = document.querySelector(`input[name=scenario][value="${mode}"]`);
    const show = () => showDemo(mode);
    if (row) {
      row.addEventListener("pointerenter", show);
      row.addEventListener("focus", show);
      row.addEventListener("click", show);
    }
    if (radio) radio.addEventListener("change", show);
  });
  playButton.addEventListener("click", () => {
    if (!recorded.length) return showDemo(chosenScenario());
    const steps = recorded.map(fromEvent).filter(Boolean).flatMap(view => view.steps);
    clearScene(); lastSeq = -1; nextFree = 0;
    play(steps, "live");
    caption.textContent = `Phát lại ${recorded.length} mốc của lần đo ${recorded[0].run_id || ""}.`;
  });
  syncButton();
  caption.textContent = "Chưa có replay.";
})();
