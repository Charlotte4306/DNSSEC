# Overview cũ và Terminal tự nhập

Ứng dụng có hai màn hình:

- **Overview**: giữ nguyên trang cũ, gồm giới thiệu, kịch bản, sơ đồ, hai panel kết quả, replay và bằng chứng. Các anchor `#story`, `#scenarios`, `#lab` vẫn hoạt động như trước.
- **Terminal**: chọn Terminal trên thanh điều hướng hoặc mở `/#/terminal`. Tự nhập lệnh trong ô `lab:~$`, Enter để chạy. Kết quả và trạng thái lab dùng chung với Overview; chuyển màn hình không chạy thêm phép đo.

## Chạy local

```powershell
docker compose up -d --build
.venv\Scripts\python.exe -B dashboard\app.py --port 18766
```

Mở `http://127.0.0.1:18766/`. Chỉ chạy một API server cho mỗi checkout. Chưa có `.venv` thì làm theo phần cài API trong README.

## Tự nhập lệnh

Không giới hạn vào một số kịch bản dựng sẵn: tự chọn resolver, tên thuộc zone `demo.test`, loại bản ghi và tùy chọn truy vấn.

```text
dig @secure www.demo.test A +dnssec
dig @plain www.demo.test A +short
dig @relay www.demo.test A +dnssec +multi
dig @authority demo.test DNSKEY +dnssec
dig @secure www.demo.test A +dnssec +cdflag
dig @secure not-present.demo.test A +dnssec
dig @secure control.demo.test A +dnssec +tcp
dig @authority demo.test SOA
logs secure tamper --tail 40
help
history
clear
```

`@secure`, `@plain`, `@relay`, `@authority` tương ứng IP `.30`, `.40`, `.20`, `.10` trong mạng `172.30.53.0/24`; có thể nhập trực tiếp các IP đó. Bỏ resolver thì dùng secure; bỏ tên thì dùng `www.demo.test`; bỏ loại thì dùng A. `help` liệt kê loại bản ghi và tùy chọn hỗ trợ. Phím ↑/↓ gọi lại lịch sử, Ctrl+L xóa màn hình. Lịch sử giữ tối đa 100 lệnh và 30 mục đầu ra trong bộ nhớ tab, không lưu qua reload.

Console hỗ trợ `dig`, `logs` và các lệnh giao diện `help/history/clear`. Đây là terminal chẩn đoán DNS trong lab; shell Linux đầy đủ dùng qua SSH riêng. Không thực thi chuỗi nhập qua shell. Parser chuyển cú pháp thành argv, chỉ cho truy vấn mạng lab và tên thuộc `demo.test`; không cho ghép lệnh, đọc file hay thêm tùy chọn không giới hạn. `logs` nhận các dịch vụ secure/plain/tamper/authority/web-good/web-fake với `--tail` từ 1–200.

`dig` chạy thật trong container authority dùng như máy chẩn đoán có sẵn công cụ; phép đo DNS → HTTP trên Overview vẫn chạy ở client. Đầu ra hiển thị khi lệnh hoàn tất, gồm stdout/stderr, exit code, thời điểm và trạng thái quá hạn/cắt đầu ra. Mỗi truy vấn có time=2/tries=1 và timeout container 8 giây; tổng stdout/stderr giới hạn 32 KiB. Không đổi mode, không flush cache hoặc ghi đè last_run_id; truy vấn vẫn có thể làm resolver nạp cache và phát sinh log. Lần chạy scenario tiếp theo flush như cũ.

API `POST /api/terminal/run` nhận `{"command":"dig @secure www.demo.test A +dnssec"}`. Trường command_id cũ còn tương thích, nhưng giao diện mới dùng command tự nhập. Hai trường không được gửi đồng thời. Terminal dùng chung khóa điều phối với job/scenario/proof, tác vụ trùng trả 409. Kết quả terminal là phép kiểm tra bổ sung mới; không gắn vào run_id của phép đo trước đó. Mất kết nối không tự gửi lại lệnh.

## Dùng khi trình bày

Sau phần DNSViz: “Vừa rồi nhóm quan sát một tên miền thật; bây giờ nhóm tự sửa một phản hồi trong lab để kiểm tra điều gì xảy ra.”

1. Overview: baseline → attack, đọc hai panel như trước.
2. Terminal: tự gõ truy vấn secure và plain; chỉ rõ SERVFAIL đối lập với A `.90`.
3. Thử `+cdflag` qua secure để yêu cầu resolver tắt kiểm tra cho truy vấn này và xem dữ liệu nhận lại. Không mô tả kết quả có CD là đã được xác thực.
4. Hỏi `control.demo.test` để chứng minh secure không hỏng toàn bộ; xem DNSKEY hoặc NXDOMAIN để giải thích thêm.
5. Về Overview, chạy recovery rồi xem bằng chứng/đối chiếu như trước.

Exit 0 của dig không chứng minh DNSSEC hợp lệ. AD phản ánh xác nhận từ resolver tin cậy; SERVFAIL riêng lẻ không chỉ rõ lỗi chữ ký. Lab dùng trust anchor cục bộ, NSEC, chưa dựng root → TLD. Relay sửa phản hồi có kiểm soát, không phải khai thác Kaminsky. DNSSEC không thay thế HTTPS.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests/dashboard -q
node tests/check_relay_replay.cjs
node tests/check_typed_terminal.cjs
```

Script terminal cần Playwright/Edge, Docker sẵn sàng và API local đang mở tại cổng 18766 (đổi bằng `LAB_URL` nếu cần). Nó đối chiếu nội dung Overview với bản HEAD cũ, chạy lệnh tự nhập, kiểm tra lịch sử/điều hướng/reload/mobile rồi chạy attack và recovery thật. Script kết thúc thành công để relay ở normal. Ảnh lưu tại thư mục tạm `dnssec-terminal`, hoặc đường dẫn `LAYOUT_ARTIFACTS`.
