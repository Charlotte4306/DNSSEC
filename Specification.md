# Đặc tả DNSSEC Visual Lab

### 1 Mục tiêu và quyết định thiết kế

Xây dựng bản demo cho người xem quan sát được hậu quả của dữ liệu DNS bị sửa. Cùng một tên miền, phía không xác thực có thể nhận IP giả lập và truy cập nhầm website; phía DNSSEC từ chối dữ liệu không hợp lệ và không gửi yêu cầu HTTP đến IP đó. Khi khôi phục, cả hai phía trở lại website hợp lệ.

Phương án được chọn là Flask kết hợp HTML, CSS, JavaScript và sơ đồ SVG. Giữ BIND, hai Unbound, relay và công cụ truy vấn của lab; bổ sung hai web server và một lớp điều khiển trên máy trình bày. Mọi kết quả trên dashboard phải bắt nguồn từ truy vấn DNS và HTTP thực tế.

### 2 Phần hiện có và phần xây mới

| Phần                   | Trạng thái và công việc                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------ |
| Lab DNSSEC nền         | Đã có BIND, relay, secure/plain Unbound, client, script CLI và bằng chứng của bản Terminal.      |
| Hai website            | Cần xây mới: web-good và web-fake, nội dung phân biệt rõ, không thu thập thông tin đăng nhập.    |
| Dashboard và API       | Cần xây mới: điều khiển chế độ, chạy phép thử, sơ đồ, hai panel, nội dung website và bằng chứng. |
| Truy cập HTTP theo DNS | Cần xây mới: worker phải dùng đúng IP vừa nhận từ resolver để kết nối.                           |
| Kiểm thử bản mới       | Cần chạy lại toàn bộ; kết quả bản Terminal cũ không phải kết quả đã kiểm thử của bản web.        |

### 3 Phạm vi và giới hạn

Dùng www.demo.test trong mạng lab riêng. Mô phỏng đối thủ đã sửa được phản hồi DNS; không triển khai khai thác Kaminsky hoặc tấn công hệ thống công cộng. Trust anchor vẫn cài cục bộ; chưa có chuỗi DS từ root công cộng. Không làm form đăng nhập, key rollover hoặc website thương hiệu thật trong phạm vi bắt buộc.

Website đích dùng HTTP nội bộ để cô lập tác động của DNS trong phép thử. Kết quả không có nghĩa giả mạo DNS luôn vượt qua HTTPS; cơ chế chứng chỉ TLS là lớp bảo vệ khác.

## 4 Kiến trúc tổng thể được chọn

```text
Trình duyệt trên máy trình bày
       | HTTP localhost:8080
       v
Dashboard Flask trên HOST
       | Docker CLI, tác vụ cố định
       v
Client worker trong Docker
       | DNS                   | HTTP tới IP đã phân giải
       v                       v
Unbound plain / secure      web-good hoặc web-fake
       |
       v
Relay tamper --> BIND authoritative
  sửa PHẢN HỒI      zone đã ký
```

Đường truy vấn DNS: worker → resolver được chọn → relay → BIND. Phản hồi đi ngược lại, có thể bị relay sửa. Đường HTTP chỉ bắt đầu sau khi worker nhận được câu trả lời DNS sử dụng được. Dashboard không thay đổi DNS của hệ điều hành hoặc trình duyệt người dùng.

### Thành phần và địa chỉ đề xuất

| Thành phần       | Triển khai và vai trò                                | Địa chỉ                    |
| ---------------- | ---------------------------------------------------- | -------------------------- |
| Dashboard        | Flask trên host; phục vụ UI và điều phối Docker CLI. | 127.0.0.1:8080             |
| init / authority | Tạo khóa, ký zone; BIND phục vụ bản đã ký.           | authority: 172.30.53.10:53 |
| tamper           | Giữ RRSIG, đổi A mục tiêu khi ON.                    | 172.30.53.20:53            |
| plain / secure   | Cùng upstream; chỉ secure bật validator.             | Host DNS 1054 / 1053       |
| client           | Worker DNS và HTTP chạy bên trong mạng Docker.       | Tên dịch vụ client         |
| web-good         | Phục vụ trang hợp lệ và định danh máy chủ.           | 172.30.53.80:80            |
| web-fake         | Phục vụ trang giả lập được gắn nhãn đào tạo.         | 172.30.53.90:80            |

