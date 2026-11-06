# Diễn tiến DNS → HTTP từ hoạt động thật

## Chạy local

```powershell
docker compose build client
docker compose up -d --no-deps client
.venv/Scripts/python.exe dashboard/app.py --port 18766
```

Mở http://127.0.0.1:18766/#lab. Dashboard cần một tiến trình điều phối; không chạy nhiều API worker độc lập. Lock process có sẵn bảo vệ lần khởi chạy bằng CLI. Bản này chưa được đẩy lên VPS.

## Worker và hợp đồng sự kiện

CLI JSON cũ giữ nguyên. Thêm `--events` để nhận NDJSON được flush ngay:

```powershell
docker compose exec -T client python -u /app/lab/api_worker.py compare --name www.demo.test --run-id test-events --events
```

Hai thread plain/secure dùng cùng run_id, khóa chung khi ghi stdout. Mỗi dòng là một object độc lập, `type=event`, `kind`, `branch`, `timestamp` UTC, `data`; dòng cuối `type=result` chứa phép đo cuối. Không tự thêm độ trễ để làm đẹp trình diễn.

| Mốc | Khi nào phát |
| --- | --- |
| dns.started | Ngay trước probe tới resolver |
| dns.response / dns.error | Sau probe, có phản hồi hoặc lỗi/timeout |
| validation.observed | Phản hồi secure cung cấp AD/rcode; không đại diện bước mật mã nội bộ |
| http.skipped | Quy tắc DNS không cho phép HTTP |
| http.connecting | Trước gọi socket connect |
| http.connected | Sau connect và lấy peer IP thành công |
| http.request_sent | Sau khi gửi request thành công |
| http.response | Đã nhận header/status; body có thể còn lỗi |
| http.error / http.finished | Lỗi và kết thúc HTTP; ghi rõ body đã nhận đầy đủ chưa |
| branch.completed | Kết thúc nhánh, cả nhánh không có HTTP |

## Job API

`POST /api/jobs` nhận JSON `{ "action": "baseline" }`, hoặc attack/recovery; target nếu truyền chỉ được là www.demo.test. Trả 202 với job_id, run_id, trạng thái và những sự kiện đầu tiên.

`GET /api/jobs/<UUID>?after=0` trả status, cursor, events có sequence lớn hơn after. Sequence bắt đầu 1, tăng theo thứ tự ghi thật ở supervisor. Timestamp worker là lúc đo, received_at là lúc supervisor nhận; thứ tự hiển thị theo sequence. GET chỉ đọc bộ đệm/journal, không gọi Docker. Cursor không hợp lệ trả 400; ID chưa có trả 404; journal sai checksum trả 409.

UI đọc mỗi 400 ms khi chạy, tối đa một request tiến độ đang chờ. Khi lỗi kết nối, UI thử lại cùng job/cursor tối đa 8 lần, cách 1 giây. Không tự POST lại khi mất kết nối. sessionStorage giữ job đang chạy/gần nhất và run_id attack của tab; tải lại sẽ đọc lại từ cursor 0, dựng lại trạng thái không diễn lại pulse cũ. Set sequence loại sự kiện trùng.

Một lock lab bao trùm đổi mode → flush cả hai → hai nhánh DNS/HTTP → proof → log → lưu evidence → đóng journal. Các lệnh đồng bộ `/api/scenario`, `/api/run`, `/api/proof` dùng cùng lock, yêu cầu chồng nhau trả 409. Các API cũ vẫn hoạt động.

Job hoàn thành có `result_url=/api/runs/<run_id>`. Nếu lỗi DNS/HTTP đã đo được, job là failed nhưng vẫn có result_url tới quan sát thật, giữ nguyên phần DNS/HTTP đã đo. Lỗi khởi chạy/worker timeout không có phép đo hợp lệ thì không tạo kết quả thay thế. SERVFAIL trong kịch bản can thiệp là phản hồi DNS đã đo được, khác timeout vận chuyển. API khởi động lại đánh dấu job chưa đóng là interrupted, không tự chạy lại.

Worker streaming có giới hạn nội bộ 25 giây (+2 giây kill); host đọc tối đa 35 giây. Mỗi Docker call khác có timeout riêng. Supervisor kiểm tra ngân sách 180 giây tại mốc ghi sự kiện; tối đa 256 mốc/job, bộ đệm giữ 64 job, các journal vẫn ở đĩa.

## Evidence và integrity

Evidence của develop được giữ nguyên: worker.json, HTTP access log, proof A/RRSIG, DNS context, preview đã sanitize và checksums.json. Bổ sung journal ở `evidence/runs/_jobs/<job_id>/events.jsonl` và state.json. Khi đóng tác vụ, state lưu SHA-256 của toàn journal, finished_at và trạng thái cuối dưới cùng lock; chỉ công bố completed sau khi đóng/checksum. Result chứa job_id để liên kết hai bộ dữ liệu. SHA-256 phát hiện sửa file, không chứng minh nguồn dữ liệu đáng tin nếu kẻ sửa cũng sửa manifest.

Proof lấy bổ sung sau phép đo, cùng revision ổn định; không phải chính gói tin truy vấn trước. Log Unbound/relay chỉ tương quan cửa sổ thời gian. SERVFAIL riêng lẻ không chứng minh lỗi chữ ký; xem A/RRSIG và log để giải thích.

## Quy tắc hiển thị

- Cobalt #3157FF cho thao tác và đường đã kết nối; xanh lá cho AD hợp lệ, cam cho can thiệp, đỏ cho từ chối/lỗi.
- Chỉ pulse client ↔ resolver theo dns.started/response. Hop relay/BIND luôn có nhãn minh họa và nét đứt.
- HTTP đi từ client tới website riêng, chỉ sáng ở http.connected; TCP kết nối và HTTP status tách nhãn. DNS thất bại/bỏ qua HTTP giữ đường trung tính.
- Pulse chạy một lượt 350 ms. Không chạy vô hạn khi chờ. Toggle hiệu ứng và prefers-reduced-motion hủy pulse tức thì, giữ mọi dữ liệu và mốc.
- Recovery thực hiện phép đo mới, so với attack gần nhất của tab/phiên sessionStorage: hai run_id, IP, AD, HTTP, site. Chưa có đối chứng thì ghi rõ; không dùng một baseline cũ làm recovery.
- Timeline đầy đủ và dữ liệu mở chi tiết đặt trong vùng bằng chứng phía dưới hai panel.

## Kiểm chứng

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests/dashboard -v
docker compose exec -T client python -m unittest discover -s tests -v
node tests/check_dashboard_layout.cjs
```

Host tests dùng fake runner có ghi rõ để kiểm tra 202/409, cursor, lỗi, restart, checksum và không chạy Docker khi đọc tiến độ. Worker tests kiểm tra callback đúng vị trí socket, timeout/SERVFAIL không HTTP, hai thread xuất NDJSON. Browser test chạy Docker thật baseline → attack → recovery, kiểm tra access log, evidence, timeline, reconnect/reload không POST lại, font offline, reduced motion, hover không lệnh chạy, desktop/mobile và panel vừa 1366×768. Các ca API lỗi do interception được ghi riêng trong script.
