# Dashboard live — bố cục và tích hợp API trên cùng nhánh

`feature/dashboard-layout` bao gồm cả giao diện và nối API theo GitFlow đã thống
nhất. Flask phục vụ trang HTML, static asset và API cùng origin. Dữ liệu màn hình
đến từ worker DNS→HTTP thật trong Docker; không còn nạp mock-data.js, không có
fallback sang fixture khi API lỗi. Animation vẫn chỉ là minh họa luồng xử lý.

## Chạy và demo

Từ thư mục gốc repo, Docker Desktop chạy Linux containers:

```powershell
docker compose up -d --build
# Nếu đã có .venv, dùng lại và bỏ qua lệnh tạo môi trường:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe dashboard/app.py --port 18766
```

Mở http://127.0.0.1:18766/. Không dùng static server `python -m http.server`;
UI live cần Flask/API. Cổng mặc định app là 8080; ví dụ chọn 18766 để tránh cổng
bị chặn/bận trên máy hiện tại. Chạy một server, dừng bằng Ctrl+C.

1. Chờ badge báo dữ liệu thật và trạng thái relay. Nút **Kiểm tra lab** đọc lại
   health/state; giao diện cũng tự kiểm tra mỗi năm giây khi tab đang hiển thị.
2. Chọn **Bình thường**, bấm **Truy vấn và truy cập**. UI gọi scenario baseline,
   flush hai resolver rồi run. Cả hai nhánh nhận `.80`, HTTP 200; secure có AD.
3. Chọn **Can thiệp**. Kết quả trước bị đánh dấu cũ và preview được gỡ ngay.
   Việc chọn chưa đổi relay. Bấm chạy mới bật can thiệp, flush và đo lại.
4. Plain nhận `.90`, kết nối HTTP tới `.90`, site_id training-fake và có access
   log cùng run_id. Secure SERVFAIL, attempted=false, không có iframe preview.
5. **Xem vì sao** mở JSON DNS/HTTP và log. **Đối chiếu A và RRSIG** lấy dữ liệu
   bổ sung thật: authority `.80`, relay `.90`, chữ ký giữ nguyên. Bằng chứng này
   cùng revision, không tuyên bố thuộc chính gói DNS của phép đo trước.
6. Chọn **Khôi phục**, bấm chạy. Hai nhánh trở về `.80`, không dùng trang giả cũ.
   Sao chép/tải JSON nếu cần đối chiếu. Evidence thật đã lưu trong evidence/runs.

## Kiến thức trọng tâm của phần nối UI

### UI không tự truy cập website theo tên miền

Nút chạy gọi POST `/api/scenario` rồi POST `/api/run`. BIND, relay, Unbound và
worker vẫn xử lý DNS/HTTP trong Docker. UI dùng schema thật `interpretation`,
`scenario_revision`, DNS raw và dữ liệu HTTP; không dùng classification từ fixture
cũ. Chỉ JSON có source live, run_id và hai nhánh khớp được render.

Preview dùng URL `/api/runs/<id>/preview/plain|secure` đúng với run_id/branch,
kiểm tra HEAD trước khi mở iframe sandbox rỗng. Nội dung là bản HTML worker đã
tải và backend đã làm sạch, không phải dựng lại một trang mẫu theo site_id.
Không đặt HTML từ API vào DOM dashboard hay iframe srcdoc. HEAD/GET preview chỉ
đọc evidence, không tạo request HTTP mới tới web-good/web-fake.

### Kết quả cũ không phải trạng thái hiện tại

UI giữ `generation` cho mỗi kết quả. Khi chọn kịch bản khác hoặc polling thấy
revision thay đổi, generation tăng, preview cũ được gỡ và các phản hồi preview
muộn không được chèn lại. JSON cũ vẫn xem/tải được nhưng ghi Lần đo trước.
Phép đo có consistent=false không hiện preview và yêu cầu chạy lại.

Badge relay lấy actual_mode từ API, không suy từ radio đang chọn. Radio thể
hiện kịch bản sẽ chạy; relay chỉ thay đổi khi gửi lệnh chạy. Thời gian DNS/HTTP
hiển thị là elapsed_ms do worker đo, tách khỏi tốc độ nét đứt trên sơ đồ.

### Không coi mất kết nối là đã hủy lab

Không có nút Hủy giả lập của bản mock. Trong lúc chạy, khóa nút thay kịch bản và
không cho gửi tác vụ xung đột. POST có thời hạn chờ 130 giây; mất kết nối hoặc
timeout chỉ nói chưa xác nhận được kết quả. Worker có thể vẫn tiếp tục.

UI kiểm tra busy/last_run_id qua state. **Xem lần chạy gần nhất** trong vùng
bằng chứng mở lại phép đo đã lưu, có nhãn đang xem lại và không gửi truy vấn mới.
Backend giữ last_run_id riêng, kể cả khi tác vụ mới nhất là proof. Metadata này
ở RAM: khởi động lại API không tự tìm lần chạy gần nhất trên đĩa, dù các run cũ
vẫn truy xuất được bằng ID. UI không tự đổi sang một kết quả mẫu khi API hỏng.