Hai IP web là địa chỉ nội bộ đề xuất, phải khai báo nhất quán trong Compose, zone, relay và kiểm thử. Nếu subnet trùng máy/VPN, đổi đồng bộ. Không dùng 192.0.2.x của bản Terminal cho hai web server thật.

## 5 Cơ chế truy cập website theo kết quả DNS

### Luồng xử lý bắt buộc

1. Backend nhận yêu cầu thử www.demo.test qua plain và secure. Tạo run_id và scenario_revision, khóa đổi chế độ trong suốt phép thử.
2. Worker gửi DNS A đến từng resolver đã chọn, lưu status, AD, IP, RRSIG và thời gian.
3. Nếu DNS thất bại hoặc không có IP phù hợp, dừng nhánh đó, đánh dấu HTTP bị bỏ qua.
4. Nếu DNS thành công, kết nối HTTP trực tiếp đến IP trong câu trả lời; gửi Host: www.demo.test.
5. Lưu IP đã kết nối, status HTTP, định danh do web server trả, nội dung trang và log.
6. Dashboard hiển thị kết quả cùng run_id, nguồn dữ liệu và thời điểm.

### Yêu cầu để chứng minh có truy cập thật

Worker dùng HTTPConnection(ip, 80, timeout=...) hoặc cơ chế tương đương, không gọi thư viện HTTP với URL tên miền rồi để thư viện tự tra DNS khác. Không dùng proxy môi trường, không tự theo redirect, không fallback sang DNS hệ điều hành hay DNS công cộng. Đối với bản đầu, chỉ chấp nhận một A thuộc tập IP của lab.

```text
# Pseudocode minh họa, chưa phải mã đã triển khai
answer = query_selected_resolver("www.demo.test", "A")
if answer.rcode != "NOERROR" or not answer.allowed_ip:
    return dns_result(http_skipped=True)
conn = HTTPConnection(answer.ip, 80, timeout=3)
conn.request("GET", "/", headers={"Host": "www.demo.test"})
response = conn.getresponse()
return measured_result(answer, response, connected_ip=answer.ip)
```

### Website thật và giả lập

web-good trả trang “Website hợp lệ của lab”, cùng X-Lab-Site: legitimate. web-fake trả trang “Website giả lập trong thử nghiệm DNSSEC”, cùng X-Lab-Site: training-fake. Cả hai trả nội dung tự chứa, không gọi tài nguyên Internet, không có form nhập mật khẩu và ghi access log kèm X-Lab-Run-ID.

Định danh website phải đọc từ phản hồi HTTP và kiểm tra với bằng chứng, không tự gán theo nút Attack. Nếu secure SERVFAIL, UI hiển thị “Dừng ở DNS, chưa gửi HTTP”; không cho hiện website hợp lệ hoặc giả lập từ dữ liệu cũ.

### Cách đưa trang lên dashboard

Trình duyệt xem bản nội dung do worker thực sự lấy qua HTTP, được backend làm sạch rồi hiển thị trong iframe sandbox. Ghi nhãn “Nội dung HTTP do máy khách lab tải”. Đây là truy cập thật từ worker, không tuyên bố thanh địa chỉ của trình duyệt người xem đã được DNS điều hướng trực tiếp.

## 6 Đặc tả giao diện trình diễn

### Bố cục một màn hình chính

| Khu vực            | Nội dung và hành vi                                                                                                     |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| Thanh điều khiển   | Ba chế độ Bình thường, Can thiệp, Khôi phục; nút Truy vấn và truy cập; trạng thái đang xử lý và thời điểm đo.           |
| Sơ đồ SVG          | Client, hai resolver, relay và BIND. Sau DNS thành công mới nối đến web-good/web-fake. Có điểm dừng khi DNS bị từ chối. |
| Panel trái         | Không xác thực DNSSEC: status DNS, AD, IP nhận, IP kết nối, status HTTP và nội dung website.                            |
| Panel phải         | Có xác thực DNSSEC: cùng bộ trường. Nếu SERVFAIL, giải thích HTTP chưa được gửi và mở bằng chứng nguyên nhân.           |
| So sánh dữ liệu    | IP gốc so với IP qua relay; RRSIG còn giữ nguyên; trust anchor được cấu hình. Chỉ hiện sau phép đo.                     |
| Bằng chứng mở rộng | Đầu ra DNS nguyên văn, log Unbound/relay, HTTP response và access log theo run_id; hỗ trợ sao chép/tải JSON.            |

### Quy tắc hiển thị

