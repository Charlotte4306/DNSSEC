"use strict";
(() => {
  const $ = (selector) => document.querySelector(selector);
  const scenarioNames = { baseline: "Bình thường", attack: "Can thiệp", recovery: "Khôi phục" };
  let current = null, timer = null, busy = false, stale = false;
  const mode = () => $("input[name=scenario]:checked").value;
  function notice(message, error = false) {
    $("#notice").textContent = message;
    $("#notice").classList.toggle("error", error);
  }
  function setBusy(value) {
    busy = value;
    $("#run").disabled = value;
    $("#run").textContent = value ? "Đang minh họa…" : "Chạy minh họa";
    $("#cancel").hidden = !value;
    document.querySelectorAll("input[name=scenario], #fixture").forEach(el => el.disabled = value);
    $("#results").setAttribute("aria-busy", String(value));
    $(".topology").classList.toggle("loading", value);
  }
  function resetPanel(resolver, title, detail) {
    const panel = $("#" + resolver + "-panel");
    panel.dataset.tone = "neutral";
    panel.querySelector(".outcome").className = "outcome neutral";
    panel.querySelector(".outcome").textContent = title;
    const box = document.createElement("div"); box.className = "empty";
    const strong = document.createElement("strong"); strong.textContent = title;
    const p = document.createElement("p"); p.textContent = detail;
    box.append(strong, p); panel.querySelector(".panel-body").replaceChildren(box);
  }
  function renderBranch(resolver, result) {
    const panel = $("#" + resolver + "-panel");
    const titles = { validated: ["Đã xác thực", "success"], reached_legitimate_unvalidated: ["Đến trang đúng · chưa xác thực", "neutral"], accepted_fake: ["Đã đến trang giả lập", "danger"], blocked: ["Đã từ chối DNS", "danger"], inconclusive: ["Chưa đủ kết quả", "warning"] };
    const [title, tone] = titles[result.classification];
    panel.dataset.tone = tone;
    const badge = panel.querySelector(".outcome"); badge.textContent = title; badge.className = "outcome " + tone;
    const body = panel.querySelector(".panel-body"); body.replaceChildren();
    const metrics = document.createElement("dl"); metrics.className = "metrics";
    [["Trạng thái DNS", result.dns.rcode ?? "Timeout"], ["Cờ AD", result.dns.ad === null ? "—" : result.dns.ad ? "1 · có" : "0 · không"], ["IP nhận từ DNS", result.dns.answers.join(", ") || "—"]].forEach(([key,value]) => {
      const item = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = key; dd.textContent = value; item.append(dt,dd); metrics.append(item);
    });
    body.append(metrics);
    const delivery = document.createElement("p"); delivery.className = "delivery";
    delivery.textContent = result.http.status ? `HTTP ${result.http.status} · IP kết nối: ${result.http.connected_ip}` : result.http.attempted ? "Đã thử HTTP · chưa kết nối được" : "Không gửi HTTP · chưa có IP DNS sử dụng được";
    body.append(delivery);
    if (result.http.status === 200) {
      const preview = document.createElement("div"); preview.className = "preview";
      const label = document.createElement("div"); label.className = "preview-label";
      label.textContent = "Nội dung website minh họa · " + result.http.site_id;
      const frame = document.createElement("iframe"); frame.title = "Website minh họa của " + resolver;
      frame.setAttribute("sandbox", ""); frame.referrerPolicy = "no-referrer";
      const fake = result.http.site_id === "training-fake";
      // All srcdoc content below is fixed, local fixture text. Never place API HTML here.
      frame.srcdoc = `<!doctype html><html lang="vi"><meta charset="utf-8"><style>body{font:14px 'Segoe UI',sans-serif;margin:0;padding:17px 20px;background:${fake ? '#fff0f0' : '#edf8f1'};color:${fake ? '#8c2630' : '#20533b'}}strong{display:block;font-size:19px;margin-bottom:6px}p{margin:0}</style><strong>${fake ? '⚠ Website giả lập' : '✓ Website hợp lệ'}</strong><p>${fake ? 'IP đã bị thay đổi. Plain vẫn chấp nhận phản hồi.' : 'Đích đến: 172.30.53.80 · Nội dung lab minh họa.'}</p></html>`;
      preview.append(label,frame); body.append(preview);
    } else {
      const box = document.createElement("div"); box.className = "stopped" + (tone === "warning" ? " warning-box" : "");
      const strong = document.createElement("strong"), p = document.createElement("p");
      strong.textContent = result.classification === "blocked" ? "Dừng trước bước HTTP" : result.http.attempted ? "Không tải được website" : "Chưa nhận được phản hồi DNS";
      p.textContent = result.classification === "blocked" ? "SERVFAIL: resolver không trả IP dùng được. Xem log mới xác định được nguyên nhân cụ thể." : result.http.error || result.dns.error;
      const why = document.createElement("button"); why.textContent = "Xem vì sao";
      why.addEventListener("click", () => { $("#evidence").open = true; $("#evidence summary").focus(); });
      box.append(strong,p,why); body.append(box);
    }
  }
  function clearEvidence() {
    current = null;
    $("#json").textContent = "{}";
    $("#evidence-explanation").textContent = "Chưa có dữ liệu mới.";
    $("#copy").disabled = true; $("#download").disabled = true;
    $("#copy-status").textContent = "";
  }
  function markStale() {
    if (!current) return;
    stale = true;
    $("#results").classList.add("stale");
    // Remove old website previews immediately; do not show a past page in the new mode.
    document.querySelectorAll("iframe").forEach(frame => frame.remove());
    notice("Lần minh họa trước — cấu hình đã đổi. Chạy lại để có kết quả phù hợp.");
    $("#run-meta").textContent = "Lần minh họa trước · " + current.run_id;
    $("#route-summary").textContent = "Kết quả trước đã cũ; chưa có kết quả cho lựa chọn mới.";
    $("#evidence-explanation").textContent = "Lần minh họa trước; JSON bên dưới thuộc " + current.run_id + ", không phải cấu hình vừa chọn.";
  }
  function start() {
    if (busy) return;
    clearEvidence(); stale = false; $("#results").classList.remove("stale");
    $("#evidence").open = false;
    const scenario = mode(), fault = $("#fixture").value;
    $("#relay-node").classList.toggle("tampered", scenario === "attack");
    $("#relay-label").textContent = scenario === "attack" ? "Minh họa sửa A, giữ RRSIG" : "Chuyển tiếp phản hồi";
    ["plain","secure"].forEach(name => resetPanel(name,"Đang minh họa", "Đang chuẩn bị dữ liệu mẫu cho DNS → HTTP."));
    $("#run-meta").textContent = "Đang chạy dữ liệu mẫu";
    $("#route-summary").textContent = "Truy vấn DNS → phản hồi → quyết định có gửi HTTP. Nhịp chuyển động chỉ để giải thích.";
    notice("Đang minh họa. Khoảng chờ này là hiệu ứng giao diện, không phải thời gian đo DNS.");
    setBusy(true);
    timer = setTimeout(() => {
      timer = null;
      current = window.MockData.create(scenario, fault);
      setBusy(false);
      $("#run-meta").textContent = `${scenarioNames[scenario]} · ${current.run_id} · ${new Date(current.created_at).toLocaleTimeString("vi-VN")}`;
      if (!current.results) {
        ["plain","secure"].forEach(name => resetPanel(name,"Không có kết quả mới", "Lab không sẵn sàng (minh họa). Kiểm tra Docker và dịch vụ trước khi thử lại."));
        notice("Lab không sẵn sàng (minh họa). Chưa đủ dữ liệu để kết luận DNSSEC chặn phản hồi.", true);
        $("#route-summary").textContent = "Chưa có dữ liệu DNS hoặc HTTP cho cả hai nhánh.";
      } else {
        Object.entries(current.results).forEach(([name,result]) => renderBranch(name,result));
        const validScenario = fault === "scenario";
        notice(validScenario ? "Đã hiển thị dữ liệu minh họa. Các số liệu này chưa được đo từ lab." : "Tình huống lỗi minh họa — không dùng để kết luận cuộc tấn công thành công.", !validScenario);
        $("#route-summary").textContent = !validScenario ? "Có lỗi trong bước DNS hoặc HTTP. Xem từng nhánh để phân biệt nơi dừng." : scenario === "attack" ? "Plain: DNS .90 → HTTP trang giả lập. Secure: SERVFAIL → không gửi HTTP (dữ liệu mẫu)." : "Cả hai nhánh: DNS .80 → HTTP trang hợp lệ. Secure có thêm xác thực DNSSEC (dữ liệu mẫu).";
      }
      $("#json").textContent = JSON.stringify(current,null,2);
      $("#evidence-explanation").textContent = scenario === "attack" && fault === "scenario" ? "Minh họa giả định: IP gốc .80 bị relay thay thành .90 nhưng giữ chữ ký. Plain chấp nhận; secure từ chối. Trong bản live cần đối chiếu RRSIG, log xác thực Unbound và access log cùng run_id để chứng minh; SERVFAIL một mình chưa đủ." : "Đây là fixture dùng review giao diện, không phải log hay phản hồi mạng thật. Cờ AD có ý nghĩa khi nhận từ resolver xác thực được tin cậy. Bản live sẽ lấy dữ liệu worker và bằng chứng theo cùng run_id.";
      $("#copy").disabled = false; $("#download").disabled = false;
    }, 900);
  }
  $("#run").addEventListener("click", start);
  $("#cancel").addEventListener("click", () => {
    clearTimeout(timer); timer = null; clearEvidence(); setBusy(false);
    ["plain","secure"].forEach(name => resetPanel(name,"Đã hủy minh họa", "Chọn Chạy minh họa để bắt đầu lại."));
    $("#run-meta").textContent = "Đã hủy · chưa có kết quả mới";
    $("#route-summary").textContent = "Minh họa đã dừng; không có tác vụ mạng nào được thực hiện.";
    notice("Đã hủy minh họa. Không giữ lại nội dung website từ lần trước.");
  });
  document.querySelectorAll("input[name=scenario], #fixture").forEach(el => el.addEventListener("change", markStale));
  $("#copy").addEventListener("click", async () => {
    if (!current) return;
    try { await navigator.clipboard.writeText(JSON.stringify(current,null,2)); $("#copy-status").textContent = stale ? "Đã sao chép lần minh họa trước." : "Đã sao chép JSON minh họa."; }
    catch { $("#copy-status").textContent = "Không truy cập được clipboard. Dùng Tải JSON minh họa."; }
  });
  $("#download").addEventListener("click", () => {
    if (!current) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{ type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = current.run_id + ".json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  ["plain","secure"].forEach(name => resetPanel(name,"Chưa có kết quả", "Chọn kịch bản và bấm Chạy minh họa."));
})();
