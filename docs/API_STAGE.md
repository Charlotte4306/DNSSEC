# Backend API — DNSSEC Visual Lab

`feature/dashboard-api` triển khai Flask trên host, gọi Docker CLI để chạy worker
thật trong container client. Nhánh này chưa nối giao diện; trang `/` chỉ mô tả
dịch vụ API. Layout và tích hợp live cùng nằm trên `feature/dashboard-layout`.
Không mount Docker socket vào web container.

## Chạy

Từ thư mục gốc repo, Docker Desktop đang chạy Linux containers và lab đã build:

```powershell
docker compose up -d --build
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\.venv\Scripts\python.exe dashboard/app.py --port 8080
```

Nếu đã có `.venv`, dùng lại; không cần tạo lại. Trong phiên phát triển hiện tại
đã tạo `.venv` và cài phụ thuộc. Nếu Windows chặn cổng 8080 hoặc cổng đang bận,
dùng `--port 18766`, đồng thời đổi URL gọi API. Ctrl+C dừng server. Không mở thêm
server cho cùng checkout: file lock chặn cả trường hợp chọn cổng khác. Chạy đúng
entrypoint này, một process, tắt debug/reloader; không chạy nhiều WSGI worker.

Server bind `127.0.0.1`, chỉ nhận Host localhost/loopback. POST cần JSON; request
từ Origin khác hoặc Sec-Fetch-Site cross-site bị từ chối. Không mở CORS.
Flask server này dùng cho demo cục bộ.

Mở terminal PowerShell khác:

```powershell
$apiBase = 'http://127.0.0.1:18766'
Invoke-RestMethod "$apiBase/api/health"
Invoke-RestMethod "$apiBase/api/state"

Invoke-RestMethod -Method Post "$apiBase/api/scenario" -ContentType 'application/json' -Body '{"action":"baseline"}'
$baselineRun = Invoke-RestMethod -Method Post "$apiBase/api/run" -ContentType 'application/json' -Body '{}'
$baselineRun.results | ConvertTo-Json -Depth 15

Invoke-RestMethod -Method Post "$apiBase/api/scenario" -ContentType 'application/json' -Body '{"action":"attack"}'
$attackRun = Invoke-RestMethod -Method Post "$apiBase/api/run" -ContentType 'application/json' -Body '{}'
$attackRun.results | ConvertTo-Json -Depth 15
Invoke-RestMethod -Method Post "$apiBase/api/proof" -ContentType 'application/json' -Body '{}'

Invoke-RestMethod -Method Post "$apiBase/api/scenario" -ContentType 'application/json' -Body '{"action":"recovery"}'
$recoveryRun = Invoke-RestMethod -Method Post "$apiBase/api/run" -ContentType 'application/json' -Body '{}'
```

`$apiBase` phải dùng cùng cổng đã chọn khi chạy server. Baseline/recovery có hai
HTTP request tới `.80`; attack có plain tới `.90`, secure SERVFAIL không HTTP.
Đổi scenario chỉ đổi mode và flush; phải gọi `/api/run` để kiểm chứng DNS→HTTP.

## Hợp đồng endpoint hiện đã triển khai

| Endpoint | Đầu vào | Kết quả |
|---|---|---|
| GET `/api/health` | Không | `source: live`, trạng thái bảy dịch vụ; 200 khi running và không unhealthy/starting, 503 nếu chưa sẵn sàng. Không tự truy vấn DNS. |
| GET `/api/state` | Không | `actual_mode: normal/attack/unknown`, revision từ relay, busy, last_task có run_id khi đo, last_error, ready_for_run. |
| POST `/api/scenario` | `{"action":"baseline/attack/recovery"}` | Đổi relay, flush plain rồi secure, đọc lại mode; trả các bước đã thành công và revision. |
| POST `/api/run` | `{}` hoặc `{"target":"www.demo.test"}` | Hai nhánh cùng run_id, source live, revision, DNS/HTTP thực, đối chiếu access log, URL preview. |
| POST `/api/proof` | `{}` | Đọc A/RRSIG từ authority và relay thật; đối chiếu chữ ký; revision trước/sau phải khớp. |
| GET `/api/runs/<id>` | ID hợp lệ | Kết quả JSON đã lưu; 404 nếu thiếu hoặc chưa hoàn thành. |
| GET `/api/runs/<id>/preview/<branch>` | plain/secure | HTML đã làm sạch từ body worker từng tải; 404 nếu không có HTTP thành công hoặc mode không nhất quán. Không gửi HTTP mới. |