Màu xanh dành cho kết quả đã xác thực hoặc trang đúng được truy cập; màu cam/đỏ cho chấp nhận IP giả lập, từ chối hoặc lỗi. Luôn có nhãn chữ để người xem không phải suy luận từ màu. Khi DNS timeout hoặc Docker dừng, ghi “Không có kết quả mới”, không tự chuyển sang trạng thái tấn công.

Khi đổi chế độ, vô hiệu hóa các nút gây xung đột và đánh dấu kết quả cũ là “Lần đo trước”. Không hiển thị lại trang cũ như kết quả hiện tại. Bố cục trình chiếu nên đọc được trên màn hình 1366×768; chi tiết dài mở theo yêu cầu, không ép toàn bộ log vào màn hình chính.

### Sơ đồ động và tính trung thực

Animation giải thích hướng xử lý theo các bước và kết quả API. Ghi “Minh họa luồng xử lý”, không gọi là bắt gói mạng hay đo thời điểm từng hop nếu chưa có pcap/telemetry tương ứng. Thời gian đo thực từ backend phải tách khỏi tốc độ animation.

Cần có trạng thái đang chờ, lỗi DNS, lỗi HTTP và hủy/kết thúc phép thử. Dùng nút “Xem vì sao” để dẫn người xem từ kết quả đến bản ghi, chữ ký và log thay vì chỉ hiện biểu tượng khiên.

## 7 Máy trạng thái và điều phối tác vụ

### Trạng thái kịch bản

| Trạng thái   | Thay đổi thực tế                                                    | Hiển thị sau phép đo đạt                            |
| ------------ | ------------------------------------------------------------------- | --------------------------------------------------- |
| BASELINE     | Relay OFF; xóa cache ở plain và secure.                             | Hai phía đến web-good; secure AD=true.              |
| ATTACK       | Relay ON; chỉ đổi A của www sang IP web-fake; giữ RRSIG; xóa cache. | plain đến web-fake; secure SERVFAIL và không HTTP.  |
| RECOVERY     | Relay OFF; xóa cache; xác nhận DNS hợp lệ.                          | Hai phía lại đến web-good; secure AD=true.          |
| BUSY / ERROR | Tác vụ đang chạy hoặc một bước điều phối thất bại.                  | Không tuyên bố đổi chế độ thành công; nêu bước lỗi. |

### Thứ tự xử lý thay đổi chế độ

Backend nhận một action trong danh sách cho phép → lấy khóa tác vụ → đổi trạng thái relay → gọi flush_zone trên cả hai resolver → kiểm tra DNSKEY/khả năng liên lạc → tăng scenario_revision → phát hành kết quả hoặc lỗi → nhả khóa. Không tự suy ra website đích từ action.

Thay đổi relay và flush hai cache không phải giao dịch nguyên tử ở tầng hạ tầng. Nếu một bước lỗi, ghi rõ actual_mode và cache_flush_status, đánh dấu ERROR và yêu cầu khôi phục; không che lỗi bằng thông báo “Đã bật thành công”.

### Tránh trộn hai trạng thái trong một lần so sánh

Chỉ một tác vụ thay đổi chế độ hoặc đo hai nhánh chạy tại một thời điểm. Phép thử giữ khóa xuyên suốt DNS và HTTP của cả hai nhánh; các truy vấn có thể chạy song song bên trong một tác vụ. Yêu cầu thứ hai trả 409 BUSY hoặc vào hàng đợi rõ ràng. Mỗi kết quả mang revision trước/sau để phát hiện dữ liệu trộn.

### Quan hệ với cache

Phần trình diễn chính luôn flush sau đổi chế độ để quan sát can thiệp mới. Có thể giải thích cache bằng một thử nghiệm tùy chọn riêng, không trộn với phép so sánh chính. Mỗi kết quả ghi cache đã được xử lý hay chưa, tránh hiểu IP cũ là DNSSEC đã bảo vệ dữ liệu khi thực tế chưa hỏi upstream.

## 8 API dự kiến và hợp đồng dữ liệu

API cùng origin với dashboard tại localhost:8080. Các endpoint dưới đây là thiết kế cần triển khai, chưa tồn tại trong bộ demo Terminal hiện tại.

