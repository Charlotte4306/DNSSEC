# Kawaii dashboard tích hợp dữ liệu thật

Nhánh feature/demo-ui-integration bắt đầu từ develop 253bd75 và tích hợp origin/feature/demo-ui ab0bc32 bằng merge chưa commit. Năm conflict ở app.py, HTML/CSS/JS và tài liệu layout được giải quyết bằng cách giữ backend mới và port phần trình bày.

Dashboard dùng cùng Job API, worker, evidence, integrity, preview sandbox, khóa điều phối và cấu hình HTTPS đã kiểm thử. Không đưa fixtures hoặc server ui_preview lên ứng dụng production. Kawaii CSS và JS riêng được nạp sau asset nền; Nunito WOFF2 cùng giấy phép OFL chạy offline, IP/số đo giữ monospace. Đã sửa unicode-range cho Nunito 500.

Nút chọn kịch bản giữ vùng bấm native bên trên hiệu ứng hover. Animation trang trí chạy hữu hạn; toggle và prefers-reduced-motion tắt mọi animation. DNS/HTTP chỉ pulse khi có sự kiện thật. Trạng thái xanh lá / cam / đỏ vẫn phân biệt xác thực, can thiệp và lỗi. Hai panel nằm trong vùng 1366×768, timeline ở bên dưới.

Preview có banner dữ liệu phát lại và source=mock, không được dùng làm bằng chứng đo. Server chặn traversal, không trả integrity verified=true, cursor không phát lại sự kiện trùng và yêu cầu đồng thời trả 409. Run preview liên kết đúng job_id mock để nút xem lại hoạt động.

Panel replay hình máy tính (`static/js/replay.js` + `static/css/replay.css`, `replay.css` nạp sau `kawaii.css`) được chép nguyên sang `dashboard/static/` và `dashboard/templates/index.html`, nằm giữa hai panel resolver và mục "Bằng chứng lần chạy". Bản production bỏ nhãn `relay · BIND: minh họa` vì các bước relay và BIND đến từ worker thật; badge "Minh họa kịch bản" vẫn báo rõ khi đang phát script dựng sẵn chứ không phải số đo. Hook nối là một dòng `CustomEvent("dnssec:event")` sau khi `app.js` thêm mốc vào timeline; scene chỉ vẽ từ dữ liệu đó, không tự suy diễn bước mật mã. SVG giữ tỉ lệ 1210×560, vì thế cao theo cột nội dung; dưới 1000px thì `.replay-stage` cuộn ngang.

Kiểm tra:

```powershell
python -m unittest discover -s tests/dashboard -q
python -m unittest discover -s tests/preview -q
node tests/check_dashboard_layout.cjs
```

Kết quả local: 46 test backend và 5 test preview qua. Browser/Docker chạy bình thường → can thiệp → khôi phục: HTTP access log lần lượt 2 → 1 → 2, secure không kết nối HTTP khi SERVFAIL; reload/reconnect, reduced motion, font offline, keyboard/hover và mobile đều qua. Hai panel kết thúc khoảng 756 px ở viewport 1366×768.

Triển khai tới itscharlotte.tech theo deploy/README.md, sao lưu source trước khi thay, giữ evidence và Docker volumes. Các thay đổi chưa được agent commit hoặc push.
