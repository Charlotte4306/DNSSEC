# ui_preview — sandbox sửa UI, không cần backend

Bốn asset đầu là bản copy nguyên vẹn từ `https://itscharlotte.tech` (bản đang chạy,
`GET /`, `/static/css/app.css`, `/static/js/app.js`, `/static/js/motion.js`, fonts).
Toàn bộ mock nằm trong `serve.py`. `index.html` và `app.js` sau đó đã bị cắt lại chữ
hiển thị (bỏ hướng dẫn thừa), logic và mọi ID hợp đồng vẫn giữ nguyên.

```powershell
.\.venv\Scripts\python.exe ui_preview\serve.py --port 18790
# mở http://127.0.0.1:18790/
```

Sửa giao diện trực tiếp trong `index.html`, `static/css/app.css`, `static/js/*`, tải lại
trang là thấy. Docker, BIND, Unbound và Flask API đều không cần.

## Fixture

| Kịch bản | Job timeline | Kết quả run | Nguồn |
|---|---|---|---|
| `baseline` | `fixtures/jobs/baseline.json` (25 events) | `runs/f6e5e807…/result.json` | ghi thật từ lab deploy |
| `attack` | `fixtures/jobs/attack.json` (21 events) | `runs/1c84eedb…/result.json` | run thật trong `evidence/`, timeline **phóng tác** |
| `recovery` | `fixtures/jobs/recovery.json` (25 events) | dùng lại run baseline | timeline **phóng tác** |

`attack.json` và `recovery.json` sinh ra từ `baseline.json` bằng `make_fixtures.py`;
chạy lại khi muốn đổi:

```powershell
.\.venv\Scripts\python.exe ui_preview\make_fixtures.py
```

Nghĩa là timeline của hai kịch bản sau chỉ dùng để dựng và test giao diện, không phải
bằng chứng đo được. Số liệu HTTP/DNS trong panel và preview đến từ run thật.

## Hành vi mock

- `POST /api/jobs` → trả `job_id` cố định (`mock-job-attack`…), phát dần ~7 event/giây,
  xong sau ~4.5 giây rồi `completed` kèm `result_url`.
- `GET /api/state` → `revision`, `actual_mode`, `last_run_id`, `busy` luôn khớp run vừa
  hoàn tất, nên UI không đánh dấu stale giả.
- `POST /api/proof` → `revision` lấy theo state hiện tại; payload là `proof.json` đã lưu.
- `GET|HEAD /api/runs/<id>/preview/<branch>` → trả HTML preview đã lưu kèm CSP `sandbox`
  như bản production. Run attack không có `secure.html` vì nhánh đó không gửi HTTP.
- `/api/run`, `/api/scenario` trả 404 có chủ đích: UI production không gọi chúng.

## Lớp kawaii (bản sửa UI)

Lớp kawaii đã được tích hợp vào dashboard production trên nhánh feature/demo-ui-integration. Preview vẫn là công cụ thử giao diện riêng. Ba file mới được nạp **sau** asset gốc:

- `static/css/kawaii.css` — đè palette + hình thái (bo tròn, pastel, bóng dày), không sửa `app.css`
- `static/js/kawaii.js` — nén nút khi ấn, sao bung, badge nảy khi kết quả đổi
- `static/img/kawaii-bg.svg`, `static/img/mascot-shield.svg` — nền và mascot vẽ bằng SVG

`index.html` đổi hai chỗ: thêm hai thẻ link/script, và thay `h1` cũ bằng `.kawaii-banner`
(mascot nhấp nhô, chữ giật theo từng từ, ruy-băng icon chạy, sao lấp lánh).Banner vẫn giữ
`id="intro-title"` và cấu trúc `line-mask / reveal-line` để `motion.js` chạy reveal như cũ.
Mọi ID mà `app.js` đọc đều giữ nguyên.

