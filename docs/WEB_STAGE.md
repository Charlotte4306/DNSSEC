# Hoàn thành giai đoạn website và client HTTP

## Phạm vi

Nhánh `feature/web-targets` gồm hai website và client HTTP nội bộ. Chưa có BIND,
Unbound, relay hoặc dashboard. Không tuyên bố các kết quả dưới đây chứng minh DNSSEC.

## Kiến thức trọng tâm

1. **IP và Host khác nhau:** kết nối TCP chọn IP đích; header Host chỉ tên website được yêu cầu.
2. **Một code server, hai dịch vụ:** biến SITE_ROLE chọn nội dung và site_id cho từng container.
3. **Readiness khác đang chạy:** tiến trình tồn tại chưa đủ; /health phải trả HTTP thành công.
   Compose chỉ áp dụng điều kiện healthy khi khởi động phụ thuộc, không tự chữa mọi lỗi runtime.
4. **Kết quả là dữ liệu đo:** connected_ip lấy từ socket; site_id/header/body lấy từ HTTP response.
5. **Đối chiếu bằng run_id:** cả hai request của một lần thử chung run_id, có branch_id khác nhau.
6. **Lỗi có từng giai đoạn:** attempted là bắt đầu thử, request_sent là đã gửi; status chỉ có khi nhận response.
   HTTP 200 nhưng body vượt giới hạn vẫn có error, không được đánh dấu passed.

SHA-256 của body hỗ trợ đối chiếu nội dung nhận được, không phải chữ ký hoặc xác thực DNSSEC.

## Kết quả đã chạy ngày 29/10/2026

Lệnh:

```powershell
docker compose exec -T client python -m unittest discover -s /app/tests -v
docker compose exec -T client python /app/lab/visit.py --target both --run-id web-stage-final
```

**9 kiểm thử đạt:** 7 unit tests và 2 integration tests. Integration tests thực hiện
các subcase cho cả hai website, gồm GET /, GET /health, GET /missing và HEAD /.

| Ca | Kết quả thực tế |
|---|---|
| Website hợp lệ | connected_ip=172.30.53.80, HTTP 200, site_id=legitimate |
| Website giả lập | connected_ip=172.30.53.90, HTTP 200, site_id=training-fake |
| Readiness | Cả hai website healthy; client đang chạy |
| Header và log | Host=www.demo.test, run_id=web-stage-final, branch_id=direct-good/direct-fake |
| Đường dẫn không có | HTTP 404 ở cả hai website |
| HEAD | Header đúng và không có response body |

Các ca đơn vị kiểm tra chặn IP ngoài lab, từ chối hostname thay IP, giữ Host/run_id,
lỗi kết nối, lỗi giao thức, không tự theo redirect và giới hạn response body.
Các ca lỗi này dùng mock; không mô tả là đã dừng máy chủ để tạo lỗi mạng thật.

## Nghiệm thu và bước kế tiếp

- Hai website có nội dung phân biệt và không thu thập thông tin đăng nhập.
- Client thực sự truy cập qua mạng lab, không chọn trang theo trạng thái mô phỏng.
- Có kiểm thử, healthcheck và hướng dẫn tái lập.
- Chưa commit/push/merge tự động. Review diff trước khi đưa vào PR.
- Bước sau: dựng DNS nền để tên www.demo.test trả IP hợp lệ; sau đó worker lấy IP
  từ resolver thay cho tham số chọn IP trực tiếp. Không thêm dashboard mock thay cho DNS thật.
