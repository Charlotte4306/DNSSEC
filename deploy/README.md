# Deploy DNSSEC lên Azure dùng chung VPS với EMS Forecast

## Trạng thái thực tế

- VPS Ubuntu 24.04: `charlotte@20.198.177.172`, hostname vm-emsforecast.
- Thư mục DNSSEC: `/home/charlotte/apps/dnssec`.
- EMS giữ nguyên ứng dụng ở `127.0.0.1:8501`.
- DNSSEC qua Gunicorn ở `127.0.0.1:18766`, một worker, tám thread.
- Caddy nhận 80/443, phân site theo hostname và cấp HTTPS cho từng domain.
- Công khai cả xem và chạy theo lựa chọn của chủ dự án; mọi người dùng chung lab.
- Docker DNS/HTTP không mở cổng 53 ra Internet; hai cổng web preview 8081/8082
  chỉ bind loopback. API điều khiển không có cổng công khai riêng.

```text
Internet → VPS 20.198.177.172 → Caddy 80/443
  emsforecast.live          → 127.0.0.1:8501  → EMS hiện tại
  itscharlotte.tech         → 127.0.0.1:18766 → Gunicorn → Flask → Docker lab
  www.itscharlotte.tech     → 127.0.0.1:18766 → cùng dashboard
```

Tên miền itscharlotte.tech dùng để mở dashboard. Các truy vấn trong thí nghiệm
vẫn là www.demo.test qua resolver nội bộ Docker. Việc deploy không biến
itscharlotte.tech thành zone thí nghiệm hoặc tấn công DNS công khai.

## 1. Trỏ DNS tại Cloudflare

Nameserver của itscharlotte.tech đang là lee.ns.cloudflare.com và
amanda.ns.cloudflare.com, nên sửa DNS tại Cloudflare.

Cloudflare → itscharlotte.tech → DNS → Records:

| Type  | Name | Nội dung          | Proxy              | TTL  |
| ----- | ---- | ----------------- | ------------------ | ---- |
| A     | @    | 20.198.177.172    | DNS only / mây xám | Auto |
| CNAME | www  | itscharlotte.tech | DNS only / mây xám | Auto |

Không tạo A trùng tên trỏ IP khác. Nếu có AAAA cũ trỏ IPv6 không dùng, cần kiểm
tra và bỏ bản ghi xung đột trước khi nghiệm thu. Giữ public IP Azure ở Static.
Trong phiên deploy đã xác nhận A/CNAME công khai trỏ đúng và người dùng đã chuyển
proxy sang DNS only. Không sửa DNS hay website emsforecast.live.

Kiểm tra từ Windows:

```powershell
Resolve-DnsName itscharlotte.tech -Type A -Server 1.1.1.1
Resolve-DnsName www.itscharlotte.tech -Type A -Server 1.1.1.1
curl.exe -I https://itscharlotte.tech/
curl.exe -I https://www.itscharlotte.tech/
```

Nếu sau này bật lại Cloudflare proxy, cần cấu hình SSL Full (strict), kiểm tra
lại POST/Origin và timeout. Bản deploy này được nghiệm thu ở chế độ DNS only.

## 2. SSH và các thành phần trên VPS

Chạy từ PowerShell trên máy của bạn:

```powershell
ssh -i "$env:USERPROFILE\.ssh\vm-emsforecast_key.pem" charlotte@20.198.177.172
```

Các lệnh sau chạy trong Ubuntu VPS:

```bash
cd /home/charlotte/apps/dnssec
docker version
docker compose version
docker compose ps
sudo systemctl status dnssec-dashboard dnssec-lab --no-pager
```

Đã cài Docker Engine/Compose từ kho chính thức của Docker cho Ubuntu noble.
Đã thêm charlotte vào nhóm docker, systemd cũng khai báo SupplementaryGroups.
Nếu mở một cửa sổ SSH từ trước khi thêm nhóm, cần đăng nhập phiên SSH mới để
nhận membership. Không cần thay cấu hình ứng dụng EMS.

