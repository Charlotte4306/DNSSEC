# Motion UI cho DNSSEC Visual Lab

Tham khảo [Lee Holmes, phần Services](https://www.leeholmes.uk/#services): chữ
lớn, khoảng trắng, hiện chữ khi cuộn và tương tác nhãn khi hover. Bản DNSSEC
được viết riêng bằng HTML/CSS/JavaScript; dùng font hệ thống, không chép code,
ảnh, font hay nội dung từ trang tham khảo. Không thêm CDN hoặc thư viện animation.

## Hướng thiết kế

- Nền trắng `#ffffff`, nền lab `#f6f6f3`, chữ `#1c1c1a`, chữ phụ `#66665f`.
  Xanh `#176448` và đỏ `#a42c35` dành cho trạng thái kết quả trong lab.
- Arial/Segoe UI cho chữ lớn và nội dung; Consolas cho địa chỉ/thông số.
- Đầu trang giới thiệu bằng typography và nét mạng. Phần kịch bản có tiêu đề
  bên trái, ba hàng tương tác bên phải. Lab thật là một vùng riêng; có lối vào
  trực tiếp từ menu và skip link, không bắt người thuyết trình cuộn hết phần đầu.
- Chỉ tiêu đề và nhãn trang trí có hiệu ứng chữ; dữ liệu đo luôn đọc ổn định.

## Trải nghiệm

1. Cuộn trang: tiêu đề lộ dần theo từng dòng, thanh đọc chạy theo vị trí cuộn.
2. Hover/focus menu hoặc nhãn kịch bản: chữ được đảo ký tự ngắn rồi trở lại.
3. Di chuột/chạm/Tab vào ba hàng kịch bản: sơ đồ giải thích đổi theo tình huống.
   Đây là minh họa cơ chế cố định, không gửi POST và không đổi radio hay relay thật.
4. Nét mạng nền dịch nhẹ theo con trỏ trên phần giới thiệu; không tự chạy vòng
   render liên tục và không được gọi là dữ liệu bắt gói.
5. Hover/focus node của sơ đồ lab: hiện giải thích vai trò thành phần.
6. Nút Hiệu ứng bật/tắt lưu lựa chọn trên trình duyệt. Hệ thống có
   prefers-reduced-motion sẽ tắt hiệu ứng. Touch vẫn dùng nút chọn/focus được.

API và vòng đời đo trong app.js giữ nguyên. Lab vẫn hỏi DNS, thực hiện HTTP,
đọc evidence và preview từ worker; không dùng hiệu ứng để dựng kết quả thành
công. Các câu số liệu, IP, run_id, AD, SERVFAIL và timing không bị scramble.

## Tệp thay đổi

| Tệp | Nội dung |
|---|---|
| templates/index.html | Ba vùng giới thiệu/kịch bản/lab, menu, toggle và chú thích. |
| static/css/app.css | Thiết kế trắng–đen, mask reveal, hover, responsive, reduced motion. |
| static/js/motion.js | IntersectionObserver, canvas minh họa, hover, focus và preference. |
| tests/check_dashboard_layout.cjs | Kiểm tra motion riêng rồi chạy tiếp các ca lab thật đã có. |

motion.js dùng IntersectionObserver để hiện tiêu đề một lần; requestAnimationFrame
chỉ cập nhật khi có scroll/pointer event. ResizeObserver chỉnh canvas theo kích
thước và mật độ điểm ảnh. Hiệu ứng cuộn dùng scroll native, không chiếm wheel
hay ép snap. Script motion không có fetch, không truy cập dữ liệu đo của app.js.

## Chạy xem local

```powershell
.\.venv\Scripts\python.exe dashboard/app.py --port 18766
```

Mở http://127.0.0.1:18766/ để xem từ đầu, hoặc http://127.0.0.1:18766/#lab để
đi thẳng tới phòng thử nghiệm. Cần Docker lab sẵn sàng để bấm chạy. Hiệu ứng và
phần giải thích vẫn đọc được khi API chưa kết nối; các nút đo bị khóa theo health.

Bản UI này đang chỉnh trên feature/dashboard-layout, chưa tự commit/push hoặc
cập nhật VPS. itscharlotte.tech tiếp tục dùng bản trước cho đến khi triển khai.

## Kiểm tra đã chạy

Edge headless trên Docker local: 23 nhóm đạt. Bao gồm reveal/hover không có
POST, focus bàn phím, giữ preference sau reload, system reduced motion, tooltip,
menu vào lab và các ca DNS→HTTP thật, proof, download, stale, offline, API lỗi.

Vòng cuối có run baseline `6a030752-c6c2-4892-b3de-d4b3ea2a224d`, attack
`e8d578fa-6266-4e3f-9402-c16bd6c05a33`, recovery
`d907f628-2f2b-49a6-b8bb-a6928271a75c`.

Đã review ảnh desktop/mobile. Ở 1366×768, sau khi vào lab, tiêu đề không bị menu
che và đáy hai panel kết quả nằm ở khoảng 748 px. Bằng chứng dài mở theo yêu cầu.
Ở 390×844, không tràn trang ngang; sơ đồ DNS cuộn ngang trong khung riêng.
Chưa thử máy chiếu thực, screen reader hoặc mọi trình duyệt.
