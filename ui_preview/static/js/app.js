"use strict";
(() => {
  const $ = selector => document.querySelector(selector);
  const names = ["plain", "secure"];
  let current = null, proof = null, labState = null, health = null, operationError = null;
  let busy = false, checking = false, stale = false, uncertain = false, generation = 0;
  const selected = () => $("input[name=scenario]:checked").value;

  class APIError extends Error {
    constructor(message, code) { super(message); this.code = code; }
  }
  async function api(path, data, timeout = 15000, method) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, {
        method: method || (data === undefined ? "GET" : "POST"),
        headers: data === undefined ? {} : {"Content-Type": "application/json"},
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: controller.signal, cache: "no-store", credentials: "same-origin",
      });
      if (method === "HEAD") {
        if (!response.ok) throw new APIError("Không tải được nội dung preview đã lưu.", "PREVIEW_ERROR");
        return null;
      }
      let value;
      try { value = await response.json(); }
      catch { throw new APIError("API không trả JSON hợp lệ. Hãy mở dashboard bằng Flask.", "INVALID_RESPONSE"); }
      if (!response.ok && !(path === "/api/health" && value.source === "mock" && value.ready === false)) throw new APIError(value.error?.message || `API trả lỗi HTTP ${response.status}.`, value.error?.code || "API_ERROR");
      return value;
    } catch (error) {
      if (error instanceof APIError) throw error;
      throw new APIError(error.name === "AbortError" ? "Hết thời gian chờ API. Tác vụ trong lab có thể vẫn đang chạy." : "Mất kết nối API. Chưa có kết quả mới được xác nhận.", "CONNECTION_UNKNOWN");
    } finally { clearTimeout(timer); }
  }
  function notice(text, error = false) {
    $("#notice").textContent = text;
    $("#notice").classList.toggle("error", error);
  }
  function updateControls() {
    const locked = busy || Boolean(labState?.busy);
    $("#run").disabled = locked || uncertain || health?.ready !== true || !labState?.revision;
    $("#run").textContent = busy ? "Đang xử lý…" : labState?.busy ? "Lab đang bận…" : "Truy vấn và truy cập";
    document.querySelectorAll("input[name=scenario]").forEach(el => el.disabled = locked);
    $("#refresh").disabled = checking;
    $("#proof").disabled = locked || uncertain || !current || stale || !current.consistent;
    $("#restore").disabled = locked || !labState?.last_run_id;
    $("#copy").disabled = !current;
    $("#download").disabled = !current;
    $("#results").setAttribute("aria-busy", String(busy));

  }
  function resetPanel(name, title, detail) {
    const panel = $("#" + name + "-panel");
    panel.dataset.tone = "neutral";
    const badge = panel.querySelector(".outcome"); badge.className = "outcome neutral"; badge.textContent = title;
    const box = document.createElement("div"); box.className = "empty";
    const strong = document.createElement("strong"), p = document.createElement("p");
    strong.textContent = title; p.textContent = detail;
    box.append(strong, p); panel.querySelector(".panel-body").replaceChildren(box);
  }
  function clearResult() {
    generation++; current = null; proof = null; stale = false;
    $("#results").classList.remove("stale");
    $("#proof-result").hidden = true;
    $("#json").textContent = "{}"; $("#copy-status").textContent = "";
    $("#evidence-explanation").textContent = "Chưa có dữ liệu mới.";
    names.forEach(name => resetPanel(name, "Chưa có kết quả mới", "Đang chuẩn bị phép đo từ lab."));
    updateControls();
  }
  function markStale(reason) {
    if (!current) return;
    generation++; stale = true; proof = null;
    $("#results").classList.add("stale");
    document.querySelectorAll("iframe").forEach(frame => frame.remove());
    $("#proof-result").hidden = true;
    $("#run-meta").textContent = "Lần đo trước · " + current.run_id;
    $("#route-summary").textContent = "Chưa có kết quả cho trạng thái mới. " + reason;
    $("#evidence-explanation").textContent = `JSON dưới đây thuộc lần đo trước ${current.run_id}. ${reason}`;
    notice("Lần đo trước — " + reason, true);
    updateControls();
  }
  async function refresh() {
    if (checking) return;
    checking = true; updateControls();
    const requestedGeneration=generation;
    const values = await Promise.allSettled([api("/api/health"), api("/api/state")]);
    try {
      if (requestedGeneration!==generation) return;
      health = values[0].status === "fulfilled" ? values[0].value : null;
      labState = values[1].status === "fulfilled" ? values[1].value : null;
      if (health?.source !== "mock" || labState?.source !== "mock") {
        throw new APIError("Chưa nhận được trạng thái live hợp lệ từ API.", "NOT_LIVE");
      }
      $("#lab-status").textContent = health.ready ? `Dữ liệu phát lại · Relay: ${labState.actual_mode === "attack" ? "can thiệp" : labState.actual_mode === "normal" ? "giữ nguyên" : "chưa rõ"}` : "Lab chưa sẵn sàng";
      $("#relay-node").classList.toggle("tampered", labState.actual_mode === "attack");
      $("#relay-label").textContent = labState.actual_mode === "attack" ? "Đang bật sửa phản hồi" : labState.actual_mode === "normal" ? "Chuyển tiếp phản hồi" : "Chưa đọc được mode";
      if (uncertain && !labState.busy) uncertain = false;
      if (current && !stale && (!health.ready || labState.revision !== current.scenario_revision)) {
        markStale("Mode đã đổi hoặc lab chưa sẵn sàng. Truy vấn lại để có kết quả mới.");
      } else if (!busy && labState.busy) {
        notice("Lab đang xử lý một tác vụ khác. Đợi tác vụ kết thúc rồi chạy lại.");
      } else if (!busy && !current) {
        notice(operationError || labState.error?.message || (!health.ready ? "Docker hoặc dịch vụ chưa sẵn sàng. Kiểm tra lab trước khi chạy." : "Đã kết nối lab. Chọn kịch bản rồi bấm Truy vấn và truy cập."), Boolean(operationError || labState.error || !health.ready));
      }
    } catch (error) {
      $("#lab-status").textContent = "Chưa kết nối được lab";
      if (current && !stale) markStale("Không kiểm tra được trạng thái lab hiện tại.");
      else if (!busy) notice(values.find(v => v.status === "rejected")?.reason.message || error.message, true);
    } finally { checking = false; updateControls(); }
  }
  function validateResult(data) {
    if (!data || data.source !== "mock" || !/^[A-Za-z0-9_-]{1,80}$/.test(data.run_id || "") || !data.scenario_revision || typeof data.consistent !== "boolean") {
      throw new APIError("Kết quả thiếu nguồn live hoặc định danh phép đo.", "INVALID_RESULT");
    }
    for (const name of names) {
      const result = data.results?.[name];
      if (!result || result.run_id !== data.run_id || result.resolver !== name || !Array.isArray(result.dns?.answers) || typeof result.http?.attempted !== "boolean") {
        throw new APIError("Kết quả hai nhánh không khớp phép đo.", "INVALID_RESULT");
      }
    }
  }
  async function addPreview(container, result, name, run, version) {
    const url = `/api/runs/${run.run_id}/preview/${name}`;
    if (!run.consistent || result.http.preview_url !== url || !result.http.attempted || result.http.status !== 200 || result.http.error) return;
    const box = document.createElement("div"); box.className = "preview";
    const label = document.createElement("div"); label.className = "preview-label";
    label.textContent = "Nội dung HTTP do máy khách lab tải · " + result.http.site_id;
    const pending = document.createElement("p"); pending.className = "preview-loading"; pending.textContent = "Đang mở nội dung đã lưu…";
    box.append(label, pending); container.append(box);
    try {
      await api(url, undefined, 15000, "HEAD");
      if (version !== generation || stale) return;
      const frame = document.createElement("iframe"); frame.title = "Nội dung HTTP thật của " + name;
      frame.setAttribute("sandbox", ""); frame.referrerPolicy = "no-referrer"; frame.src = url;
      pending.replaceWith(frame);
    } catch (error) {
      if (version === generation) pending.textContent = error.message;
    }
  }
  function renderBranch(name, result, run, version) {
    const panel = $("#" + name + "-panel");
    const titles = { validated: ["Đã xác thực", "success"], reached_legitimate_unvalidated: ["Trang đúng · chưa xác thực", "neutral"], accepted_fake: ["Đã đến trang giả lập", "danger"], blocked: ["DNS từ chối", "danger"], inconclusive: ["Chưa đủ kết luận", "warning"] };
    const [title, tone] = titles[result.interpretation] || titles.inconclusive;
    panel.dataset.tone = tone;
    const badge = panel.querySelector(".outcome"); badge.textContent = title; badge.className = "outcome " + tone;
    const body = panel.querySelector(".panel-body"); body.replaceChildren();
    const metrics = document.createElement("dl"); metrics.className = "metrics";
    [["Trạng thái DNS", result.dns.rcode ?? "Không có phản hồi"], ["Cờ AD", result.dns.ad === null ? "—" : result.dns.ad ? "1 · có" : "0 · không"], ["IP nhận từ DNS", result.dns.answers.join(", ") || "—"]].forEach(([key, value]) => {
      const item = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = key; dd.textContent = value; item.append(dt,dd); metrics.append(item);
    });
    body.append(metrics);
    const delivery = document.createElement("p"); delivery.className = "delivery";
    delivery.textContent = result.http.status ? `HTTP ${result.http.status} · IP kết nối: ${result.http.connected_ip || "—"}` : result.http.attempted ? "Đã thử HTTP · chưa nhận phản hồi thành công" : "Không gửi HTTP · DNS chưa cấp IP sử dụng được";
    body.append(delivery);
    const timing = document.createElement("p"); timing.className = "timing";
    timing.textContent = `Thời gian đo: DNS ${result.dns.elapsed_ms ?? "—"} ms · HTTP ${result.http.elapsed_ms ?? "—"} ms`;
    body.append(timing);
    if (result.http.status === 200 && result.http.preview_url && run.consistent && !result.http.error) {
      addPreview(body, result, name, run, version);
    } else {
      const box = document.createElement("div"); box.className = "stopped" + (tone === "warning" ? " warning-box" : "");
      const strong = document.createElement("strong"), p = document.createElement("p");
      strong.textContent = !run.consistent ? "Mode đổi trong lúc đo" : result.http.status === 200 ? "Chưa có preview hợp lệ" : result.http.attempted ? "Không tải được website" : "Dừng trước bước HTTP";
      p.textContent = !run.consistent ? "Kết quả được giữ để đối chiếu; cần chạy lại trong mode ổn định." : result.dns.rcode === "SERVFAIL" ? "Resolver trả SERVFAIL. Xem log xác thực và đối chiếu chữ ký để xác định nguyên nhân." : result.http.error || result.dns.error || result.stop_reason || "Xem bằng chứng để xác định nơi dừng.";
      const why = document.createElement("button"); why.textContent = "Xem vì sao";
      why.addEventListener("click", () => { $("#evidence").open = true; $("#evidence > summary").focus(); });
      box.append(strong,p,why); body.append(box);
    }
  }
  function showResult(data) {
    validateResult(data);
    generation++; current = data; proof = null; stale = false; operationError = null;
    $("#results").classList.remove("stale"); $("#proof-result").hidden = true;
    const version = generation;
    names.forEach(name => renderBranch(name, data.results[name], data, version));
    $("#run-meta").textContent = `${data.run_id} · ${new Date(data.finished_at).toLocaleTimeString("vi-VN")}`;
    $("#json").textContent = JSON.stringify(data,null,2);
    const route = name => {
      const r = data.results[name];
      return `${name}: DNS ${r.dns.rcode ?? "lỗi truyền tải"}${r.dns.answers.length ? " / " + r.dns.answers.join(", ") : ""} → ${r.http.attempted ? "HTTP " + (r.http.status ?? "lỗi") : "không HTTP"}`;
    };
    $("#route-summary").textContent = names.map(route).join(". ") + ".";
    $("#evidence-explanation").textContent = "DNS raw, kết quả HTTP và access log bên dưới thuộc cùng run_id. Log Unbound/relay chỉ đối chiếu theo cửa sổ thời gian. SERVFAIL một mình chưa xác định nguyên nhân; nút Đối chiếu A và RRSIG lấy thêm dữ liệu thật từ authority/relay.";
    const incomplete = !data.consistent || names.some(name => data.results[name].interpretation === "inconclusive");
    notice(incomplete ? "Đã lưu phép đo nhưng chưa đủ kết luận. Xem lỗi và bằng chứng từng nhánh." : "Đã nhận kết quả DNS → HTTP phát lại từ lab và đối chiếu access log.", incomplete);
    updateControls();
  }
  // All progress is keyed by the backend sequence; reloading replays state without pulses.
  let activeJob = null, cursor = 0, liveVersion = 0;
  const seenEvents = new Set(), pulseFrames = new Map();
  const storage = {
    get(key) { try { return sessionStorage.getItem("dnssec-" + key); } catch { return null; } },
    set(key, value) { try { if (value === null) sessionStorage.removeItem("dnssec-" + key); else sessionStorage.setItem("dnssec-" + key, value); } catch {} },
  };
  const labels = {"job.accepted":"Tác vụ được nhận", "mode.changed":"Đã đổi chế độ relay", "cache.flushed":"Đã xóa cache", "dns.started":"Bắt đầu hỏi DNS", "dns.response":"Đã nhận phản hồi DNS", "dns.error":"Lỗi / timeout DNS", "validation.observed":"Trạng thái từ resolver", "http.skipped":"Bỏ qua HTTP", "http.connecting":"Đang kết nối HTTP", "http.connected":"TCP đã kết nối website", "http.request_sent":"Đã gửi HTTP request", "http.response":"Đã nhận HTTP response", "http.error":"Lỗi HTTP", "http.finished":"Kết thúc HTTP", "branch.completed":"Nhánh đã kết thúc", "proof.started":"Bắt đầu đối chiếu A / RRSIG", "proof.observed":"Đã thu bằng chứng A / RRSIG", "proof.unavailable":"Không thu được bằng chứng bổ sung", "evidence.saved":"Đã lưu evidence", "job.completed":"Đã hoàn tất phép đo", "job.failed":"Tác vụ thất bại"};
  function motionEnabled() { return document.documentElement.dataset.motion !== "off" && !matchMedia("(prefers-reduced-motion: reduce)").matches; }
  function stopPulses() {
    pulseFrames.forEach((frame, dot) => { cancelAnimationFrame(frame); dot.remove(); }); pulseFrames.clear();
  }
  new MutationObserver(() => { if (!motionEnabled()) stopPulses(); }).observe(document.documentElement, {attributes:true,attributeFilter:["data-motion"]});
  matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", () => { if (!motionEnabled()) stopPulses(); });
  function pulse(id, reverse) {
    const path = document.getElementById(id);
    if (!path || !motionEnabled()) return;
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("r", "4"); dot.setAttribute("fill", "#3157FF"); dot.setAttribute("aria-hidden", "true");
    path.ownerSVGElement.append(dot);
    const length = path.getTotalLength(), began = performance.now();
    const tick = time => {
      const fraction = Math.min(1,(time-began)/350), point = path.getPointAtLength(length * (reverse ? 1-fraction : fraction));
      dot.setAttribute("cx",point.x); dot.setAttribute("cy",point.y);
      if (fraction === 1) { dot.remove(); pulseFrames.delete(dot); }
      else pulseFrames.set(dot,requestAnimationFrame(tick));
    };
    pulseFrames.set(dot,requestAnimationFrame(tick));
  }
  function resetProgress() {
    liveVersion++; cursor = 0; seenEvents.clear(); stopPulses();
    $("#event-timeline").replaceChildren(); $("#timeline-status").textContent = "Chờ sự kiện";
    $("#recovery-comparison").hidden = true;
    for (const name of names) {
      $("#resolver-"+name).dataset.state = "idle";
      $("#http-"+name).classList.remove("connected");
      $("#http-"+name+"-label").textContent = name+" · chưa kết nối HTTP";
    }
    document.querySelectorAll('.validation-steps span').forEach(el=>el.classList.remove('observed'));
    $("#validation-received").textContent = "Nhận DNS: chờ";
    $("#validation-resolver").textContent = "AD / SERVFAIL: chờ";
    $("#validation-proof").textContent = "A / RRSIG / log: chờ";
  }
  function consumeEvents(events, replay = false) {
    for (const e of events) {
      if (seenEvents.has(e.sequence)) continue;
      seenEvents.add(e.sequence);
      const item = document.createElement("li"), detail = document.createElement("details"), summary = document.createElement("summary"), raw = document.createElement("pre");
      const stamp = new Date(e.timestamp).toLocaleTimeString("vi-VN", {hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit",fractionalSecondDigits:3});
      summary.textContent = `${String(e.sequence).padStart(2,"0")} · ${stamp} · ${e.branch || "điều phối"} · ${labels[e.kind] || e.kind}`;
      raw.textContent = JSON.stringify(e,null,2); detail.append(summary,raw); item.append(detail); item.dataset.kind=e.kind;
      $("#event-timeline").append(item);
      $("#timeline-status").textContent = `${seenEvents.size} mốc · ${e.run_id}`;
      const branch = names.includes(e.branch) ? e.branch : null, data = e.data || {};
      if (branch==='secure' && ['dns.response','dns.error'].includes(e.kind)) $("#validation-received").classList.add('observed');
      if (e.kind==='validation.observed') $("#validation-resolver").classList.add('observed');
      if (['proof.started','proof.observed','proof.unavailable','evidence.saved'].includes(e.kind)) $("#validation-proof").classList.add('observed');
      if (branch) {
        const node = $("#resolver-"+branch);
        if (e.kind === "dns.started") { node.dataset.state="processing"; if (!replay) pulse("dns-"+branch,false); }
        if (e.kind === "dns.response") {
          node.dataset.state = data.rcode === "SERVFAIL" ? "rejected" : data.rcode === "NOERROR" ? (branch === "secure" && data.ad ? "validated" : "response") : "error";
          if (!replay) pulse("dns-"+branch,true);
          if (branch === "secure") $("#validation-received").textContent="Nhận DNS: "+(data.rcode || "phản hồi");
        }
        if (e.kind === "dns.error") {
          node.dataset.state="error";
          if (branch === "secure") { $("#validation-received").textContent="Nhận DNS: lỗi / timeout"; $("#validation-resolver").textContent="AD / SERVFAIL: chưa biết"; }
        }
        if (e.kind === "validation.observed") $("#validation-resolver").textContent=`Resolver: ${data.rcode || "—"} · AD=${data.ad ? 1 : 0}`;
        if (e.kind === "http.connected") {
          $("#http-"+branch).classList.add("connected");
          $("#http-"+branch+"-label").textContent=`${branch} → ${data.ip === "172.30.53.80" ? "web-good · .80" : data.ip === "172.30.53.90" ? "web-fake · .90" : data.ip} · TCP kết nối`;
          if (!replay) pulse("http-"+branch,false);
        }
        if (e.kind === "http.response") $("#http-"+branch+"-label").textContent += ` · HTTP ${data.status}`;
        if (e.kind === "http.error") $("#http-"+branch+"-label").textContent += " · lỗi HTTP";
        if (e.kind === "http.skipped") $("#http-"+branch+"-label").textContent=branch+" · bỏ qua HTTP";
      }
      if (e.kind === "mode.changed") {
        $("#relay-node").classList.toggle("tampered",data.attack === true);
        $("#relay-label").textContent=data.attack ? "Đang bật sửa phản hồi" : "Chuyển tiếp phản hồi";
        $("#lab-status").textContent="Dữ liệu phát lại · Relay: "+(data.attack ? "can thiệp" : "giữ nguyên");
      }
      if (e.kind === "proof.started") $("#validation-proof").textContent="A / RRSIG / log: đang thu";
      if (e.kind === "proof.observed") $("#validation-proof").textContent="A / RRSIG: đã thu · xem evidence";
      if (e.kind === "proof.unavailable") $("#validation-proof").textContent="A / RRSIG: chưa đủ dữ liệu";
      if (e.kind === "evidence.saved") $("#validation-proof").textContent=data.complete ? "A / RRSIG / log: đã lưu, xem evidence" : "Evidence đã lưu · có dữ liệu chưa thu được";
    }
  }
  async function compareRecovery(run, action) {
    if (action === "attack" && run.consistent && run.scenario_before?.attack === true) storage.set("attack-run",run.run_id);
    if (action !== "recovery") return;
    const version = liveVersion, oldID = storage.get("attack-run");
    $("#recovery-comparison").hidden=false; $("#recovery-table").replaceChildren();
    $("#recovery-note").textContent=oldID ? "Đang đọc lần can thiệp gần nhất trong phiên này…" : `Đã đo mới ${run.run_id}. Chưa có lần can thiệp trong phiên này để đối chứng.`;
    if (!oldID) return;
    try {
      const old = await api("/api/runs/"+encodeURIComponent(oldID)); validateResult(old);
      if (version !== liveVersion) return;
      $("#recovery-note").textContent=`Can thiệp: ${old.run_id} → Khôi phục: ${run.run_id}. Đây là hai phép đo riêng; đối chiếu DNS, HTTP và site đích.`;
      const table=document.createElement("table"), head=document.createElement("tr");
      for (const text of ["Nhánh / phép đo","IP từ DNS","AD","HTTP","Site đích"]) { const th=document.createElement("th"); th.textContent=text; head.append(th); }
      const thead=document.createElement("thead"), tbody=document.createElement("tbody"); thead.append(head);
      for (const name of names) for (const [label,measure] of [["Can thiệp",old],["Khôi phục",run]]) {
        const r=measure.results[name], tr=document.createElement("tr");
        for (const value of [name+" / "+label,r.dns.answers.join(", ")||"—",r.dns.ad===null ? "—" : r.dns.ad ? "1" : "0",r.http.attempted ? r.http.status ?? "Lỗi" : "Bỏ qua",r.http.site_id||"—"]) { const td=document.createElement("td");td.textContent=value;tr.append(td); }
        tbody.append(tr);
      }
      table.append(thead,tbody); $("#recovery-table").append(table);
    } catch (error) { if (version === liveVersion) $("#recovery-note").textContent=`Đã đo mới ${run.run_id}; không đọc được đối chứng ${oldID}: ${error.message}`; }
  }
  async function followJob(jobID, replay = false) {
    activeJob=jobID; storage.set("active-job",jobID);
    const version=liveVersion;
    let retries=0;
    while (version === liveVersion) {
      let job;
      try { job=await api(`/api/jobs/${encodeURIComponent(jobID)}?after=${cursor}`); retries=0; }
      catch (error) {
        if (error.code !== "CONNECTION_UNKNOWN" || ++retries>8) throw error;
        notice("Mất kết nối tiến độ; đang nối lại cùng tác vụ, không gửi lệnh chạy mới.",true);
        await new Promise(resolve=>setTimeout(resolve,1000)); continue;
      }
      if (version !== liveVersion) return;
      if (job.job_id!==jobID || !Array.isArray(job.events)) throw new APIError("Tiến độ không khớp tác vụ.","INVALID_JOB");
      if (["baseline","attack","recovery"].includes(job.action)) document.querySelector(`input[value="${job.action}"]`).checked=true;
      consumeEvents(job.events,replay); replay=false; cursor=job.cursor;
      $("#run-meta").textContent=`${job.run_id} · ${job.status === "running" ? "đang đo" : job.status}`;
      if (job.status === "completed") {
        if (job.result_url!==`/api/runs/${job.run_id}`) throw new APIError("Đường dẫn kết quả không hợp lệ.","INVALID_JOB");
        const result=await api(job.result_url); if (version !== liveVersion) return;
        showResult(result); await compareRecovery(result,job.action);
        storage.set("active-job",null); storage.set("last-job",jobID); activeJob=null; return;
      }
      if (job.status !== "running") {
        storage.set("active-job",null); activeJob=null;
        if (job.result_url===`/api/runs/${job.run_id}`) showResult(await api(job.result_url));
        throw new APIError(job.error?.message || "Tác vụ chưa hoàn tất.",job.error?.code || "JOB_FAILED");
      }
      await new Promise(resolve=>setTimeout(resolve,400));
    }
  }
  async function start(resumeID = null) {
    if (!resumeID && $("#run").disabled) return;
    busy=true; operationError=null; clearResult(); resetProgress(); $("#evidence").open=false;
    $("#run-meta").textContent=resumeID ? "Đang đọc lại cùng tác vụ" : "Đang chuẩn bị kịch bản và xóa cache";
    notice("Theo dõi các mốc thực từ worker. Đóng tab không dừng tác vụ trong lab.");
    try {
      const jobID=resumeID || (await api("/api/jobs",{action:selected()},15000)).job_id;
      await followJob(jobID,Boolean(resumeID));
    } catch (error) {
      if (!current) names.forEach(name=>resetPanel(name,"Không có kết quả mới","Xem timeline và kiểm tra lab trước khi thử lại."));
      $("#run-meta").textContent="Chưa có phép đo mới được xác nhận";
      uncertain=error.code==="CONNECTION_UNKNOWN";
      operationError=error.message+(uncertain ? " Tác vụ có thể vẫn chạy; tải lại để nối lại cùng định danh." : "");
      notice(operationError,true);
    } finally { busy=false; updateControls(); await refresh(); if(operationError) notice(operationError,true); }
  }
  $("#run").addEventListener("click", () => start());
  $("#refresh").addEventListener("click", refresh);
  document.querySelectorAll("input[name=scenario]").forEach(el => el.addEventListener("change", () => {
    operationError = null;
    if (current) markStale("Bạn đã chọn kịch bản khác; relay chỉ đổi khi bấm chạy.");
    else notice("Kịch bản đã chọn. Bấm Truy vấn và truy cập để đổi relay, flush cache và đo.");
  }));
  $("#proof").addEventListener("click", async () => {
    if ($("#proof").disabled) return;
    busy = true; updateControls();
    try {
      const value = await api("/api/proof", {}, 130000);
      if (value.source !== "mock" || value.revision !== current.scenario_revision) {
        markStale("Revision của bằng chứng khác lần đo. Chạy lại để đối chiếu."); return;
      }
      proof = value;
      $("#proof-json").textContent = JSON.stringify(value,null,2);
      const records = value.proof.records;
      $("#proof-note").textContent = `Authority: ${records.authority.answers.join(", ")} · Relay: ${records.tamper.answers.join(", ")} · ${value.proof.rrsig_unchanged ? "RRSIG giữ nguyên" : "Chữ ký khác"}. Lấy bổ sung cùng revision, không phải cùng gói truy vấn của run.`;
      $("#proof-result").hidden = false; $("#evidence").open = true;
    } catch (error) { notice(error.message, true); }
    finally { busy = false; updateControls(); }
  });
  $("#restore").addEventListener("click", async () => {
    if ($("#restore").disabled) return;
    const runID = labState.last_run_id;
    busy = true; clearResult();
    try {
      const saved=await api("/api/runs/" + encodeURIComponent(runID));
      resetProgress(); showResult(saved);
      if (saved.job_id) {
        const version=liveVersion, job=await api("/api/jobs/"+encodeURIComponent(saved.job_id));
        if (version===liveVersion && job.run_id===saved.run_id) consumeEvents(job.events,true);
      }
      notice("Đang xem lại phép đo đã lưu " + runID + "; chưa thực hiện truy vấn mới.");
      if (current.scenario_revision !== labState.revision) markStale("Mode hiện tại khác lần đo đã lưu.");
    } catch (error) { notice(error.message, true); }
    finally { busy = false; updateControls(); }
  });
  const exportData = () => proof ? {...current, supplementary_proof: proof} : current;
  $("#copy").addEventListener("click", async () => {
    if (!current) return;
    try { await navigator.clipboard.writeText(JSON.stringify(exportData(),null,2)); $("#copy-status").textContent = stale ? "Đã sao chép lần đo trước." : "Đã sao chép kết quả."; }
    catch { $("#copy-status").textContent = "Không truy cập được clipboard. Dùng Tải JSON kết quả."; }
  });
  $("#download").addEventListener("click", () => {
    if (!current) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportData(),null,2)], {type:"application/json"}));
    const link = document.createElement("a"); link.href = url; link.download = current.run_id + ".json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  names.forEach(name => resetPanel(name,"Chưa có kết quả", "Chọn kịch bản rồi bấm Truy vấn và truy cập."));
  const rememberedJob=storage.get("active-job") || storage.get("last-job");
  if (rememberedJob) start(rememberedJob); else refresh();
  // One poll at a time; no synthetic data or fallback to mock when API is down.
  setInterval(() => { if (!document.hidden && !busy) refresh(); }, 5000);
})();