| Endpoint                            | Đầu vào                                       | Kết quả hoặc tác dụng                                                        |
| ----------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------- |
| GET /api/health                     | Không có.                                     | Docker, dịch vụ và khả năng sẵn sàng; không tự tạo kết quả DNS/HTTP.         |
| GET /api/state                      | Không có.                                     | actual_mode, revision, busy, tác vụ gần nhất và lỗi nếu có.                  |
| POST /api/scenario                  | action: baseline, attack hoặc recovery.       | Đổi mode và flush; trả trạng thái từng bước, revision và lỗi.                |
| POST /api/run                       | target cố định và hai resolver đã định nghĩa. | Thực hiện DNS → HTTP; trả run_id cùng kết quả hai nhánh.                     |
| POST /api/proof                     | Không nhận lệnh tùy ý.                        | Đọc A/RRSIG từ BIND và relay; đối chiếu chữ ký.                              |
| GET /api/runs/<id>                  | run_id hợp lệ trong evidence.                 | Bằng chứng JSON và log gắn lần chạy; không nhận đường dẫn tệp tùy ý.         |
| GET /api/runs/<id>/preview/<branch> | plain hoặc secure của lần chạy.               | Nội dung HTML đã lấy, được làm sạch; không thực hiện một truy cập tùy ý mới. |

### Các trường tối thiểu của kết quả mỗi nhánh

```text
run_id, scenario_revision, requested_at, finished_at
resolver: plain | secure
dns: rcode, ad, answers, elapsed_ms, raw, error
http: attempted, connected_ip, status, site_id, body_hash, error
evidence: dns_file, http_file, matched_log_ids
interpretation: validated | accepted_fake | blocked | inconclusive
```

Nếu không nhận phản hồi DNS, rcode/ad là null và có transport_error, không gán AD=false như thể đã nhận gói tin. DNS NOERROR nhưng HTTP thất bại vẫn là lỗi HTTP, không tự suy thành xác thực DNSSEC thất bại. Chỉ nhánh không có HTTP mới đặt attempted=false.

Backend lưu dữ liệu thô trước, sau đó suy diễn nhãn dựa trên kết quả và bằng chứng. SERVFAIL chưa có log phù hợp chỉ ghi “DNS từ chối/chưa xác định nguyên nhân”. Nhật ký cũ không được ghép vào phép thử mới chỉ vì cùng tên miền.

## 9 Cấu trúc thư mục dự kiến của bản làm lại

Đề xuất repo gốc DNSSEC theo cấu trúc dưới đây. Đây là cấu trúc mục tiêu để triển khai lại; không mô tả rằng các tệp mới đã được tạo. Lab hiện tại trong dnssec-demo cần được di chuyển hoặc tái tổ chức có kiểm soát, không xóa trước khi có bản mới đạt kiểm thử.

```text
DNSSEC/
|-- README.md
|-- .gitignore
|-- compose.yaml
|-- Dockerfile.lab
|-- run-dashboard.ps1
|-- run-dashboard.sh
|-- dashboard/
|   |-- requirements.txt
|   |-- app.py
|   |-- config.py
|   |-- services/
|   |   |-- docker_runner.py
|   |   |-- scenario_service.py
|   |   `-- evidence_service.py
|   |-- templates/index.html
|   `-- static/
|       |-- css/app.css
|       |-- js/app.js
|       `-- img/topology.svg
|-- lab/
|   |-- init_lab.py
|   |-- tamper.py
|   |-- dns_probe.py
|   |-- visit.py
|   |-- api_worker.py
|   `-- conf/
|       |-- named.conf
|       |-- common.conf
|       |-- secure.conf
|       `-- plain.conf
|-- websites/
|   |-- good/index.html
|   |-- fake/index.html
|   `-- server.py
|-- tests/
|   |-- test_tamper.py
|   |-- test_http_routing.py
|   |-- test_scenarios.py
|   `-- test_dashboard_api.py
|-- evidence/runs/              # sinh khi chạy, không commit mặc định
`-- docs/
    |-- DAC_TA.md
    |-- DEMO_SCRIPT.md
    `-- TEST_REPORT.md
