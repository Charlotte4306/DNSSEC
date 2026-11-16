"use strict";
(() => {
  const output=document.querySelector('#terminal-output'),input=document.querySelector('#terminal-input'),status=document.querySelector('#terminal-status'),submit=document.querySelector('#terminal-submit');
  let busy=false,locked=true,uncertain=false,entries=[],history=[],cursor=0,draft='';
  const help=`Tự nhập lệnh DNS trong zone demo.test:
dig @secure www.demo.test A +dnssec
dig @plain www.demo.test A +short
dig @relay www.demo.test A +dnssec +multi
dig @authority demo.test DNSKEY +dnssec
dig @secure www.demo.test A +dnssec +cdflag
dig @secure not-present.demo.test A +dnssec
logs secure tamper --tail 40

Resolver: @secure / @plain / @relay / @authority, hoặc IP lab tương ứng.
Loại: A AAAA DNSKEY RRSIG DS NSEC NSEC3 SOA NS TXT CNAME MX ANY CAA SRV PTR HTTPS.
Tùy chọn: +dnssec +nodnssec +tcp +notcp +cdflag +nocdflag +short +noshort
+multi +nomulti +norecurse +recurse +noall +all +answer +noanswer
+comments +nocomments +stats +nostats +authority +noauthority
+additional +noadditional +question +noquestion +rrcomments +ttlunits.
logs [secure plain tamper authority web-good web-fake] --tail 1..200
help / history / clear là lệnh tại trình duyệt.
↑ / ↓: lịch sử; Enter: chạy; Ctrl+L: xóa màn hình.
Mỗi lệnh hoàn tất mới hiển thị đầu ra. Shell đầy đủ dùng SSH riêng.`;
  function controls(){submit.disabled=busy;input.readOnly=busy;document.querySelector('#terminal-clear').disabled=busy;}
  function render(){
    output.replaceChildren();
    if(!entries.length){const p=document.createElement('pre');p.textContent='DNSSEC lab console\nNhập lệnh bên dưới rồi Enter. Gõ help để xem cú pháp.\nCác lệnh kiểm tra giữ nguyên kịch bản trên overview.';output.append(p);}
    for(const entry of entries){
      const a=document.createElement('article');a.className='terminal-entry';
      const prompt=document.createElement('p');prompt.className='terminal-prompt';prompt.textContent=`lab@${entry.executed_in||'console'}:~$ ${entry.command}`;a.append(prompt);
      if(entry.requested_at){const meta=document.createElement('p');meta.className='terminal-meta';meta.textContent=new Date(entry.requested_at).toLocaleString('vi-VN')+' · truy vấn bổ sung';a.append(meta);}
      const pre=document.createElement('pre');pre.textContent=entry.stdout||'';a.append(pre);
      if(entry.error||entry.stderr){const err=document.createElement('pre');err.className='terminal-error';err.textContent=entry.error||entry.stderr;a.append(err);}
      if(entry.exit_code!==undefined){const end=document.createElement('p');end.className='terminal-exit';end.textContent=`exit ${entry.exit_code} · ${entry.elapsed_ms} ms${entry.timed_out?' · quá thời gian':''}${entry.truncated?' · đầu ra giới hạn 32 KiB':''}${entry.output_complete===false?' · đầu ra chưa đầy đủ':''}${entry.consistent===false?' · mode đã thay đổi':''}`;a.append(end);}
      output.append(a);
    }
    output.scrollTop=output.scrollHeight;
  }
  function append(entry){entries.push(entry);entries=entries.slice(-30);render();}
  async function run(command){
    if(busy)return;
    history.push(command);history=history.slice(-100);cursor=history.length;draft='';input.value='';
    if(command==='clear'){entries=[];render();return;}
    if(command==='help'){append({command,stdout:help});return;}
    if(command==='history'){append({command,stdout:history.map((c,i)=>`${i+1}  ${c}`).join('\n')});return;}
    if(locked||uncertain){append({command,error:'Lab chưa sẵn sàng hoặc đang bận. Chờ trạng thái lab rồi chạy lại.'});return;}
    busy=true;controls();status.textContent='Đang thực thi lệnh trong lab…';window.dispatchEvent(new CustomEvent('dnssec:terminal-busy',{detail:true}));
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch('/api/terminal/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command}),signal:controller.signal,cache:'no-store',credentials:'same-origin'});
      const data=await response.json();
      if(!response.ok){const error=new Error(data.error?.message||`HTTP ${response.status}`);error.code=data.error?.code;throw error;}
      if(data.source!=='live'||data.kind!=='supplementary_command'||data.command!==command||typeof data.stdout!=='string'||typeof data.stderr!=='string')throw new Error('Phản hồi không khớp lệnh đã nhập.');
      append(data);status.textContent=data.timed_out?'Lệnh quá thời gian; xem đầu ra thu được.':data.consistent===false?'Mode đã đổi trong khi kiểm tra.':`Lệnh hoàn tất · exit ${data.exit_code}. Đọc RCODE/AD để hiểu kết quả DNS.`;
    }catch(error){uncertain=!error.code;append({command,error:error.message||'Mất kết nối API'});status.textContent=uncertain?'Chưa xác nhận lệnh hoàn tất; đang kiểm tra lại lab. Không tự gửi lại lệnh.':error.message;}
    finally{clearTimeout(timer);busy=false;controls();window.dispatchEvent(new CustomEvent('dnssec:terminal-busy',{detail:false}));if(document.documentElement.dataset.screen==='terminal')input.focus({preventScroll:true});}
  }
  document.querySelector('#terminal-form').addEventListener('submit',e=>{e.preventDefault();const command=input.value.trim();if(command)run(command);});
  input.addEventListener('keydown',e=>{
    if(busy)return;
    if(e.ctrlKey&&e.key.toLowerCase()==='l'){e.preventDefault();entries=[];render();}
    if(e.key==='ArrowUp'){e.preventDefault();if(cursor===history.length)draft=input.value;cursor=Math.max(0,cursor-1);input.value=history[cursor]||draft;}
    if(e.key==='ArrowDown'){e.preventDefault();cursor=Math.min(history.length,cursor+1);input.value=cursor===history.length?draft:history[cursor];}
  });
  addEventListener('dnssec:state',({detail})=>{locked=detail.locked||!detail.ready;if(!busy&&!locked)uncertain=false;controls();if(!busy&&!uncertain)status.textContent=locked?'Lab chưa sẵn sàng hoặc đang có tác vụ. Có thể nhập help để xem hướng dẫn.':'Sẵn sàng · tự nhập lệnh DNS để kiểm chứng lab.';});
  document.querySelector('#terminal-clear').addEventListener('click',()=>{entries=[];render();input.focus();});
  document.querySelector('#terminal-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(output.innerText);status.textContent='Đã sao chép đầu ra.';}catch{status.textContent='Chọn chữ trong terminal để sao chép.';}});
  controls();render();
})();

