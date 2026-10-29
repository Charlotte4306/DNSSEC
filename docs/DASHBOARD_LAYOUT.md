# Dashboard layout — bản minh họa để review

Phạm vi `feature/dashboard-layout`: HTML/CSS/JavaScript và sơ đồ SVG, chưa có Flask,
API, điều khiển Docker hoặc truy vấn mạng lab. Nhãn nguồn dữ liệu luôn hiện trên
đầu trang. Đây chưa phải sản phẩm nghiệm thu thực nghiệm DNSSEC.

## Chạy trên máy

Từ thư mục gốc repo, dùng Python đã cài trên host:

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory dashboard
```

Mở http://127.0.0.1:8080/templates/index.html. Dừng bằng Ctrl+C trong terminal.
Không cần Docker, npm, tải font hay CDN. Không mở trực tiếp HTML bằng file://.
Nếu cổng 8080 bận, chọn cổng khác trong lệnh và URL. Đây là server xem file tĩnh;
không gọi lệnh `python dashboard/app.py` vì backend chưa được triển khai.

## Ý đồ thiết kế

- Bảng màu: nền xanh xám `#edf2f8`, bề mặt trắng `#ffffff`, chữ xanh đậm
  `#18334e`, hành động xanh `#235b9d`, xác thực xanh lá `#176448`, cảnh báo đỏ
  `#a42c35`. Có nhãn chữ đi kèm màu để phân biệt trạng thái.
- Segoe UI/Tahoma cho tiếng Việt, Consolas cho địa chỉ và dữ liệu DNS; dùng font
  hệ thống để trình chiếu offline. Tiêu đề canh trái, số liệu cùng vị trí hai bên.
- Sơ đồ mạng là điểm nhấn duy nhất. Bỏ hiệu ứng nền và các thẻ số trang trí để
  người xem tập trung vào resolver và điểm dừng trước HTTP.
- Bố cục: điều khiển → đường đi DNS → hai panel đối chiếu → bằng chứng mở rộng.
  Ở 1366×768, nội dung kết quả chính nằm trên màn hình; log mở riêng khi cần.
  Màn hình hẹp chuyển về một cột; sơ đồ có thể cuộn ngang.

## Các tệp và kiến thức trọng tâm

| Tệp | Vai trò |
|---|---|
| `dashboard/templates/index.html` | Cấu trúc trang, điều khiển, SVG inline có mô tả cho trình đọc màn hình, hai panel và vùng bằng chứng. |
| `dashboard/static/css/app.css` | Màu, bố cục, trạng thái, responsive, focus bàn phím và reduced motion. |
| `dashboard/static/js/mock-data.js` | Tạo fixture có `source: mock`, không thực hiện DNS/HTTP; là schema UI tạm, không tuyên bố trùng toàn bộ JSON worker. |
| `dashboard/static/js/app.js` | Vòng đời minh họa, render dữ liệu, hủy, đánh dấu cũ, xóa preview, xuất JSON mẫu. |

`app.js` tách việc nhận dữ liệu khỏi việc vẽ panel qua `renderBranch`. Nhánh
dashboard-live sẽ cần adapter dữ liệu worker thật; không chỉ đổi mock thành fetch
rồi giả định mọi trường đã tương thích. Kết quả secure SERVFAIL không có iframe
và hiển thị rõ không gửi HTTP. AD=0 ở plain dù website đúng vẫn ghi chưa xác thực.

Preview dùng iframe sandbox rỗng, `srcdoc` chỉ chứa HTML mẫu cố định, không có
script/form. Không lấy URL trang giả bằng trình duyệt người xem. Khi tích hợp live,
dùng endpoint preview đã làm sạch từ nội dung worker tải; không gắn HTML API vào
DOM và không sử dụng iframe mẫu để thay thế kết quả thực.

