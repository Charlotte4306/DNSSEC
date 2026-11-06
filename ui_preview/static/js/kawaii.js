/* Hieu ung nhat cua ban kawaii: nen nut + sao bung khi an. Khong cham toi du lieu lab. */
(() => {
  "use strict";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const enabled = () => document.documentElement.dataset.motion !== "off" && !reduced.matches;
  const SPARKLES = ["#ffd76e", "#ff9ecb", "#93d5ff", "#8fe3bd", "#cbb0f2", "#f6b8d4"];

  function burst(x, y) {
    if (!enabled()) return;
    for (let i = 0; i < 7; i += 1) {
      const star = document.createElement("span");
      const angle = (Math.PI * 2 * i) / 7 + Math.random() * .5;
      const distance = 34 + Math.random() * 42;
      star.className = "kw-burst";
      star.style.left = x + "px";
      star.style.top = y + "px";
      star.style.background = SPARKLES[i % SPARKLES.length];
      star.style.setProperty("--dx", Math.cos(angle) * distance + "px");
      star.style.setProperty("--dy", Math.sin(angle) * distance + "px");
      document.body.append(star);
      setTimeout(() => star.remove(), 640);
    }
  }

  document.addEventListener("pointerdown", event => {
    const control = event.target.closest("button, .scenario label, .scenario-row, .text-link, .scroll-link, .nav-link");
    if (!control || control.disabled) return;
    control.classList.add("kw-press");
    const release = () => {
      control.classList.remove("kw-press");
      removeEventListener("pointerup", release);
      removeEventListener("pointercancel", release);
    };
    addEventListener("pointerup", release, {once: true});
    addEventListener("pointercancel", release, {once: true});
  });

  document.addEventListener("click", event => {
    const button = event.target.closest("button:not(:disabled)");
    if (!button) return;
    burst(event.clientX || button.getBoundingClientRect().left + 12, event.clientY || button.getBoundingClientRect().top + 12);
  });

  // Badge bounce khi ket qua doi, phat hien theo tone chu khong theo chinh class cua ta.
  const lastTone = new WeakMap();
  const toneOf = el => (el.className || "").replace(/\b(outcome|kw-bounce|neutral|success|danger|warning)\b/g, "").trim()
    + "|" + (el.textContent || "").trim();
  const outcomes = document.querySelectorAll(".outcome");
  outcomes.forEach(el => {
    lastTone.set(el, toneOf(el));
    new MutationObserver(() => {
      const tone = toneOf(el);
      if (lastTone.get(el) === tone) return;
      lastTone.set(el, tone);
      if (!enabled()) return;
      el.classList.remove("kw-bounce");
      void el.offsetWidth;
      el.classList.add("kw-bounce");
    }).observe(el, {attributes: true, attributeFilter: ["class"], childList: true, characterData: true, subtree: true});
  });
  document.addEventListener("animationend", event => {
    if (event.animationName === "kw-pop") event.target.classList.remove("kw-bounce");
  });
})();