```

## 10 Trách nhiệm tệp và tổ chức dữ liệu

| Nhóm tệp                | Trách nhiệm chính                                                                               |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| docker_runner.py        | Chạy Docker CLI bằng argv cố định và cwd xác định; timeout, kiểm tra exit code, đọc JSON chuẩn. |
| scenario_service.py     | Khóa tác vụ, đổi mode, flush cache, revision và phản hồi lỗi từng bước.                         |
| dns_probe.py / visit.py | Hỏi resolver chỉ định, trích DNS; dùng IP đó để HTTP; không tự đổi DNS hoặc theo redirect.      |
| api_worker.py           | Giao thức JSON của client container: nhận phép thử đã cho phép, xuất JSON kết quả ra stdout.    |
| evidence_service.py     | Lưu theo run_id, đối chiếu log/timestamp, giới hạn nội dung trả về và tạo preview an toàn.      |
| static/js/app.js        | Gọi API, trạng thái nút, hai panel, animation SVG và mở bằng chứng; không tự tạo kết quả đo.    |
| websites/server.py      | Phục vụ trang tương ứng role, header X-Lab-Site và access log có run_id.                        |
| tests/                  | Kiểm tra biến đổi, DNS→HTTP, nhánh bị chặn, API và tình huống lỗi.                              |

### Docker volume và dữ liệu sinh ra

Tách signing-data chứa khóa/zone, trust-data chứa DNSKEY công khai, attack-state chứa chế độ, và web-logs chứa access log theo vai trò. Chỉ init/authority nhận dữ liệu ký theo nhu cầu; tamper không được mount khóa bí mật. Dữ liệu trust công khai có thể mount chỉ đọc vào secure. Thiết kế này cải thiện việc dùng chung toàn bộ lab-data của bản cũ.

```text
evidence/runs/<run_id>/
|-- manifest.json       # version, mode, revision, timestamps
|-- plain-dns.json      # phản hồi DNS gốc
|-- secure-dns.json
|-- plain-http.json     # attempted/status/IP/site_id
|-- secure-http.json
|-- raw-http/           # body/headers đã đo
|-- logs/               # đoạn log gắn lần thử
`-- comparison.json    # kết luận kèm căn cứ
```

Không commit .venv/, **pycache**/, khóa .private, log không cần thiết hoặc evidence lớn. Có thể commit một bộ bằng chứng mẫu đã rà soát và gắn nhãn “lần chạy mẫu”, tách khỏi dữ liệu live.

## 11 Cấu hình và nguyên tắc chạy backend

### Dashboard chạy trên host

Chọn Flask chạy trên máy trình bày để dùng Docker CLI hiện có, tránh phải mount Docker socket vào container web. Backend gọi compose exec client để worker thực hiện DNS và HTTP bên trong mạng Docker; trên Windows, không giả định host truy cập trực tiếp được bridge IP của web container.

Backend bind 127.0.0.1:8080, tắt debug/reloader khi demo. Các action, service và tên miền là danh sách cố định; subprocess dùng shell=False, timeout và đường dẫn Compose xác định. Chỉ nhận JSON cùng origin với token phiên; không có endpoint chạy lệnh shell từ người dùng.

### Thay đổi bắt buộc ở lab

1. Thêm web-good 172.30.53.80 và web-fake 172.30.53.90.
2. Đổi A hợp lệ của www sang .80; A giả tại relay sang .90.
3. Giữ control là tên không bị sửa, có thể trỏ web-good để kiểm tra thêm HTTP.
4. Ký lại zone, nạp lại BIND và cấu hình trust anchor công khai khớp khóa.
5. Cập nhật mọi assertion còn dùng 192.0.2.x; không để giá trị cũ sót trong UI hoặc test.
6. Bổ sung worker HTTP, JSON API và log web theo run_id.

### Hiển thị HTML và phạm vi truy cập

Chỉ cho worker kết nối tập IP và cổng web đã chốt; bỏ qua redirect tới địa chỉ khác. Nội dung website lab tự chứa. Preview dùng iframe sandbox không cho script/form/top-navigation; không gắn nguyên HTML không tin cậy vào DOM dashboard. Với HTTP bị bỏ qua, không tạo iframe preview từ dữ liệu cũ.

### HTTP và HTTPS trong lời giải thích

DNSSEC quyết định dữ liệu DNS có được tin để dùng hay không; HTTP là bước quan sát hậu quả tiếp theo. Hai website dùng HTTP trong mạng thử nghiệm. Nếu áp dụng HTTPS ngoài thực tế, chứng chỉ và kiểm tra TLS có thể chặn hành vi giả mạo bổ sung; không nói DNS sai tự động phá được HTTPS.

## 12 Quy trình triển khai theo giai đoạn