Ảnh nền raster không dùng được vì ImageGen trả HTTP 403 (hết credit theo gói); nên toàn bộ
nền + mascot là SVG tự viết. Nếu muốn ảnh vẽ thật, cung cấp file PNG/JPG rồi trỏ
`body::before { background: url(...) }` trong `kawaii.css` là xong, khỏi sửa gì khác.

Tắt hiệu ứng: `#motion-toggle` (hoặc hệ thống đặt reduce-motion) sẽ dừng animation và sao bung.

## Replay hình máy tính

Panel `.wire-replay` nằm ngay trên mục "Bằng chứng lần chạy": **tám chiếc máy** vẽ bằng SVG
(`PLAN` trong `static/js/replay.js`), mỗi màn hình là một terminal 2–3 dòng và lệnh được
**gõ dần** theo từng sự kiện, kèm gói tin chạy trên dây và bong kết quả (`AD ✓`, `A→.90`, `∅`).

Hai làn tách hẳn, mỗi làn có máy khách riêng:

| Cột | Trên (không DNSSEC) | Dưới (có DNSSEC) |
|---|---|---|
| Máy khách | `clientP` — laptop, hỏi qua plain | `clientS` — laptop, hỏi qua secure |
| Resolver | `plain` — monitor, bỏ qua chữ ký | `secure` — monitor, đối chiếu RRSIG |

Ở giữa trên là `attacker` (laptop relay), giữa dưới là node **Internet** (`.rp-net-blob`), cột
phải là `bind` + `good` + `fake` (server có khe thông gió và đèn). Ba kiểu vỏ `laptop` /
`monitor` / `server` vẽ trong `buildMachines()`; lúc chưa có dữ liệu vỏ màu **hồng**
(`#fff3f7`), khi có sự kiện mới đổi viền: cobalt (đang xử lý), xanh mint (đúng), hồng đậm (bị
chặn), đỏ + rung cho relay khi `tamper --enable`.

- **Live**: `app.js` phát `CustomEvent("dnssec:event")` cho mỗi mốc job thật → panel vẽ đúng
  thứ tự đã đo. Badge "Phát lại sự kiện thật".
- **Demo**: hover dòng kịch bản hoặc đổi radio → chạy `script[baseline|attack|recovery]` dựng
  sẵn trong `replay.js`. Badge "Minh họa kịch bản" — phần này **phóng tác để xem giao diện**.
  Dòng chữ `relay · BIND: minh họa` cạnh tiêu đề nói rõ hai bước đó không đo từ worker.
- Nút **Phát lại**: nếu trang đang có sự kiện của một phép đo (vừa chạy, hoặc bấm
  "Xem lần chạy gần nhất") thì phát đúng các mốc đó, nhãn đổi thành "Phát lại lần đo";
  khi chưa có gì thì chạy script demo của kịch bản đang chọn, nhãn là "Xem mô phỏng".
  Hover/tap dòng kịch bản và đổi radio cũng dựng lại demo.
- Tắt hiệu ứng (`#motion-toggle` / reduce-motion): màn hình in đủ dòng ngay, gói tin chỉ làm
  sáng dây khoảng 200ms.

Muốn đổi nội dung gõ trên màn hình: sửa `fromEvent()` (live) hoặc mảng `script` (demo) trong
`replay.js`; muốn đổi vị trí/kích thước máy và số dòng terminal: sửa `PLAN`. Dây nối nằm
trong `index.html` (`rp-cp`, `rp-cs`, `rp-pa`, `rp-sa`, `rp-ab` cho DNS). HTTP đi qua node
**Internet** ở giữa: `rp-hpc`/`rp-hsc` xuống từ hai máy khách, `rp-hng`/`rp-hnf` lên Web
thật/Web giả, nên không còn dây vòng quanh mép và không sợi nào cắt nhau. `netHops()` phát
hai chặng liên tiếp (300ms + 260ms); tọa độ hai đầu dây phải khớp cạnh `PLAN` và cạnh blob
`.rp-net-blob` (600,392 · 204×88).

