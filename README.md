# DNSSEC Visual Lab

Demo theo [đặc tả](docs/Specification.md), sử dụng [cấu hình chung](docs/PROJECT_CONTRACTS.md)
và [Git workflow](docs/GITFLOW.md).

## Phần hiện đã triển khai

Đã có hai website, BIND ký zone, relay sửa phản hồi và hai Unbound có/không
xác thực DNSSEC. Feature dns-core kiểm chứng đủ baseline → attack → recovery.
Đã có worker hỏi từng resolver rồi truy cập HTTP theo đúng IP nhận được.
Đã có dashboard layout dùng dữ liệu minh họa, chưa nối API/lab thật.
Chế độ kiểm tra trực tiếp authority vẫn giữ cho chẩn đoán.

| Dịch vụ | IP lab | Cổng xem trên host | Site ID |
|---|---|---|---|
| web-good | 172.30.53.80:80 | http://127.0.0.1:8081 | legitimate |
| web-fake | 172.30.53.90:80 | http://127.0.0.1:8082 | training-fake |
| client | Docker cấp động | Không công bố | Chạy phép thử HTTP |

## Khởi động và kiểm thử

Cần Docker Desktop chạy Linux containers và Docker Compose.
Lần build đầu cần Internet. Không cần cài Python trên host cho cụm web này.

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec -T client python -m unittest discover -s /app/tests -v
docker compose exec -T client python /app/lab/visit.py --target both --run-id my-web-check
docker compose logs --tail 20 web-good web-fake
```

Compose chờ hai website healthy mới khởi động client. Chọn `--target good`,
`fake` hoặc `both`. JSON kết quả có IP kết nối thật, HTTP status, site_id,
HTML, SHA-256 của body và trạng thái gửi request. Mã thoát 0 nghĩa là các đích
được chọn đều trả đúng IP/site_id/nội dung; mã 1 nghĩa là có kết quả không đạt.

Mở cổng 8081/8082 để xem trực tiếp hai website. Đây là truy cập qua cổng host,
khác với phép thử từ client qua IP mạng lab.

## Cấu trúc phần web

```text
compose.yaml               # dịch vụ, mạng, readiness, cổng
Dockerfile.web             # image web server
Dockerfile.client          # image máy khách thực hiện phép thử
websites/server.py         # server chung, role good/fake
websites/good/index.html
websites/fake/index.html
lab/visit.py               # kết nối IP trực tiếp, giữ Host www.demo.test
tests/test_visit.py        # kiểm thử client với kết nối giả lập
tests/test_web_integration.py  # HTTP thật trong mạng Docker
docs/WEB_STAGE.md          # kiến thức trọng tâm và kết quả nghiệm thu
```

## Mạng và giao thức

- `lab` có subnet 172.30.53.0/24, `internal: true`; client chỉ tham gia mạng này.
- Hai website còn nối mạng bridge `preview` để Docker công bố cổng localhost.
  Mạng preview không internal, nên hai website có thêm kết nối mạng đó.
  Đây là điều chỉnh triển khai so với sơ đồ chỉ có một mạng trong đặc tả.
- Cổng preview chỉ bind 127.0.0.1. Chưa thay DNS của máy người dùng.
- Client chỉ kết nối IP trong danh sách lab, gửi `Host: www.demo.test`, không dùng
  proxy môi trường, không tự theo redirect và giới hạn body 1 MiB.
- Server trả `X-Lab-Site`; log JSON có method, host, run_id, branch_id và status.
- `GET /` trả HTML, `HEAD /` chỉ trả header, `GET /health` trả JSON readiness.
  Đường dẫn khác trả 404. Health probes không ghi vào access log thực nghiệm.
- Python http.server ở đây là server cho lab cục bộ, không phải cấu hình production.

## Sửa code và dừng

Code được COPY vào image, không bind mount. Sửa file rồi build lại:

```powershell
docker compose up -d --build
```

Khi image đã có, có thể khởi động bằng `docker compose up -d --no-build`.
Dừng và gỡ container/network dự án bằng `docker compose down`.

## Xử lý lỗi thường gặp

- Không kết nối Docker: mở Docker Desktop và kiểm tra `docker version`.
- Cổng 8081/8082 bị dùng: đổi phần cổng host trong Compose; IP lab không đổi.
- Subnet trùng mạng khác: cần đổi đồng bộ Compose, cấu hình chung và TARGETS trong visit.py.
- Website không healthy: xem `docker compose logs web-good web-fake`.
- Sửa code không thấy thay đổi: build lại image; khởi động lại container đơn thuần không COPY code mới.

Kết quả kiểm thử cụ thể nằm trong [WEB_STAGE.md](docs/WEB_STAGE.md).

## DNS core đã hoàn thành

```powershell
docker compose up -d --build
.\dns.ps1 test
.\dns.ps1 baseline
.\dns.ps1 attack
.\dns.ps1 compare
.\dns.ps1 proof
.\dns.ps1 logs
.\dns.ps1 recover
```

plain nhận IP .90 khi bị sửa; secure trả SERVFAIL và không IP.
Sau phục hồi secure trở về .80 với AD=true. Kết quả kiểm thử được lưu ngoài Git.
Xem [DNS_STAGE.md](docs/DNS_STAGE.md) để đọc code, volume, khóa, thời hạn chữ ký,
kiểm thử và giới hạn chính xác của feature.


## Worker DNS → HTTP đã hoàn thành

```powershell
.\worker.ps1 test
.\dns.ps1 baseline
.\worker.ps1 compare
.\dns.ps1 attack
.\worker.ps1 compare
.\dns.ps1 recover
```

Khi bị sửa, plain thực sự đến web-fake; secure không gửi HTTP. Kết quả JSON có
IP DNS, IP kết nối, status và nội dung HTTP; đối chiếu access log theo run_id.
25 test và ba kịch bản worker thực tế đã đạt.
Xem [WORKER_STAGE.md](docs/WORKER_STAGE.md) để đọc schema, CLI và giới hạn đồng bộ.

## Xem dashboard layout (dữ liệu minh họa)

Từ thư mục gốc repo, chạy Python trên host:

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory dashboard
```

Mở http://127.0.0.1:8080/templates/index.html. Thử Bình thường → Can thiệp →
Khôi phục; xem hai panel, trạng thái chờ/lỗi và JSON minh họa. Giao diện chưa
truy vấn DNS/HTTP, chưa điều khiển Docker và chưa có Flask backend.
Xem [hướng dẫn layout](docs/DASHBOARD_LAYOUT.md) để hiểu cấu trúc và cách review.
