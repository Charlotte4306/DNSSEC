# Feature dns-core

Phạm vi đúng theo GITFLOW.md: BIND + ký zone + trust anchor + Unbound plain/secure
+ relay + kiểm thử hợp lệ → bị sửa → khôi phục. Chưa tích hợp hai resolver với
HTTP worker hoặc dashboard. `browse.py` cũ vẫn hỏi trực tiếp authority.

## 1. Mô hình

```text
client → plain  (172.30.53.40, chỉ iterator) ----------+
                                                    +→ tamper (.20) → BIND (.10)
client → secure (172.30.53.30, validator + iterator) --+
```

Đây là hướng truy vấn. Phản hồi từ BIND đi qua relay rồi trở về resolver.
Relay chỉ sửa A của www.demo.test thành 172.30.53.90 khi ON, giữ RRSIG.
IP đúng là 172.30.53.80. Không sửa BIND hoặc khóa để tạo lỗi.

## 2. Tệp cần đọc và kiến thức trọng tâm

| Tệp | Vai trò và điều cần hiểu |
|---|---|
| lab/init_dnssec.py | Tạo KSK/ZSK ECDSA P-256 nếu chưa có; ký zone và xuất trust anchor |
| lab/conf/named.conf | BIND phục vụ /signed/demo.test.signed; không tự ký lại phản hồi relay sửa |
| lab/conf/secure.conf | Bật validator và tin DNSKEY KSK của zone thử nghiệm |
| lab/conf/plain.conf | Chỉ chạy iterator; vẫn phân giải nhưng không kiểm tra chữ ký |
| lab/conf/unbound-common.conf | Hai resolver cùng stub đến relay, cùng cấu hình cache và log |
| lab/tamper.py | Chuyển tiếp UDP/TCP và sửa đúng A mục tiêu, không được mount khóa bí mật |
| lab/dns_probe.py | Chọn rõ authority/tamper/plain/secure, không fallback DNS hệ điều hành |
| lab/dns_scenario.py | So sánh, đối chứng, kiểm tra kết quả và ghi evidence |
| dns.ps1 | Đổi mode, flush hai cache, chạy các trạng thái và thu log |

### KSK, ZSK và trust anchor

ZSK ký dữ liệu trong zone; KSK ký RRset DNSKEY. Khóa công khai được công bố trong
DNSKEY. Resolver secure được cấp trước DNSKEY KSK qua `/trust/anchor.key`, nên có
điểm bắt đầu tin cậy. Lab không tự tin một khóa bất kỳ chỉ vì máy chủ gửi nó.

Tệp `/trust/anchor.ds` được sinh để minh họa digest. Lab không có zone cha hoặc
DS được công bố trên Internet; không tuyên bố chuỗi xác thực từ root công cộng.

### Vì sao sửa IP làm chữ ký sai?

RRSIG bảo vệ RRset ban đầu. Relay không có khóa bí mật và không tạo chữ ký mới,
nên đổi IP làm chữ ký cũ không còn khớp. Unbound secure kiểm tra mật mã và từ chối.
Đây là mô phỏng khả năng sửa phản hồi trên đường đi, không khai thác Kaminsky.

### Cache và log

Mỗi lần chuyển mode, script flush_zone demo.test ở cả hai resolver. Nếu không,
IP đã cache có thể che mất trạng thái upstream mới. SERVFAIL có nhiều nguyên nhân;
log của lần chạy phải chỉ ra lỗi mật mã, kết hợp baseline và các đối chứng.

## 3. Khởi động và vận hành

```powershell
docker compose up -d --build
docker compose ps
.\dns.ps1 baseline
.\dns.ps1 attack
.\dns.ps1 proof
.\dns.ps1 logs
.\dns.ps1 recover
```

`init` thoát mã 0 là bình thường vì là bước chuẩn bị một lần. Các dịch vụ DNS/web
phải healthy; client đang chạy. DNS server chỉ mở trong mạng lab, không công bố
cổng DNS trên host ở giai đoạn này. Dùng client để truy vấn:

```powershell
docker compose exec -T client python /app/lab/dns_probe.py --server secure
docker compose exec -T client python /app/lab/dns_probe.py --server plain
docker compose exec -T client python /app/lab/dns_probe.py --name demo.test --type DNSKEY
```

Chỉ `dns.ps1` xử lý đổi mode kèm flush đầy đủ; gọi trực tiếp on/off trong container
mà không flush không tạo một phép thử sạch. Không thao tác mode đồng thời ở nhiều cửa sổ.

## 4. Volume và khóa

- dns-keys: khóa bí mật/công khai, chỉ init được mount.
- signed-zone: init ghi; BIND chỉ đọc zone đã ký.
- trust-data: init ghi; secure chỉ đọc trust anchor công khai.
- attack-state: init/client ghi mode, relay chỉ đọc; không chứa khóa.
- evidence: bind mount để lưu kết quả tại máy người dùng.

Các volume runtime không được commit lên Git. Khóa được giữ lại qua `down`, không
cần tạo lại mỗi lần. Chữ ký hiệu lực khoảng 30 ngày, bắt đầu trước lúc ký 1 giờ.
Nếu cần làm mới chữ ký, `docker compose down` rồi `up -d --build` để init ký mới
và BIND khởi động với zone mới. Không thay đồng hồ để né thời hạn chữ ký, không
dùng `down -v` như thao tác chạy hằng ngày vì sẽ xóa dữ liệu/khóa của lab.

## 5. Kiểm thử

```powershell
.\dns.ps1 test
```

Script đặt OFF, chạy 18 test hiện có, rồi kiểm chứng baseline/attack/recovery.
Cuối cùng luôn cố đưa mode về OFF; khi dịch vụ lỗi, vẫn phải đọc lỗi và kiểm tra
thực tế, không giả định phần finally chắc chắn phục hồi thành công.

| Trạng thái | plain | secure |
|---|---|---|
| Baseline | NOERROR, .80, AD=false | NOERROR, .80, AD=true |
| Attack | NOERROR, .90, AD=false | SERVFAIL, không IP, AD=false |
| Recovery | NOERROR, .80, AD=false | NOERROR, .80, AD=true |

Trong cả ba trạng thái còn kiểm tra: control vẫn xác thực, NXDOMAIN có AD,
secure qua TCP nhất quán với UDP, BIND vẫn có IP gốc, RRSIG của BIND/relay giữ nguyên.
`proof` so sánh chuỗi RRSIG và hash SHA-256; hash này chỉ giúp so sánh, không thay
thế kiểm tra chữ ký mật mã do Unbound thực hiện.

Unit test relay dùng chữ ký tổng hợp để kiểm tra giới hạn biến đổi. Xác thực
mật mã thật được kiểm tra qua Unbound và log, không qua chữ ký giả trong unit test.

## 6. Bằng chứng và giới hạn

Kết quả mỗi trạng thái vào `evidence/runs/<timestamp>-<phase>-<id>/dns.json`.
Log lỗi trong lần chạy vào `evidence/dns-validation.log`. Các đường dẫn này được
gitignore; không commit toàn bộ runtime logs. Sau thử nghiệm có thể đọc:

```powershell
Select-String evidence/dns-validation.log -Pattern 'signature crypto failed'
```

Feature này kết thúc ở quyết định DNS. Việc plain dùng IP giả để HTTP đến website
giả, secure không HTTP khi DNS lỗi, cùng API trả JSON cho dashboard sẽ hoàn thiện
trong `feature/dns-http-worker`, không mở rộng lẫn vào dns-core.

## 7. Kết quả lần kiểm thử ngày 29/10/2026

18 test đạt; các phép kiểm chứng baseline, attack, recovery đạt. Unbound ghi
`signature crypto failed from 172.30.53.20` đúng trong lần thử bị sửa.
Sau khi kết thúc, script đưa relay về OFF và flush cache. Không có stage/commit/push tự động.

## 8. Nguồn kỹ thuật

- https://bind9.readthedocs.io/en/stable/dnssec-guide.html
- https://unbound.docs.nlnetlabs.nl/en/latest/manpages/unbound.conf.html
- https://dnspython.readthedocs.io/en/stable/query.html