Mọi kết quả API và lỗi đều JSON, trừ preview là HTML. Lỗi có
`error.code`, `error.message`, tùy ca có `error.details`. Trường/lệnh/tên miền lạ
bị từ chối. Giới hạn request 4 KiB. Caller không được cấp run_id hay câu lệnh.

| Mã | Ý nghĩa |
|---|---|
| 400 / 415 | Đầu vào, JSON hoặc Content-Type không hợp lệ. |
| 403 | Host/Origin không được chấp nhận. |
| 404 | Run/preview không tồn tại. |
| 409 | Lab bận, chưa chuẩn bị scenario hoặc mode xung đột. |
| 502 | JSON/schema worker sai. |
| 503 / 504 | Docker/dịch vụ/thao tác lỗi hoặc timeout. |
| 500 | Lỗi nội bộ/lưu evidence; xem terminal, không tự tạo kết quả thay thế. |

200 ở `/api/run` nghĩa là có một phép đo được ghi nhận, không có nghĩa mọi nhánh
đều HTTP 200 hoặc demo đã đạt. DNS/HTTP lỗi nằm trong từng nhánh. Nếu mode đổi
trong lúc đo, vẫn lưu kết quả với `consistent: false`, interpretation inconclusive
và không cấp preview. Đọc các trường kết quả thay vì chỉ nhìn HTTP status API.

## Ba kiến thức trọng tâm

### 1. Flask chỉ điều phối, client mới thực hiện DNS và HTTP

`docker_runner.py` dùng `subprocess.run` với danh sách đối số, `shell=False`,
repo root cố định và timeout. Chỉ có các lệnh đã viết sẵn: đọc mode, đổi on/off,
flush resolver, worker compare, proof và log. Worker tiếp tục dùng đúng IP nhận
từ DNS, không dùng DNS hệ điều hành host và không fallback khi secure lỗi.
Worker exit 1 có thể là một phép đo DNS/HTTP lỗi hợp lệ; backend vẫn giữ JSON đó.

### 2. Khóa tác vụ tránh trộn kịch bản

`scenario_service.py` dùng một lock cho toàn bộ scenario/run/proof, bao gồm thời
gian thu log và lưu evidence. Request xung đột nhận 409 ngay. State vẫn đọc được
để UI báo busy. Đổi mode phải flush cả hai resolver rồi mới đặt ready_for_run.
Nếu flush lỗi giữa chừng, API trả các bước đã làm, readiness bị hủy; mode thực
có thể đã đổi. Không nói đã rollback nếu chưa rollback thật.

Mỗi lần khởi động API cần chuẩn bị scenario qua API. Snapshot `changed_at` của
relay làm revision; run so khớp trước/worker/sau. Các snapshot phát hiện đổi mode
ngoài API nhưng không khóa được người chạy `dns.ps1` hay Docker CLI trực tiếp.
Trong buổi demo dùng một API server, không đồng thời thao tác CLI đổi mode/flush.
`ready_for_run` nói scenario đã được API chuẩn bị, không thay thế `/api/health`.

API hiện chạy đồng bộ, mỗi Docker command có timeout (25 giây; health/log 10
giây). Đóng tab hoặc hủy fetch không hủy worker; tác vụ có thể vẫn hoàn tất.
UI live phải theo dõi state/last_task/run_id, không tuyên bố đã dừng lab chỉ vì
ngừng chờ HTTP. Khi Docker timeout, không chắc tiến trình bên trong container
đã dừng; kiểm tra lab và chuẩn bị recovery lại trước khi tiếp tục.

### 3. Kết quả và bằng chứng là hai lớp

`observed_interpretation` giữ nhận xét của worker. `interpretation` chỉ giữ kết
luận tương ứng nếu có bằng chứng phù hợp: HTTP thành công cần access log khớp
run_id, branch_id, Host, path, status và site_id. Thiếu log → inconclusive.
Worker báo không HTTP nhưng có access log cùng nhánh cũng → inconclusive.

Access log được đọc lại trong tối đa hai giây chờ Docker hiển thị bản ghi.
Bộ đọc xử lý được hai JSON liền nhau trên một dòng do web server đa luồng ghi
đồng thời. Không thu được log khác với không có request: lỗi thu log làm các
trường đếm/không quan sát HTTP thành null, không giả số 0.