## 3. Source và build

Phiên này chuyển bản source hiện có trên máy Windows bằng archive đã lọc; chưa
tạo Git checkout trên VPS vì code dashboard vẫn đang chờ người dùng commit/merge.
Không dùng git pull ở thư mục VPS hiện tại. Không chuyển .git, .venv, private
keys, .env hoặc evidence từ máy Windows lên. deploy-source-sha256.json lưu hash
source trong gói để đối chiếu. Không có commit/push do agent thực hiện.

Quy trình build đã chạy trên VPS:

```bash
cd /home/charlotte/apps/dnssec
mkdir -p evidence/runs
python3 -m venv .venv
.venv/bin/python -m pip install -r deploy/requirements.txt
.venv/bin/python -m unittest discover -s tests/dashboard -p test_api.py -v
docker compose config --quiet
docker compose build
docker compose up -d --no-build
```

Flask/Bleach nằm trong dashboard/requirements.txt; deploy/requirements.txt thêm
Gunicorn 26.2.0. Host dùng Python 3.12, container client/web dùng Python 3.14
theo Dockerfile. Docker build log nằm ở evidence/deploy-build.log.

Các lần cập nhật sau: đưa source đã review lên đúng thư mục này, giữ lại .venv,
evidence và Docker volumes, cài dependencies/build image nếu có thay đổi rồi
restart các unit cần thiết. Sau khi dự án có commit ổn định trên develop/main,
có thể lập quy trình Git-based deployment riêng; không tự đổi nhánh/force push.

## 4. Gunicorn và systemd

Các tệp đã cài:

| Trong repo                      | Trên VPS                                     |
| ------------------------------- | -------------------------------------------- |
| deploy/dnssec-lab.service       | /etc/systemd/system/dnssec-lab.service       |
| deploy/dnssec-dashboard.service | /etc/systemd/system/dnssec-dashboard.service |
| deploy/dashboard.env.example    | /etc/dnssec/dashboard.env                    |
| deploy/gunicorn.conf.py         | đọc từ thư mục source                        |

Biến môi trường:

```ini
DNSSEC_PUBLIC_HOSTS=itscharlotte.tech,www.itscharlotte.tech
DNSSEC_BEHIND_PROXY=1
PYTHONUNBUFFERED=1
```

Ứng dụng vẫn chặn hostname lạ, giữ kiểm tra Origin cho POST. ProxyFix chỉ tin
scheme từ một Caddy; không tin X-Forwarded-Host do client gửi. Caddy terminate
HTTPS, app vẫn hiểu origin là https://itscharlotte.tech để tránh lỗi 403 sai.
Gunicorn bind loopback và dùng đúng một worker để các lock/state chung không
bị tách thành nhiều process. Tám thread cho phép GET state khi một phép đo đang chạy.

dashboard/wsgi.py giữ single_server lock; không chạy thêm app.py hoặc một
Gunicorn khác trong cùng checkout khi service đang hoạt động. Không bật debug
hay reloader trên VPS. Hai unit đã enable để khởi động cùng máy; chưa thực hiện
thử reboot vì VPS còn phục vụ EMS.

## 5. Caddy dùng chung hai website

Giữ nguyên block EMS hiện tại và thêm import:

```caddyfile
emsforecast.live, www.emsforecast.live {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8501
}

import /etc/caddy/sites-enabled/*.caddy
```

Site DNSSEC được cài từ deploy/Caddyfile.dnssec vào
`/etc/caddy/sites-enabled/dnssec.caddy`. Mỗi hostname được chọn đúng backend;
không chạy thêm Nginx hoặc web server khác tranh cổng 80/443.