Khoảng chờ 900 ms và nét đứt chuyển động chỉ minh họa tiến trình, không phải số
đo thời gian mạng. `created_at` là lúc tạo fixture. Mã `mock-*` tránh nhầm với run
thật. Chưa có raw DNS/log/chữ ký giả mang nhãn thực nghiệm; JSON nêu rõ giới hạn.

## Review bằng tay

1. Vào trang: chưa có kết quả, hai panel trống và nguồn mock luôn hiện.
2. Bình thường → Chạy minh họa: hai IP `.80`, HTTP 200; chỉ secure AD=1.
3. Chọn Can thiệp: kết quả cũ bị làm mờ, iframe cũ được gỡ ngay. Chạy lại:
   plain `.90`/training-fake, secure SERVFAIL/HTTP không gửi, không có iframe secure.
4. Xem vì sao → vùng JSON và giải thích mở. JSON có `source: mock`. Thử tải và
   sao chép; nếu clipboard bị trình duyệt chặn, dùng tải JSON.
5. Khôi phục → chạy: cả hai trở lại `.80`, không giữ trang giả từ lần trước.
6. Mở Tình huống để review giao diện: chọn DNS timeout, HTTP lỗi, lab không sẵn
   sàng; chạy từng ca, kiểm tra không báo tấn công thành công từ lỗi hạ tầng.
7. Bấm Hủy trong lúc đang chờ: không xuất hiện kết quả muộn, preview cũ bị xóa;
   điều khiển được bật lại. Khi đang chờ không đổi kịch bản/fixture được.
8. Kiểm tra ở 1366×768 và 390×844; dùng Tab/Enter, phóng chữ, reduced motion.

Kiểm thử layout không thay thế `worker.ps1 test` hay kiểm thử live. Trong nhánh
này không thay compose, worker, cấu hình DNS, website đích hoặc API chung.

## Bước tiếp theo theo GitFlow

Commit và PR `feature/dashboard-layout` → `develop` để review. Sau khi merge,
nhánh `feature/dashboard-api` triển khai Flask, Docker runner và khóa tác vụ;
`feature/dashboard-live` mới nối UI tới API, bỏ fixture khỏi chế độ live, ghép
preview/bằng chứng thật. Chưa được mô tả bản layout là đang chặn tấn công thật.


## Kiểm tra trình duyệt tự động

`tests/check_dashboard_layout.cjs` tự mở server tĩnh cổng tạm, dùng Edge headless,
chạy các thao tác rồi đóng server/trình duyệt. Công cụ này chỉ cần khi phát triển;
xem layout thông thường vẫn chỉ cần Python. Cần Node.js và package Playwright.
Ví dụ cài công cụ ngoài repo để không thêm node_modules vào dự án:

```powershell
npm install --prefix "$env:TEMP\dnssec-ui-tools" playwright
$env:NODE_PATH = "$env:TEMP\dnssec-ui-tools\node_modules"
node tests/check_dashboard_layout.cjs
```

Script mặc định dùng Microsoft Edge trên Windows; đặt `EDGE_PATH` nếu nằm ở nơi
khác. Ảnh mặc định lưu ở `$env:TEMP\dnssec-layout-review`; có thể đổi bằng biến
`LAYOUT_ARTIFACTS`. Không lưu ảnh/log runtime vào Git.

Đã chạy thực tế bằng Edge headless: 18 nhóm kiểm tra đạt, không có lỗi JavaScript,
không có request API hay mạng ngoài. Bao gồm baseline/attack/recovery, DNS/HTTP/
hạ tầng lỗi, điều khiển khi chờ, hủy không có kết quả muộn, bỏ preview cũ,
sandbox, JSON mock và tải file, responsive 1366×768/390×844, reduced motion.
Đã mở ảnh desktop/mobile để review. Hai panel kết quả nằm trong chiều cao 768 px;
bằng chứng và chú thích có thể cần cuộn. Chưa kiểm tra tích hợp backend, clipboard
trên mọi trình duyệt hoặc nghiệm thu trình đọc màn hình.