File mới: `static/css/replay.css`, `static/js/replay.js` (nạp sau kawaii, `index.html:12,16`).
Cùng hai file này được chép sang `dashboard/static/` cho app Flask thật; bản đó không có nhãn
`relay · BIND: minh họa` vì relay và BIND đo từ worker — xem `docs/DEMO_UI_INTEGRATION.md`.

## Font

Bản production không dùng font mặc định của trình duyệt: `app.css` tự khai báo
`Be Vietnam Pro` (body + heading) và `Xanh Mono` (nhãn), còn số liệu/IP dùng
`Consolas`. Bản kawaii nạp thêm `static/fonts/nunito-fonts.css` (Nunito tự host,
có dấu tiếng Việt) và đặt lại `font-family` trong `:root`, nên chỉ cần xoá một
trong hai dòng là quay về font gốc:

```html
<link rel="stylesheet" href="/static/fonts/nunito-fonts.css">   <!-- index.html:10 -->
```

```css
:root { font-family: "Nunito", "Be Vietnam Pro", sans-serif; }  /* kawaii.css:20 */
```

Còn một block thứ hai áp Nunito cho heading (`kawaii.css:24-32`, gồm `.intro h1`,
`.lab-heading h2`, `.node text`…); xoá cả hai là về font gốc.

Muốn đổi font khác: thả file `.woff2`/`.ttf` vào `static/fonts/`, viết `@font-face`
theo mẫu `nunito-fonts.css`, rồi sửa tên font trong hai chỗ trên. Ưu tiên font có
subset `vietnamese` để dấu không bị rơi về font hệ thống.

## Thay ảnh / logo

`serve.py` phục vụ mọi file dưới `/static/`, nên thả file vào `static/img/` là dùng được
ngay — tên tự đặt, viết thường và dùng dấu gạch nối, ví dụ `nen.png`, `banner-mascot.png`,
`logo.png`. SVG/PNG/JPG/WEBP đều được. Ba chỗ đang tham chiếu ảnh:

| Vị trí | File hiện tại | Sửa ở đâu |
|---|---|---|
| Nền toàn trang | `static/img/kawaii-bg.svg` | `kawaii.css:39` (`body::before`) |
| Mascot trong banner | `static/img/mascot-shield.svg` | `index.html` thẻ `<img class="banner-mascot">` |
| Icon nhỏ (sao, tim, mây…) | sprite SVG nội tuyến cuối `index.html` | `<symbol id="g-…">` trong `.kawaii-sprite` |

Logo trên header hiện là ký tự text `↳` trong `.brand-symbol`; để thay bằng ảnh thì
thay nội dung thẻ đó bằng `<img src="/static/img/logo.png" alt="DNSSEC Lab">` và giữ
`width/height` khoảng 34px để `masthead` không nhảy. Ảnh nên to gấp 2 lần kích thước
hiển thị (hoặc dùng SVG) để nét trên màn Retina.

## Tích hợp với dashboard thật

Nhánh `feature/demo-ui-integration` giữ backend jobs/events/evidence từ develop và đưa giao diện kawaii vào `dashboard/templates/index.html` cùng các asset `dashboard/static/`. Không copy server mock hoặc fixtures sang production.

`ui_preview/` luôn hiện banner dữ liệu phát lại, mọi phản hồi API dùng `source: mock`, integrity ghi `verified: false`. Timeline attack/recovery là dữ liệu dựng lại; recovery dùng lại run baseline để thử bố cục. Những giá trị này không phải bằng chứng demo mới.

Server chỉ đọc file static bên trong `ui_preview/static` sau khi resolve đường dẫn. Cursor của job đã kết thúc vẫn lọc sự kiện và yêu cầu chạy chồng nhau trả 409.

Kiểm tra server preview:

```powershell
python -m unittest discover -s tests/preview -v
```

Khi chỉnh logic live, cập nhật bản app.js trong preview theo hợp đồng mock và chạy lại kiểm thử. Không thay app.js production bằng bản chấp nhận mock. Nunito, Be Vietnam Pro và Xanh Mono đều được kèm giấy phép OFL trong static/fonts.
