# Giai đoạn DNS nền

## Mô hình đã chạy

client → BIND authoritative (172.30.53.10) → trả A 172.30.53.80
client → HTTP tới chính 172.30.53.80, Host: www.demo.test → web-good

Đây là DNS chưa ký, chưa có resolver xác thực. Không diễn giải AD=False thành
xác thực thất bại: chưa thực hiện kiểm tra DNSSEC ở giai đoạn này.

## Tệp quan trọng

- Dockerfile.dns: cài BIND, copy cấu hình/zone, kiểm tra cú pháp khi build.
- lab/conf/named.conf: khai báo zone demo.test, recursion no; không phục vụ tra cứu Internet.
- lab/zones/demo.test: dữ liệu SOA, NS, ns, www và control.
- lab/dns_probe.py: gửi truy vấn đến IP BIND cố định, không fallback DNS hệ điều hành.
- lab/browse.py: DNS thành công và có đúng một IP lab được phép thì mới gọi visit.
- lab/visit.py: HTTP theo IP đã nhận; header Host dùng đúng tên truy vấn.
- lab/requirements.txt: dnspython==2.8.0.

## Kiến thức trọng tâm

Zone là phạm vi dữ liệu DNS mà máy chủ quản lý. SOA chứa thông tin quản lý và serial;
NS xác định máy chủ có thẩm quyền; A ánh xạ tên tới IPv4. Dấu chấm cuối tên đầy đủ
ngăn BIND tự nối thêm tên zone. TTL 15 là thời gian cache của các bản ghi dùng TTL mặc định.

Cờ AA cho biết phản hồi có thẩm quyền; khác với AD là dấu hiệu dữ liệu đã xác thực
trong ngữ cảnh resolver tin cậy. Ở đây AA=True, AD=False là bình thường.
NXDOMAIN: tên không tồn tại. NODATA: tên tồn tại nhưng không có loại bản ghi hỏi;
ví dụ www không có AAAA, status vẫn NOERROR và không có câu trả lời AAAA.

## Kiểm thử thực tế ngày 29/10/2026

14 test đạt: 9 test của HTTP và 5 test bổ sung DNS/gating.

- UDP/TCP trả www A=172.30.53.80, AA=True, AD=False.
- NXDOMAIN thật cho not-present.demo.test, không gọi hàm HTTP.
- AAAA của www: NOERROR, không có bản ghi trả lời.
- Luồng DNS→HTTP nhận HTTP 200, site_id legitimate, IP kết nối trùng IP DNS.
- Access log ghi run_id=dns-stage-final, Host=www.demo.test.
- SERVFAIL, timeout và IP ngoài lab được kiểm tra bằng mock: đều không gọi HTTP.
- named-checkconf và named-checkzone đều đạt.

## Giới hạn hiện tại

Chỉ hỗ trợ các tên lab cố định và luồng IPv4 đơn giản. Chưa theo CNAME hoặc chọn
nhiều IP. SOA serial cần tăng khi sửa zone. Zone được COPY vào image nên sau thay đổi
phải chạy docker compose up -d --build. Chưa có chữ ký, trust anchor hay hành vi
can thiệp; chặng sau mới bổ sung các thành phần đó.

## Tài liệu gốc

- https://bind9.readthedocs.io/en/stable/
- https://dnspython.readthedocs.io/en/stable/query.html
