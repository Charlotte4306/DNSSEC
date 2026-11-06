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
      if (!response.ok && !(path === "/api/health" && value.source === "live" && value.ready === false)) throw new APIError(value.error?.message || `API trả lỗi HTTP ${response.status}.`, value.error?.code || "API_ERROR");
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
    $(".topology").classList.toggle("loading", locked);
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
    const values = await Promise.allSettled([api("/api/health"), api("/api/state")]);
    try {
      health = values[0].status === "fulfilled" ? values[0].value : null;
      labState = values[1].status === "fulfilled" ? values[1].value : null;
      if (health?.source !== "live" || labState?.source !== "live") {
        throw new APIError("Chưa nhận được trạng thái live hợp lệ từ API.", "NOT_LIVE");
      }
      $("#lab-status").textContent = health.ready ? `Dữ liệu thật · Relay: ${labState.actual_mode === "attack" ? "can thiệp" : labState.actual_mode === "normal" ? "giữ nguyên" : "chưa rõ"}` : "Lab chưa sẵn sàng";
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
    if (!data || data.source !== "live" || !/^[A-Za-z0-9_-]{1,80}$/.test(data.run_id || "") || !data.scenario_revision || typeof data.consistent !== "boolean") {
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
      why.addEventListener("click", () => { $("#evidence").open = true; $("#evidence summary").focus(); });
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
    notice(incomplete ? "Đã lưu phép đo nhưng chưa đủ kết luận. Xem lỗi và bằng chứng từng nhánh." : "Đã nhận kết quả DNS → HTTP thật từ lab và đối chiếu access log.", incomplete);
    updateControls();
  }
  async function start() {
    if ($("#run").disabled) return;
    busy = true; operationError = null; clearResult(); $("#evidence").open = false;
    $("#run-meta").textContent = "Đang chuẩn bị kịch bản và xóa cache";
    notice("Đang đổi mode và flush hai resolver. Đóng tab không dừng tác vụ trong lab.");
    try {
      const scenario = await api("/api/scenario", {action: selected()}, 130000);
      if (scenario.source !== "live" || !scenario.ready_for_run) throw new APIError("Kịch bản chưa sẵn sàng.", "NOT_READY");
      $("#lab-status").textContent = `Dữ liệu thật · Relay: ${scenario.actual_mode === "attack" ? "can thiệp" : "giữ nguyên"}`;
      $("#relay-node").classList.toggle("tampered", scenario.actual_mode === "attack");
      $("#relay-label").textContent = scenario.actual_mode === "attack" ? "Đang bật sửa phản hồi" : "Chuyển tiếp phản hồi";
      $("#run-meta").textContent = "Đang truy vấn DNS và truy cập HTTP";
      names.forEach(name => resetPanel(name, "Đang đo", "Máy khách đang hỏi resolver và quyết định bước HTTP."));
      notice("Đang chạy DNS → HTTP thật. Không đổi kịch bản trong lúc đo.");
      showResult(await api("/api/run", {}, 130000));
    } catch (error) {
      clearResult();
      names.forEach(name => resetPanel(name,"Không có kết quả mới", "Xem trạng thái lab rồi thử lại."));
      $("#run-meta").textContent = "Không có phép đo mới được xác nhận";
      $("#route-summary").textContent = "Chưa đủ dữ liệu DNS và HTTP để kết luận. Không dùng lại trang cũ.";
      uncertain = error.code === "CONNECTION_UNKNOWN";
      operationError = error.message + (uncertain ? " Bấm Kiểm tra lab; có thể xem lần chạy gần nhất khi tác vụ kết thúc." : "");
      notice(operationError, true);
    } finally {
      busy = false; updateControls();
      // Reconcile without replacing the concrete error message with an idle message.
      const savedNotice = $("#notice").textContent, savedError = $("#notice").classList.contains("error");
      await refresh();
      if (!current && health?.ready && !labState?.busy) notice(savedNotice, savedError);
    }
  }
  $("#run").addEventListener("click", start);
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
      if (value.source !== "live" || value.revision !== current.scenario_revision) {
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
      showResult(await api("/api/runs/" + encodeURIComponent(runID)));
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
  refresh();
  // One poll at a time; no synthetic data or fallback to mock when API is down.
  setInterval(() => { if (!document.hidden) refresh(); }, 5000);
})();