| Giai đoạn          | Nhiệm vụ cụ thể                                                                    | Điều kiện chuyển bước                                                 |
| ------------------ | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| 1 Chốt hợp đồng    | Chốt sơ đồ, IP, target, site_id, trường JSON, trạng thái UI và phép thử chấp nhận. | Cả nhóm diễn giải giống nhau về DNS→HTTP và giới hạn mô phỏng.        |
| 2 Hai web server   | Dựng trang tốt/giả, header site_id, log run_id; kiểm tra từ client container.      | HTTP tới từng IP nhận đúng nội dung và log được.                      |
| 3 Lab DNS cập nhật | Đổi IP, ký lại, kiểm tra plain/secure, can thiệp, proof và recover.                | Ba trạng thái DNS đạt; log xác nhận lỗi chữ ký.                       |
| 4 Worker truy cập  | DNS theo resolver → IP → HTTP; ghi attempted, connected_ip, status và site_id.     | plain đi trang giả khi ON; secure không HTTP; recovery đi trang đúng. |
| 5 Backend Flask    | Implement API, khóa tác vụ, runner, error mapping và evidence per run.             | API trả kết quả thật, lỗi rõ, không trộn hai mode.                    |
| 6 Frontend         | Sơ đồ SVG, hai panel, điều khiển, preview, bằng chứng và trạng thái cũ/mới.        | Đọc hiểu được ở máy chiếu; UI khớp API khi thành công và thất bại.    |
| 7 Tái lập          | Chạy test, người khác cài theo README, tổng duyệt và quay video thật.              | Có test report, evidence và kịch bản demo ổn định.                    |

### Lệnh dự kiến cho bản mới

```text
# Chỉ dùng SAU KHI đã triển khai cấu trúc mới
docker compose up -d --build
python -m venv .venv
.venv\Scripts\python -m pip install -r dashboard/requirements.txt
.venv\Scripts\python dashboard/app.py
# Mở http://127.0.0.1:8080
```

Các lệnh này là quy trình mục tiêu, chưa chạy được nguyên trạng trên repo hiện tại. run-dashboard.ps1/sh dự kiến gói việc kiểm tra phụ thuộc và mở backend; file Python cần tự xác định repo root từ **file** để không phụ thuộc thư mục đang đứng. Cài/build trước buổi học, không dùng CDN cho asset trình chiếu.

## 13 Ma trận kiểm thử chấp nhận chính

| Mã  | Kịch bản            | Kết quả bắt buộc                                                                                  |
| --- | ------------------- | ------------------------------------------------------------------------------------------------- |
| T01 | Baseline, hai nhánh | Đúng IP web-good; secure AD=true; cả hai HTTP 200, site_id legitimate và có access log.           |
| T02 | Attack qua plain    | Nhận IP web-fake; HTTP thật đến .90; site_id training-fake; log cùng run_id.                      |
| T03 | Attack qua secure   | SERVFAIL, không IP dùng được; attempted=false; không có HTTP request của nhánh secure.            |
| T04 | Phục hồi            | Sau OFF và flush, cả hai về web-good, secure xác thực lại thành công.                             |
| T05 | Đối chiếu chữ ký    | A gốc và qua relay khác nhau khi ON; có RRSIG A và giữ nguyên; không so sánh hash của chuỗi rỗng. |
| T06 | Tên đối chứng       | control không bị thay; secure vẫn xác thực; không phải validator hỏng toàn bộ.                    |
| T07 | BIND trực tiếp      | Vẫn trả IP hợp lệ khi relay ON; gắn nguyên nhân với can thiệp sau authoritative.                  |
| T08 | NXDOMAIN và TCP     | Câu trả lời âm được xác thực ở trạng thái tốt; TCP/UDP nhất quán trong phạm vi kiểm tra.          |

### Cách chứng minh nhánh secure không gọi website

Mỗi nhánh truyền run_id và branch_id riêng vào header HTTP. Kiểm tra attempted=false trong kết quả secure và không có access log tương ứng ở cả web-good/web-fake. Không suy từ việc panel không hiện ảnh để kết luận không có kết nối; cần kiểm tra worker và log máy chủ.

### Bằng chứng của truy cập nhầm

Phải đồng thời có: DNS qua plain trả IP .90; worker ghi connected_ip=.90; HTTP nhận nội dung/site_id của web-fake; access log chứa run_id. Thiếu một trong các căn cứ thì gắn nhãn chưa đủ bằng chứng thay vì tự cho PASS.

## 14 Kiểm thử lỗi và chất lượng trình bày

