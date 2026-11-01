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

Bản production không bị đụng tới. Ba file mới được nạp **sau** asset gốc:

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

## Khi muốn lên bản thật

Bản deploy lớn hơn mọi nhánh trong repo (`app.js` 30 KB so với 18.7 KB ở
`feature/dashboard-layout`) và có `/api/jobs`; code đó chưa có trong Git. Muốn chỉnh sửa
này thành bản chính thức thì copy `index.html` → `dashboard/templates/`, `static/` →
`dashboard/static/`, và giữ nguyên tên file.