Đã sao lưu cấu hình gốc tại
`/etc/caddy/Caddyfile.before-dnssec-20261029T082450Z`.
Đã validate trước khi reload; Caddy cấp chứng chỉ Let's Encrypt cho cả miền gốc
và www. EMS được kiểm tra HTTP 200 trước/sau reload.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -n 50 --no-pager
```

## 6. Vận hành và kiểm tra

```bash
sudo systemctl status dnssec-dashboard dnssec-lab --no-pager
sudo journalctl -u dnssec-dashboard -n 80 --no-pager
cd /home/charlotte/apps/dnssec
docker compose ps
docker compose logs --tail 50 secure tamper
curl -fsS http://127.0.0.1:18766/api/health
curl -fsS https://itscharlotte.tech/api/health
```

Mở https://itscharlotte.tech/, chạy Bình thường → Can thiệp → Khôi phục, xem
đối chiếu A/RRSIG. Các bằng chứng ghi tại evidence/runs trên VPS, không nằm trong
evidence của máy Windows. Đây là lab công khai dùng chung: người khác có thể đổi
mode giữa các lần bạn trình bày, UI sẽ đánh dấu revision cũ; tác vụ đồng thời bị
chặn 409. Không gọi CLI đổi mode trong khi dashboard đang chạy tác vụ.

Sau sửa code Python/Gunicorn:

```bash
sudo systemctl restart dnssec-dashboard
```

Sau thay Dockerfile/lab/websites, khi không có người chạy demo:

```bash
sudo systemctl stop dnssec-dashboard
cd /home/charlotte/apps/dnssec
docker compose build
sudo systemctl restart dnssec-lab
sudo systemctl start dnssec-dashboard
```

Không dùng docker compose down -v khi cập nhật: volumes chứa khóa, zone và mode.
Không dừng Docker/Caddy toàn hệ thống chỉ để dừng demo DNSSEC.

Nếu cần gỡ site DNSSEC khỏi Caddy, chuyển riêng dnssec.caddy ra ngoài thư mục
import, validate/reload và stop hai unit DNSSEC. Giữ block EMS. Backup gốc dùng
để tham khảo, không ghi đè cấu hình EMS mới hơn bằng backup cũ.

## Nguồn kỹ thuật

- [Azure: trỏ domain tới public IP](https://learn.microsoft.com/en-us/azure/virtual-machines/custom-domain).
- [Cloudflare: quản lý DNS record](https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/).
- [Docker: cài trên Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
- [Flask ProxyFix và số proxy được tin cậy](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/).

## Kết quả nghiệm thu trên domain công khai

Ngày 29/10/2026: 20 kiểm thử host đã đạt, gồm regression khởi tạo mới. Đã sửa
initializer để mode.json luôn có attack=false và changed_at ngay khi tạo lab,
tránh UI khóa nút chạy ở lần cài đầu. Đã restart riêng lab/dashboard và kiểm tra
revision hợp lệ trước lần gọi scenario đầu tiên, không reboot VPS hay dừng EMS.

Kiểm thử Edge headless đi qua HTTPS thật → Caddy → Gunicorn → Docker:

| Kịch bản | Run ID                               | Plain           | Secure                       | HTTP access log |
| -------- | ------------------------------------ | --------------- | ---------------------------- | --------------- |
| Baseline | f487faef-a5bd-430b-a01e-3233b219ad61 | .80             | NOERROR, AD                  | 2               |
| Attack   | 7d0897b0-6003-4547-88a4-76fcb6c8a0ee | .90 / trang giả | SERVFAIL, không HTTP/preview | 1               |
| Recovery | 6f1e8a91-6057-4c56-b4ce-2e39f1916e09 | .80             | NOERROR, AD                  | 2               |

Đã xem nội dung preview thật trong iframe, proof RRSIG giữ nguyên cùng revision,
www HTTPS 200, EMS HTTPS 200, POST từ Origin emsforecast.live vào API DNSSEC bị
403 như dự kiến. Không có lỗi JavaScript trong vòng trình duyệt. Đã review ảnh
attack/recovery và giữ lab ở trạng thái recovery đã được đo xác nhận.

Các unit đã enable, nhưng chưa thử reboot VPS. Các kiểm thử ở đây không phải
load test hoặc kiểm thử khả năng chịu nhiều nhóm truy cập đồng thời.