| Mã  | Tình huống lỗi                          | Hành vi mong đợi                                                                |
| --- | --------------------------------------- | ------------------------------------------------------------------------------- |
| E01 | Docker dừng hoặc dịch vụ không sẵn sàng | UI hiện lỗi hạ tầng, không giữ trạng thái thành công cũ như lần đo mới.         |
| E02 | DNS timeout                             | DNS transport_error, ad/rcode chưa biết; không HTTP và không tự gán lỗi chữ ký. |
| E03 | HTTP server dừng sau DNS hợp lệ         | Hiện DNS thành công nhưng HTTP lỗi; không đổi thành DNSSEC thất bại.            |
| E04 | Flush một resolver thất bại             | scenario ERROR kèm trạng thái thực tế; không thông báo mode chuyển hoàn tất.    |
| E05 | Bấm Attack và Query liên tiếp           | Khóa hoặc từ chối BUSY; kết quả không trộn revision.                            |
| E06 | Chuyển mode trong lúc đo                | Không cho can thiệp giữa DNS và HTTP; kết quả gắn đúng revision.                |
| E07 | Redirect hoặc IP ngoài danh sách        | Worker từ chối, ghi lỗi; không gọi mạng bên ngoài.                              |
| E08 | Preview từ lần chạy trước               | Gắn nhãn lịch sử hoặc ẩn; không hiện như trang đã tải ở lần bị chặn.            |
| E09 | Chỉ SERVFAIL nhưng không log khớp       | Hiện từ chối/chưa xác định nguyên nhân; không tự khẳng định chữ ký sai.         |

### Tiêu chí trực quan

Trên màn hình chính, người xem phải nhận ra tên miền đang thử, trạng thái can thiệp, hai resolver khác nhau ở đâu, mỗi bên đã kết nối tới đâu và vì sao secure dừng. Chi tiết dài chỉ mở khi cần. Thử ở 1366×768 và độ phóng phù hợp máy chiếu; không dùng màu làm tín hiệu duy nhất.

Kiểm tra UI bằng dữ liệu thành công, thất bại và đang chờ thực tế. Không dùng dữ liệu mock để nghiệm thu hành vi live. Nếu có chế độ phát lại evidence, ghi rõ “Phát lại lần chạy đã lưu”, run_id và thời điểm; tách khỏi chế độ truy vấn trực tiếp.

## 15 Kịch bản trình diễn trong 5 đến 6 phút

| Thời điểm | Thao tác trên giao diện                | Điều cần giải thích                                                               |
| --------- | -------------------------------------- | --------------------------------------------------------------------------------- |
| 0:00–0:45 | Mở dashboard, giới thiệu sơ đồ.        | Hai resolver cùng hỏi qua relay; website được tải bởi client lab.                 |
| 0:45–1:30 | Bình thường → Truy vấn và truy cập.    | Hai bên đến web-good; secure có AD và dữ liệu đã được xác thực.                   |
| 1:30–2:30 | Bật can thiệp → chạy lại.              | plain nhận IP giả và tải web-fake; secure dừng ở DNS, không gọi HTTP.             |
| 2:30–3:30 | Mở đối chiếu RRSIG và log.             | IP đổi nhưng chữ ký không đổi; validator báo nguyên nhân phù hợp.                 |
| 3:30–4:30 | Mở đối chứng BIND/control và HTTP log. | Dịch vụ vẫn hoạt động; chứng minh truy cập thật theo IP DNS trả.                  |
| 4:30–5:30 | Khôi phục → chạy lại → kết luận.       | Cả hai trở về web-good; DNSSEC bảo vệ dữ liệu DNS, không bảo đảm mọi lớp bảo mật. |

### Tổ chức buổi tổng duyệt

Build image, cài phụ thuộc và chạy kiểm thử trước. Dùng đúng máy trình bày, đồng bộ giờ, ký mới zone nếu cần, đưa mode về BASELINE. Người khác thao tác UI trong khi người phụ trách giải thích để tìm chỗ gây nhầm. Quay video một vòng thật cùng phiên bản và evidence.

### Phương án dự phòng

Nếu lỗi trình diễn, chuyển sang video đã quay hoặc chế độ replay được gắn nhãn rõ, không âm thầm phát kết quả cũ như đang live. Giữ CLI/dig và log làm công cụ kiểm chứng khi cô hỏi. Không cần sửa lỗi Docker kéo dài trước lớp.

### Câu kết luận đề xuất

“Ở cùng trạng thái can thiệp, máy khách không kiểm tra DNSSEC đã dùng IP giả và đến website giả lập. Máy khách dùng resolver xác thực từ chối dữ liệu không khớp chữ ký nên không thực hiện HTTP bằng IP đó. Khi trả lại dữ liệu nguyên vẹn, truy cập hợp lệ hoạt động trở lại.”

