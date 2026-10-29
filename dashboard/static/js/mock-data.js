/* Development fixtures only. No network calls; never import in live mode. */
"use strict";
window.MockData = (() => {
  const goodIP = "172.30.53.80", fakeIP = "172.30.53.90";
  function branch(resolver, attack, fault) {
    const secure = resolver === "secure";
    const blocked = secure && attack;
    const ip = attack ? fakeIP : goodIP;
    const dnsError = fault === "dns-error";
    const httpError = fault === "http-error" && !blocked && !dnsError;
    const stopped = blocked || dnsError;
    return {
      branch_id: resolver, resolver,
      dns: { server_ip: secure ? "172.30.53.30" : "172.30.53.40", name: "www.demo.test", rcode: dnsError ? null : blocked ? "SERVFAIL" : "NOERROR", ad: dnsError ? null : secure && !blocked, answers: stopped ? [] : [ip], error: dnsError ? "DNS timeout (minh họa)" : null },
      http: { attempted: !stopped, request_sent: !stopped && !httpError, connected_ip: stopped || httpError ? null : ip, status: stopped || httpError ? null : 200, site_id: stopped || httpError ? null : attack ? "training-fake" : "legitimate", error: httpError ? "Connection refused (minh họa)" : null },
      classification: dnsError || httpError ? "inconclusive" : blocked ? "blocked" : attack ? "accepted_fake" : secure ? "validated" : "reached_legitimate_unvalidated"
    };
  }
  return { create(scenario, fault) {
    const attack = scenario === "attack";
    return {
      source: "mock", warning: "Dữ liệu minh họa; không phải kết quả đo hay bằng chứng thực nghiệm.",
      run_id: "mock-" + Date.now().toString(36), created_at: new Date().toISOString(),
      scenario, fault, target: "www.demo.test",
      results: fault === "infra-error" ? null : { plain: branch("plain", attack, fault), secure: branch("secure", attack, fault) },
      illustration: attack ? { original_ip: goodIP, relay_ip: fakeIP, rrsig: "Giả định giữ nguyên RRSIG; chưa đo trong bản layout", validation: "SERVFAIL riêng lẻ chưa chứng minh lỗi chữ ký; bản live phải đối chiếu log Unbound." } : { note: "Giả định DNS hợp lệ; bản layout không kiểm tra chữ ký." }
    };
  }};
})();
