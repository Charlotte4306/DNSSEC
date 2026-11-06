"use strict";
(() => {
  const root = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(hover: hover) and (pointer: fine)");
  let preference = "on", frame = 0;
  try { preference = localStorage.getItem("dnssec-motion") || "on"; } catch {}
  const enabled = () => preference !== "off" && !reduced.matches;
  const toggle = document.querySelector("#motion-toggle");
  function applyPreference() {
    root.dataset.motion = enabled() ? "on" : "off";
    toggle.setAttribute("aria-pressed", String(enabled()));
    toggle.setAttribute("aria-label", enabled() ? "Tắt hiệu ứng chuyển động" : "Bật hiệu ứng chuyển động");
    toggle.textContent = enabled() ? "Hiệu ứng bật" : "Hiệu ứng tắt";
    toggle.disabled = reduced.matches;
    toggle.title = reduced.matches ? "Theo thiết lập giảm chuyển động của hệ thống" : "Bật hoặc tắt hiệu ứng trang";
    drawNetwork();
  }
  toggle.addEventListener("click", () => {
    preference = enabled() ? "off" : "on";
    try { localStorage.setItem("dnssec-motion", preference); } catch {}
    applyPreference();
  });
  reduced.addEventListener("change", applyPreference);

  // Animate only editorial labels. IPs, timestamps, results, and control text stay intact.
  document.querySelectorAll("[data-scramble]").forEach(label => {
    const original = label.textContent;
    let timer;
    const restore = () => { clearInterval(timer); label.textContent = original; };
    const play = () => {
      restore();
      if (!enabled()) return;
      let step = 0;
      timer = setInterval(() => {
        label.textContent = [...original].map((char,index) => char === " " || index < step / 1.3 ? char : "+/<>01"[Math.floor(Math.random()*6)]).join("");
        if (++step > original.length*1.3+1 || !enabled()) restore();
      }, 22);
    };
    const target = label.closest("a,button");
    target.addEventListener("pointerenter", play);
    target.addEventListener("focus", play);
    target.addEventListener("pointerleave", restore);
    target.addEventListener("blur", restore);
  });

  const preview = document.querySelector(".scenario-visual");
  const descriptions = {
    baseline: [".80","Đến trang hợp lệ",".80","Chữ ký hợp lệ"],
    attack: [".90","Đến trang giả lập","SERVFAIL","Dừng trước HTTP"],
    recovery: [".80","Trở lại trang hợp lệ",".80","Xác thực thành công"],
  };
  document.querySelectorAll("[data-preview-mode]").forEach(row => {
    const show = () => {
      preview.dataset.preview = row.dataset.previewMode;
      document.querySelectorAll("[data-preview-mode]").forEach(other => {
        other.classList.toggle("is-active", other === row);
        other.setAttribute("aria-pressed", String(other === row));
      });
      const values = descriptions[row.dataset.previewMode];
      ["#preview-plain","#preview-plain-note","#preview-secure","#preview-secure-note"].forEach((id,index) => document.querySelector(id).textContent = values[index]);
    };
    row.addEventListener("pointerenter", show);
    row.addEventListener("focus", show);
    row.addEventListener("click", show);
  });

  const tip = document.querySelector("#node-tip");
  document.querySelectorAll("[data-node-note]").forEach(node => {
    const show = () => { tip.textContent = node.dataset.nodeNote; tip.hidden = false; };
    node.addEventListener("pointerenter", show);
    node.addEventListener("focus", show);
    node.addEventListener("click", show);
    node.addEventListener("pointerleave", () => { if (document.activeElement !== node) tip.hidden = true; });
    node.addEventListener("blur", () => tip.hidden = true);
  });

  if ("IntersectionObserver" in window) {
    const reveal = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add("seen"); reveal.unobserve(entry.target); }
    }), {threshold:.15});
    document.querySelectorAll("[data-reveal]").forEach(el => reveal.observe(el));
    const navigation = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      document.querySelectorAll(".nav-link").forEach(link => {
        if (link.hash === "#"+entry.target.id) link.setAttribute("aria-current","location");
        else link.removeAttribute("aria-current");
      });
    }), {rootMargin:"-15% 0px -45% 0px", threshold:0});
    ["#story","#scenarios","#lab"].forEach(id => navigation.observe(document.querySelector(id)));
  } else document.querySelectorAll("[data-reveal]").forEach(el => el.classList.add("seen"));

  const canvas = document.querySelector("#network-art"), context = canvas.getContext("2d");
  let width=0, height=0, pointer={x:.7,y:.4};
  function drawNetwork() {
    if (!context || !width || !height) return;
    context.clearRect(0,0,width,height);
    const scale = width < 700 ? .7 : 1;
    const anchors = [[.76,.25],[.9,.59],[.58,.74],[.22,.68],[.42,.18]];
    anchors.forEach(([x,y],index) => {
      const drift = enabled() && finePointer.matches ? (pointer.x-.5)*12 : 0;
      const ox=x*width+drift*(index%2 ? 1 : -1), oy=y*height;
      const unit=16*scale;
      context.lineWidth=.75;
      context.strokeStyle=index%2 ? "#d4d4cc" : "#c7c7be";
      const branches=[[-3,0,-1,0,-1,-2,1,-2,1,-3],[0,3,0,1,2,1,2,-1,4,-1],[-3,2,-2,2,-2,1,0,1,0,-1]];
      branches.forEach(coords => {
        context.beginPath();
        for (let i=0;i<coords.length;i+=2) {
          const px=ox+coords[i]*unit, py=oy+coords[i+1]*unit;
          if (i===0) context.moveTo(px,py); else context.lineTo(px,py);
        }
        context.stroke();
        context.strokeRect(ox+coords[coords.length-2]*unit-2,oy+coords[coords.length-1]*unit-2,4,4);
      });
    });
  }
  function resize() {
    const rect=canvas.getBoundingClientRect(), ratio=Math.min(devicePixelRatio || 1,2);
    width=rect.width; height=rect.height;
    canvas.width=Math.round(width*ratio); canvas.height=Math.round(height*ratio);
    context?.setTransform(ratio,0,0,ratio,0,0);
    drawNetwork();
  }
  new ResizeObserver(resize).observe(canvas);
  document.querySelector("#story").addEventListener("pointermove", event => {
    if (!enabled() || !finePointer.matches) return;
    const box=canvas.getBoundingClientRect(); pointer={x:(event.clientX-box.left)/box.width,y:(event.clientY-box.top)/box.height};
    if (!frame) frame=requestAnimationFrame(()=>{frame=0;drawNetwork();});
  }, {passive:true});
  let scrollFrame=0;
  addEventListener("scroll", () => {
    if (scrollFrame) return;
    scrollFrame=requestAnimationFrame(()=>{
      scrollFrame=0;
      const max=document.documentElement.scrollHeight-innerHeight;
      root.style.setProperty("--read",max>0?String(scrollY/max):"0");
      root.style.setProperty("--hero-y",enabled()?Math.min(scrollY*.075,45)+"px":"0px");
    });
  },{passive:true});
  applyPreference();
})();
