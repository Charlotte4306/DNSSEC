# DNSSEC Visual Lab

Demo theo [đặc tả](docs/Specification.md), sử dụng [cấu hình chung](docs/PROJECT_CONTRACTS.md)
và [Git workflow](docs/GITFLOW.md).

## Phần hiện đã triển khai

Hai website Docker, BIND authoritative và client DNS → HTTP nội bộ.
Chưa triển khai chữ ký DNSSEC hoặc dashboard. visit.py kiểm tra IP trực tiếp;
browse.py lấy IP từ phản hồi BIND rồi mới truy cập HTTP.

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

## DNS nền đã triển khai

BIND authoritative phục vụ zone demo.test tại 172.30.53.10:53 trong mạng lab.
www.demo.test và control.demo.test trỏ 172.30.53.80. Chưa ký DNSSEC, chưa có
Unbound hoặc relay; truy vấn đang hỏi trực tiếp authoritative.

```powershell
docker compose exec -T client python /app/lab/dns_probe.py
docker compose exec -T client python /app/lab/dns_probe.py --tcp
docker compose exec -T client python /app/lab/browse.py --run-id my-dns-check
docker compose exec -T client python /app/lab/browse.py --name not-present.demo.test
```

Lệnh cuối dự kiến kết thúc mã 1: NXDOMAIN nên không thực hiện HTTP.
Bộ test hiện gồm 14 test, chạy bằng lệnh unittest ở trên.
Xem [DNS_STAGE.md](docs/DNS_STAGE.md) để hiểu cấu hình và các giới hạn.