## Tệp liên quan

| Tệp | Vai trò |
|---|---|
| dashboard/app.py | Flask render trang `/`, phục vụ `/static` và API cùng origin. |
| dashboard/templates/index.html | Điều khiển lab, sơ đồ, hai panel, bằng chứng và xem lại lần đo. |
| dashboard/static/js/app.js | Gọi API, trạng thái chờ/lỗi, validation/adapter dữ liệu, polling, stale, iframe và export JSON. |
| dashboard/static/css/app.css | Giữ thiết kế xanh xám, bố cục hai cột, responsive và reduced motion. |
| dashboard/services/scenario_service.py | Bổ sung last_run_id, không mất ID lần đo khi lấy proof. |
| dashboard/services/evidence_service.py | CSS preview gọn để đọc nội dung thật trên panel; sanitizer/CSP giữ nguyên chức năng. |
| tests/check_dashboard_layout.cjs | Thay test mock cũ bằng test trình duyệt → Flask → Docker thật. |

Mock fixture cũ đã bỏ. Không có endpoint nhận lệnh Docker hoặc URL tùy ý.
Scope API, lock và giới hạn tương quan log được giải thích ở [API_STAGE.md](API_STAGE.md).

## Kiểm tra

API unit test trên host:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/dashboard -p test_api.py -v
```

Kiểm thử trình duyệt cần Node.js, Playwright và Microsoft Edge. Công cụ nằm
ngoài repo, không cần cho người chỉ chạy dashboard:

```powershell
npm install --prefix "$env:TEMP\dnssec-ui-tools" playwright
$env:NODE_PATH = "$env:TEMP\dnssec-ui-tools\node_modules"
node tests/check_dashboard_layout.cjs
```

Đóng API server đang chạy trước lệnh test browser. Script tự mở Flask trên cổng
tạm, dùng .venv, thực hiện baseline/attack/recovery qua các nút UI thật, lấy
proof, kiểm tra iframe/JSON/access log và tự khôi phục relay/flush khi xong.
Ảnh lưu ở `$env:TEMP\dnssec-live-review` hoặc biến LAYOUT_ARTIFACTS. Có thể đặt
LAB_PYTHON và EDGE_PATH khi Python/Edge nằm ở vị trí khác.

Chỉ các ca lỗi UI ở phần cuối test mới intercept API có chủ đích: 503, health
chưa sẵn sàng, API mất kết nối. Chúng kiểm tra hiển thị lỗi, không được dùng làm
bằng chứng thực nghiệm DNSSEC. Ba kịch bản chính và thử đổi revision từ ngoài
đều dùng Docker thật. Không dừng Docker thật để mô phỏng lỗi UI.

Các điểm cần nghiệm thu: plain thật đến trang giả khi can thiệp, secure không
HTTP/preview, proof khớp A/RRSIG, xem lại sau reload, preview cũ bị gỡ khi đổi mode,
trạng thái lỗi không có fallback, màn hình 1366×768 và 390×844 không tràn ngang.

## Git

Phần API từ develop đã được đưa vào bằng merge --no-commit; không có commit do
agent tạo. README đã giải quyết xung đột và đánh dấu resolved. Kiểm tra toàn bộ
diff, stage các tệp cập nhật rồi bạn tự commit để kết thúc merge. PR của nhánh
dashboard-layout vào develop sẽ gồm phần UI live còn lại; API đã có trên develop.

## Kết quả kiểm tra thực tế

Đã chạy 18 API unit test và 16 nhóm kiểm tra trình duyệt. Ba ca chính đi qua
UI → Flask → Docker → DNS → HTTP thật, không intercept dữ liệu:

| Kịch bản | Run ID | Access log HTTP |
|---|---|---|
| Baseline | 3a43d07f-5d5e-4f8f-a0a4-7fcac1f5848f | 2 request đến trang hợp lệ. |
| Attack | ec351c74-556d-4155-8cf7-347272b204ba | 1 request plain đến trang giả; secure không HTTP/preview. |
| Recovery | b0c0287c-33f0-4bbb-bdac-2e305280a5d1 | 2 request trở về trang hợp lệ. |

Đã kiểm tra proof A/RRSIG thật, tải JSON, mở lại sau reload/proof, đổi mode từ
ngoài để kiểm tra stale, lỗi API không fallback, trạng thái health chưa sẵn sàng,
API mất kết nối, không có lỗi JavaScript hoặc request mạng ngoài. Hai panel kết
quả vừa 1366×768; mobile 390×844 không tràn ngang. Đã mở ảnh desktop/mobile để
review; evidence/log dài cần mở rộng hoặc cuộn. Sau test đã khôi phục mode và
flush hai resolver. Kiểm thử cuối qua máy chiếu và trình đọc màn hình chưa chạy.