`no_http_observed` chỉ nói worker không thử HTTP và không thấy access log trong
cửa sổ thu thập; không phải chứng minh tuyệt đối rằng không có lưu lượng mạng.
Log secure/relay chỉ gắn theo thời gian, ghi rõ
`dns_context_correlation: time_window_only_not_exact_run_id`. SERVFAIL vẫn mang
nghĩa DNS từ chối/chưa xác định nguyên nhân; không tự nâng thành lỗi chữ ký.
`/api/proof` và log xác thực giúp đối chiếu nguyên nhân khi trình bày.

## Evidence và preview

```text
evidence/runs/<uuid>/
  worker.json           # JSON gốc, gồm DNS raw và body HTTP gốc
  http-access.json      # chỉ các access log cùng run_id
  dns-context.log       # log DNS theo cửa sổ thời gian, có giới hạn tail
  preview-plain.html    # chỉ tạo khi có body HTTP 200
  preview-secure.html   # không có ở nhánh SERVFAIL
  result.json           # xuất bản sau cùng, kết quả + bằng chứng cho API
```

API không gắn body gốc vào JSON UI; trả `body_hash/body_sha256`, body_available
và preview_url. HTML gốc vẫn nằm trong worker.json để đối chiếu. Preview loại
script/style/head nguồn, lọc allowlist thẻ và bỏ toàn bộ thuộc tính/URL ngoài;
thêm CSS cố định của lab. Vì vậy hình thức có thể khác trang gốc, nội dung vẫn
lấy từ HTTP worker thật. CSP sandbox/default-src none chặn script, form, mạng
ngoài; frontend phải tiếp tục dùng iframe sandbox rỗng. Không có request mới khi
xem preview. UUID được kiểm tra, không nhận đường dẫn tùy ý.

## Kiểm thử đã chạy

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/dashboard -p test_api.py -v
.\.venv\Scripts\python.exe tests/dashboard/integration_api.py
```

Lệnh đầu: 17 test dùng runner giả cho các ca lỗi, khóa đồng thời, validation,
thiếu log, JSON liền nhau, sanitizer và timeout. Lệnh sau: Flask test client gọi
route thật với Docker runner thật, không mock DNS/HTTP; cần lab đang chạy, API
server đã dừng để tránh thao tác song song. Test tự khôi phục mode/flush cuối.
Các test API nằm riêng để test discovery trong image client không cần Flask.

Kết quả vòng thực nghiệm cuối:

| Ca | Run ID | Kết quả |
|---|---|---|
| Baseline | `5878ba65-5d78-4576-b6de-6153dd5a3713` | Hai HTTP tới trang đúng, secure AD, hai access log. |
| Attack | `1ad55abe-9e53-4787-905e-2aca86285251` | Plain tới trang giả, một access log; secure SERVFAIL, không HTTP/preview; proof giữ nguyên RRSIG, log có signature crypto failed. |
| Recovery | `1a2c71a6-e877-4b2e-af5a-adf5fb55a928` | Hai HTTP trở về trang đúng, hai access log, không preview giả cũ. |

Evidence runtime đã lưu trên máy, không commit. Đã kiểm tra thêm GET health/state qua HTTP localhost, POST khác Origin trả 403 và chặn server thứ hai dù dùng cổng khác. Server kiểm thử đã dừng. Giao diện live, kiểm thử toàn bộ
UI→API và nghiệm thu cuối nằm ở các bước sau; chưa gọi dashboard live hoàn tất.

## Nguồn kỹ thuật

- [Flask: kiểm thử bằng test client](https://flask.palletsprojects.com/en/stable/testing/).
- [Bleach: làm sạch HTML fragment và phạm vi sử dụng](https://bleach.readthedocs.io/en/latest/clean.html).

## Mốc commit và phần còn lại

Feature backend có thể commit/review sau khi kiểm tra diff. Không tự commit/push.
PR `feature/dashboard-api` → `develop`. Sau khi merge, trở lại
`feature/dashboard-layout`, fetch/merge develop và triển khai tích hợp live trên
chính nhánh đó theo GitFlow đã cập nhật.


## Bổ sung ở feature/evidence-tests

POST /api/run tự lấy proof trong lock và lưu proof.json nếu thu được; mỗi run
mới có checksums.json. GET /api/runs/<id>/integrity trả verified/status/tập tệp,
HTTP 200 chỉ nghĩa là trả được kết quả kiểm tra, phải đọc verified. Run mới bị
đổi/mất artifact sẽ bị GET result/preview từ chối 409 EVIDENCE_CORRUPT. Run cũ
không có manifest vẫn đọc được nhưng integrity là unavailable, không được coi
là đã xác minh. Chi tiết ở [EVIDENCE_STAGE.md](EVIDENCE_STAGE.md).