## 16 Tiêu chí hoàn thành và bàn giao

### Phạm vi bắt buộc

- [ ] Lab DNS ba trạng thái chạy ổn định.
- [ ] Hai web server thật, định danh và access log rõ.
- [ ] Worker thực hiện DNS rồi HTTP đúng IP trả về, không tra cứu lại bằng DNS khác.
- [ ] secure thất bại thì không gửi HTTP, có bằng chứng kiểm tra.
- [ ] Dashboard hiển thị kết quả thật, có lỗi/đang chờ/lịch sử rõ ràng.
- [ ] RRSIG, log và đối chứng hỗ trợ lời giải thích.
- [ ] Khôi phục hoạt động và không còn preview giả ở kết quả mới.
- [ ] Có test report, cấu hình, hướng dẫn tái lập, video dự phòng và người khác chạy lại được.

### Sản phẩm bàn giao

Repo DNSSEC với mã và cấu hình theo cây thư mục mục tiêu; README từ khởi động đến dừng; tài liệu API; kịch bản trình diễn; kiểm thử tự động và báo cáo kết quả; evidence của ít nhất một vòng hoàn chỉnh. Không ghi PASS cho bản web trước khi các phép thử tương ứng chạy thật.

### Thứ tự ưu tiên nếu thiếu thời gian

Ưu tiên DNS→HTTP và hai website trước, rồi API và hai panel. Animation, chế độ replay và hiệu ứng bổ sung làm sau khi lõi có bằng chứng đạt. Giữ giao diện một trang, chưa thêm đăng nhập, quản lý người dùng, hệ thống nhiều tên miền hay rollover.

### Khác biệt với đặc tả bản Terminal

Bản cũ chứng minh resolver chấp nhận/từ chối dữ liệu DNS trên Terminal với IP tài liệu. Bản mới bổ sung truy cập HTTP thật đến hai server nội bộ và lớp giao diện giải thích luồng. Các bằng chứng cũ được giữ làm tài liệu nền; không dùng để tuyên bố phần web mới đã hoàn thành.

## 17 Tài liệu kỹ thuật và thuật ngữ

| Thuật ngữ         | Cách dùng trong bản demo                                                                             |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| DNSKEY / RRSIG    | Khóa công khai và chữ ký RRset; chữ ký phải kiểm tra với dữ liệu và khóa được tin cậy.               |
| Trust anchor      | Khóa DNSKEY công khai được cài trước cho demo.test tại secure resolver.                              |
| AD / SERVFAIL     | AD diễn giải trong ngữ cảnh tin resolver; SERVFAIL là lỗi tổng quát cần log để xác định nguyên nhân. |
| site_id           | Định danh do web server trả, giúp đối chiếu máy chủ đã được HTTP truy cập.                           |
| run_id / revision | Định danh phép thử và phiên bản trạng thái kịch bản, dùng ghép bằng chứng và tránh lẫn kết quả.      |
| Live / replay     | Live là phép thử vừa thực hiện; replay là phát lại bằng chứng được ghi trước và phải gắn nhãn.       |

BIND DNSSEC Guide — Ký vùng và dữ liệu DNSSEC.

https://bind9.readthedocs.io/en/stable/dnssec-guide.html

Unbound configuration — Validator, trust anchor, stub và log.

https://unbound.docs.nlnetlabs.nl/en/latest/manpages/unbound.conf.html

Flask JavaScript fetch JSON — Giao tiếp frontend với API.

https://flask.palletsprojects.com/en/stable/patterns/javascript/

Python http.client — Kết nối HTTP trực tiếp tới IP và gửi Host phù hợp.

https://docs.python.org/3/library/http.client.html

Docker Compose networking — Địa chỉ, tên dịch vụ và phạm vi mạng Docker.

https://docs.docker.com/compose/how-tos/networking/

RFC 4033 và RFC 4035 — Mục tiêu, giới hạn; hành vi xác thực xem thêm RFC 4035.

https://www.rfc-editor.org/rfc/rfc4033

Kiểm tra phiên bản thực tế khi triển khai. Các API, IP, đường dẫn mới và lệnh trong bản đặc tả này là quyết định thiết kế; cần triển khai và kiểm thử trước khi đưa vào báo cáo như kết quả thực nghiệm.
