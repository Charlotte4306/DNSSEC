# Cấu hình chung của DNSSEC Visual Lab

## 1. Tên miền và địa chỉ

| Thành phần | Giá trị |
|---|---|
| Zone DNS | demo.test |
| Tên miền truy cập website | www.demo.test |
| Tên miền đối chứng | control.demo.test |
| Mạng Docker | 172.30.53.0/24 |
| BIND authoritative | 172.30.53.10 |
| Relay tamper | 172.30.53.20 |
| Website hợp lệ | 172.30.53.80 |
| Website giả lập | 172.30.53.90 |
| Dashboard trên host | http://127.0.0.1:8080 |

## 2. Tên dịch vụ Docker

- init: tạo khóa, ký zone và chuẩn bị dữ liệu.
- authority: BIND phục vụ dữ liệu DNS đã ký.
- tamper: chuyển tiếp và mô phỏng sửa phản hồi DNS.
- plain: Unbound không xác thực DNSSEC.
- secure: Unbound có xác thực DNSSEC.
- client: thực hiện truy vấn DNS và truy cập HTTP.
- web-good: phục vụ website hợp lệ.
- web-fake: phục vụ website giả lập.

## 3. Nguyên tắc DNS rồi HTTP

1. Client truy vấn DNS qua resolver được chọn.
2. Nếu DNS thành công và trả IP được phép trong lab,
   client dùng chính IP đó để kết nối HTTP.
3. Khi kết nối HTTP, client gửi Host: www.demo.test.
4. Nếu DNS thất bại, client không gửi HTTP.
5. Không tự chuyển sang resolver khác khi gặp lỗi.
6. Dashboard hiển thị kết quả thực tế do client trả về.

## 4. Ba trạng thái thử nghiệm

- BASELINE: relay giữ nguyên dữ liệu.
- ATTACK: relay đổi A của www.demo.test sang
  172.30.53.90 nhưng giữ nguyên chữ ký RRSIG.
- RECOVERY: relay trở lại giữ nguyên dữ liệu,
  xóa cache hai resolver rồi kiểm tra lại.