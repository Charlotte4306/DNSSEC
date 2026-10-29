# Feature dns-http-worker

## Phạm vi đã hoàn thành

Theo GITFLOW.md: hỏi DNS qua resolver chỉ định → HTTP tới chính IP nhận được →
xuất JSON. Plain phải truy cập được trang giả khi phản hồi bị sửa; secure dừng ở
DNS và không gửi HTTP. Đây chưa phải dashboard hoặc Flask REST API.

## 1. Luồng xử lý

`lab/browse.py` thực hiện một nhánh:

1. Kiểm tra tên lab, resolver và run_id.
2. Gọi probe với đúng server, không dùng DNS hệ điều hành và không fallback resolver khác.
3. DNS lỗi/rcode khác NOERROR thì HTTP attempted=false; không có body cũ.
4. Riêng secure: NOERROR còn phải có AD trong ngữ cảnh tin resolver của lab.
5. Chỉ nhận đúng một A thuộc tập IP web của lab, rồi gọi visit với IP đó và Host đúng tên.
6. Giữ status/IP/site_id/body thật; phân biệt lỗi DNS và lỗi HTTP.

`lab/api_worker.py` là giao diện dòng lệnh JSON cho backend tương lai. Mỗi lần
compare dùng chung run_id cho hai nhánh, branch_id là plain/secure; hai nhánh chạy
song song và được chờ hoàn tất trước khi trả JSON.

## 2. Chạy thử

```powershell
.\dns.ps1 baseline
.\worker.ps1 compare
.\dns.ps1 attack
.\worker.ps1 compare
.\dns.ps1 recover
```

Muốn gọi trực tiếp và đặt mã lần thử:

```powershell
docker compose exec -T client python /app/lab/api_worker.py compare --run-id my-worker-check
docker compose exec -T client python /app/lab/api_worker.py visit --resolver secure --run-id my-secure-check
```

Chỉ nhận tên lab và resolver trong danh sách. run_id dài 1–80 ký tự chữ, số,
gạch ngang/gạch dưới; không nhận chuỗi header tùy ý.

## 3. Hợp đồng JSON

Compare trả `schema_version`, `run_id`, `target`, `scenario_before`,
`scenario_after`, `consistent` và `results.plain`/`results.secure`.
Mỗi nhánh có resolver, branch_id, requested_at/finished_at, dns, http,
stop_reason và interpretation.

| Nhóm | Trường quan trọng |
|---|---|
| dns | server, rcode, ad, aa, answers, raw, error, elapsed_ms |
| http | attempted, request_sent, connected_ip, status, site_id, body, body_sha256, error |
| interpretation | validated / reached_legitimate_unvalidated / accepted_fake / blocked / inconclusive |

`blocked` chỉ có nghĩa dừng ở DNS; không tự kết luận lỗi mật mã chỉ từ SERVFAIL.
Muốn giải thích chữ ký không khớp phải kết hợp log và proof của dns-core.
Nếu HTTP lỗi sau DNS thành công, giữ nguyên kết quả DNS và stop_reason=HTTP_ERROR.

CLI api_worker trả mã 0 khi đo được kết quả hợp lệ, kể cả resolver từ chối DNS.
Timeout/lỗi thực thi hoặc kết quả trộn chế độ trả mã 1. Backend phải đọc JSON để
hiểu kết quả, không xem mã thoát 0 là website đã truy cập thành công.
CLI browse cũ vẫn trả mã 1 khi không tải được website, dùng cho kiểm tra thủ công.

## 4. Giới hạn đồng bộ ở feature này

Worker đọc mode trước và sau phép thử. Khi phát hiện thay đổi, consistent=false
và hai interpretation thành inconclusive. Worker không đổi mode hoặc flush cache;
dùng dns.ps1 trước khi chạy. Trong chặng này chỉ một người điều khiển kịch bản.

Đọc snapshot không phải khóa giao dịch. Việc khóa xuyên suốt đổi mode và phép đo
sẽ được triển khai trong feature/dashboard-api; không tuyên bố đã có khóa ở đây.

## 5. Kiểm thử và bằng chứng

```powershell
.\worker.ps1 test
```

Script đặt baseline, chạy 25 test, rồi kiểm tra ba trạng thái và access log.
Mỗi trạng thái có run_id duy nhất, evidence tại:

```text
evidence/runs/worker-<phase>-<id>/
  result.json       # JSON worker thực tế
  http-access.json  # log hai website đã lọc theo run_id
```

Các file runtime bị gitignore. Sao lưu những lần cần đưa vào báo cáo trước khi
dọn môi trường; không tạo evidence giả.

Kết quả đã chạy ngày 29/10/2026:

| Trạng thái | Plain | Secure | HTTP log cùng run_id |
|---|---|---|---|
| Baseline | .80, HTTP 200, legitimate | .80, HTTP 200, AD=true, legitimate | Đúng 2 request, mỗi nhánh 1 |
| Attack | .90, HTTP 200, training-fake | SERVFAIL, attempted=false, body=null | Đúng 1 request của plain; không secure |
| Recovery | .80, HTTP 200, legitimate | .80, HTTP 200, AD=true, legitimate | Đúng 2 request, mỗi nhánh 1 |

Access log còn kiểm tra Host=www.demo.test, path=/, site_id và status khớp kết quả
worker. Không chỉ nhìn UI/body trống để khẳng định chưa có HTTP.

25 unit/integration test đều đạt. 7 test worker mới kiểm tra chặn SERVFAIL,
không fallback, secure yêu cầu AD, dùng đúng IP từ DNS, phân biệt lỗi HTTP,
run_id không hợp lệ, thay mode giữa phép đo và không dùng lại body từ lần trước.
Các tình huống lỗi này dùng mock; ba kịch bản chính dùng DNS và HTTP thực tế.

Cuối script luôn cố recover. Nếu môi trường bị lỗi, cần đọc thông báo và kiểm
tra lại actual mode; finally không bảo đảm hạ tầng luôn phục hồi được.

## 6. Điều chưa làm trong feature này

Chưa có Flask API, khóa điều phối toàn cục, preview HTML hoặc animation. Trình
duyệt người xem chưa dùng DNS lab trực tiếp: HTTP được thực hiện bởi client Docker.
Không tự mở rộng tên miền, redirect hoặc IP ngoài lab. Giữ nguyên giới hạn mô phỏng
và trust anchor cục bộ của dns-core.

## 7. Review và bàn giao

Đọc browse.py trước để hiểu điều kiện cho phép HTTP, rồi api_worker.py và worker.ps1.
Review diff, commit trên feature/dns-http-worker, push và PR vào develop.
Không tự tạo nhánh tính năng mới trước khi chốt PR này.
