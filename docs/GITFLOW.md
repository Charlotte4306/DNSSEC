# Git workflow cho DNSSEC Visual Lab

Quy trình làm việc của nhóm 3 người xây dashboard, lab DNSSEC và hai website minh họa theo `Specification.docx`. Dùng GitFlow rút gọn: `main` giữ bản ổn định, `develop` tích hợp công việc, mỗi nhiệm vụ có một nhánh riêng và được review qua pull request (PR).

Repo hiện có nhánh `main` và remote `origin` trỏ đến https://github.com/Charlotte4306/DNSSEC.git. Không cần chạy `git init` hoặc thêm `origin` lần nữa. Các lệnh bên dưới là hướng dẫn, không phải thao tác đã được thực hiện.

## 1. Các nhánh và quy tắc ghép

| Nhánh | Dùng để làm gì | Tạo từ | PR vào |
|---|---|---|---|
| `main` | Bản đã kiểm thử, sẵn sàng demo | Nhánh chính | Nhận bản phát hành từ `develop` |
| `develop` | Tích hợp các phần đã review | `main` lần đầu | `main` khi chốt bản demo |
| `feature/<ten-viec>` | Thêm một khả năng cụ thể | `develop` | `develop` |
| `fix/<ten-loi>` | Sửa lỗi của bản đang phát triển | `develop` | `develop` |
| `docs/<ten-tai-lieu>` | README, đặc tả, kịch bản, hướng dẫn | `develop` | `develop` |
| `hotfix/<ten-loi>` | Sửa khẩn cấp bản ổn định trước buổi trình bày | `main` | `main`, rồi đưa bản sửa về `develop` |

```text
main       o----------------------------------------M---tag v1.0.0
            \                                      /
develop      o----M------M------M------M-------------o
              \  /       \    /
feature        o-o         o--o
```

- Không push code trực tiếp vào `main` hoặc `develop` sau khi thiết lập nhóm.
- Mỗi nhánh xử lý một nhiệm vụ có sản phẩm kiểm tra được; không gom cả demo vào một PR.
- Tên nhánh dùng tiếng Anh không dấu, chữ thường và dấu gạch ngang.
- Không cần nhánh dài hạn theo tên người. Một người có thể lần lượt làm nhiều nhánh nhiệm vụ.
- Chưa cần `release/*` cho bài giữa kỳ. Chốt một đợt phát hành trực tiếp từ `develop` sang `main`.

## 2. Chia công việc và thứ tự phụ thuộc

### Nhánh mở đầu

`feature/project-contracts` tạo cấu trúc thư mục, thống nhất API, schema kết quả, IP, tên dịch vụ, site_id, run_id và quy tắc trạng thái UI. Chỉ tạo khung tối thiểu cần dùng; không đánh dấu chức năng chưa triển khai là đã hoạt động.

Phải review và ghép nhánh này trước khi ba người xây phần riêng. Đây là điểm thống nhất hợp đồng để giảm xung đột.

### Các nhánh triển khai

| Thứ tự | Nhánh đề xuất | Phạm vi | Điều kiện để ghép |
|---|---|---|---|
| 1 | `feature/dns-core` | BIND, ký zone, relay, Unbound plain/secure, trust anchor | DNS hợp lệ → bị sửa → khôi phục chạy đúng; có log và đối chứng |
| 1 song song | `feature/web-targets` | Hai web server, trang hợp lệ/giả lập, site_id và access log | Client gọi từng IP nhận đúng nội dung và log |
| 2 | `feature/dns-http-worker` | DNS theo resolver rồi HTTP đến đúng IP, xuất JSON | Plain đến trang giả khi bị sửa; secure dừng và không HTTP |
| 2 song song | `feature/dashboard-layout` | Bố cục hai panel, sơ đồ, trạng thái chờ/lỗi | Có thể review bố cục; dữ liệu mock được ghi nhãn và chỉ dùng phát triển |
| 3 | `feature/dashboard-api` | Flask, Docker runner, điều phối mode, khóa tác vụ | API dùng worker thật, lỗi rõ ràng và không trộn trạng thái |
| 4 | `feature/dashboard-live` | Nối UI với API, preview từ HTTP thật, bằng chứng | UI bỏ mock trong chế độ live; kết quả khớp phép thử thật |
| 4 | `feature/evidence-tests` | Lưu theo run_id, kiểm thử đầy đủ và tình huống lỗi | Báo cáo chỉ rõ ca đạt/chưa đạt, có bằng chứng |
| 5 | `docs/demo-handover` | README, lệnh chạy, tổng duyệt, kịch bản 5–6 phút | Một người khác chạy lại theo hướng dẫn được |

Nhóm có thể phân vai: người A làm DNS/lab; người B làm website/worker; người C làm dashboard. Đây là gợi ý theo mảng, không thay thế phân công nhân sự nhóm đã chốt. Mỗi người viết tài liệu và kiểm thử cho phần mình.

### Quy tắc tránh giẫm tệp

- Khi chuẩn bị chỉnh `compose.yaml`, Dockerfile, schema hoặc cấu hình IP, báo trước trong nhóm và giao một người điều phối bản chung.
- API/schema thay đổi phải cập nhật tài liệu cùng PR, báo người làm frontend và worker.
- Không ghép một thay đổi phá hợp đồng nếu phần còn lại chưa có cách tương thích hoặc kế hoạch tích hợp rõ.
- Ưu tiên PR nhỏ theo chức năng hoàn chỉnh. Không chia cơ học theo số tệp nếu làm bản tích hợp không thể chạy.

## 3. Thiết lập nhóm một lần

Người quản lý repo thực hiện tạo `develop` sau khi `main` đã có commit đầu tiên:

```powershell
git switch main
git pull --ff-only origin main
git switch -c develop
git push -u origin develop
```

Nếu `develop` đã tồn tại trên GitHub, không tạo lần nữa:

```powershell
git fetch origin
git switch --track origin/develop
```

Nếu đã có nhánh local `develop`, dùng `git switch develop` rồi `git pull --ff-only origin develop`.

Trên GitHub, thiết lập bảo vệ `main` và `develop` bằng branch protection hoặc ruleset phù hợp:

- Yêu cầu PR trước khi merge.
- Ít nhất một người khác review; không tự duyệt thay cho nhóm.
- Giải quyết các cuộc trao đổi trước khi merge.
- Chặn force push và xóa hai nhánh chính.
- Chỉ yêu cầu status check CI sau khi nhóm đã tạo workflow CI và xác nhận tên check thực tế.

Không yêu cầu CI chưa tồn tại vì sẽ làm mọi PR bị kẹt. Nếu tài khoản/repo không áp dụng được bảo vệ nhánh, nhóm vẫn tuân thủ quy ước PR thủ công.

## 4. Workflow hằng ngày của mỗi thành viên

### Bước 1 Kiểm tra và nhận việc

```powershell
git status
git fetch origin
git switch develop
git pull --ff-only origin develop
git switch -c feature/dns-core
```

Tên `feature/dns-core` là ví dụ; thay bằng đúng nhiệm vụ bạn nhận. Trước khi đổi nhánh, commit công việc đang làm hoặc dùng stash có chủ đích; không bỏ thay đổi chỉ để lệnh chạy được.

### Bước 2 Làm một phần có thể kiểm tra

Viết code, chạy kiểm tra liên quan, cập nhật README/schema nếu hành vi thay đổi. Sau đó xem diff trước khi commit:

```powershell
git diff
git status
git add <tep-can-commit>
git diff --cached
git commit -m "feat(dns): configure validating and plain resolvers"
```

`<tep-can-commit>` là chỗ điền đường dẫn thật, không gõ nguyên dấu ngoặc nhọn. Thêm tệp cụ thể thay vì dùng `git add .` mà chưa xem danh sách, để tránh đưa khóa hoặc evidence vào repo.

### Bước 3 Push và mở PR sớm

```powershell
git push -u origin feature/dns-core
```

Mở PR `feature/dns-core` → `develop`. Dùng Draft PR khi đang làm để nhóm theo dõi. Chuyển Ready for review khi đã đủ nội dung, kiểm thử và hướng dẫn kiểm tra.

### Bước 4 Nhận review và sửa

Commit các sửa tiếp trên cùng nhánh rồi `git push`. Không tạo nhánh mới chỉ để trả lời review. Reviewer kiểm tra cả kết quả và cách thực hiện, không chỉ xem ảnh giao diện.

### Bước 5 Sau khi PR được merge

```powershell
git switch develop
git pull --ff-only origin develop
git branch -d feature/dns-core
```

Với PR squash merge, Git có thể từ chối `branch -d` vì không thấy lịch sử được merge theo cách thông thường. Khi đó xác nhận PR đã merge và commit đã có trong `develop`; có thể giữ nhánh để kiểm tra, không cần ép xóa. Không dùng `-D` theo thói quen.

## 5. Quy ước commit

Mẫu: `type(scope): mô tả ngắn`. Chọn một ngôn ngữ thống nhất cho phần mô tả; các ví dụ sau dùng tiếng Anh.

| Loại | Dùng khi | Ví dụ |
|---|---|---|
| `feat` | Có chức năng mới | `feat(worker): fetch HTTP using the DNS answer IP` |
| `fix` | Sửa lỗi | `fix(ui): clear stale preview after DNS failure` |
| `test` | Thêm/sửa kiểm thử | `test(dns): assert no HTTP request after SERVFAIL` |
| `docs` | Tài liệu | `docs: explain local trust anchor and demo limits` |
| `refactor` | Sắp xếp code, giữ hành vi | `refactor(api): separate scenario orchestration` |
| `chore` | Cấu hình hoặc việc hỗ trợ | `chore: ignore generated evidence and private keys` |

Tránh commit kiểu `update`, `fix all`, `final`, `final2`. Một commit nên diễn đạt được một thay đổi cụ thể.

## 6. Nội dung một PR

Sao chép mẫu sau vào mô tả PR:

```markdown
## Vấn đề và kết quả
Thay đổi này giải quyết điều gì, hành vi trước/sau ra sao?

## Phạm vi
- Thành phần thay đổi:
- API/schema/cấu hình dùng chung có thay đổi không:

## Cách kiểm tra
1. Chuẩn bị:
2. Lệnh hoặc thao tác:
3. Kết quả mong đợi:

## Đã kiểm tra thực tế
- Lệnh/ca đã chạy và kết quả:
- Ca chưa chạy hoặc đang lỗi:
- Ảnh/log/run_id cần đối chiếu:

## Phụ thuộc và điểm cần review
- PR hoặc nhiệm vụ cần hoàn thành trước:
- Lưu ý khi tích hợp:
```

PR giao diện có ảnh trước/sau hoặc ảnh kết quả; PR DNS/HTTP có lệnh và bằng chứng phù hợp. Không viết “đã test” nếu chỉ đọc code. Không ghi các lệnh dự kiến chưa tồn tại trong repo như thể đã chạy.

## 7. Điều kiện merge và cách merge

### Feature, fix, docs vào develop

Người khác review và các lỗi quan trọng được xử lý. Chạy kiểm tra liên quan đến thay đổi; CI chạy các bước đã được cấu hình. Dùng **Squash and merge** để một PR thành một commit rõ nghĩa trên `develop`.

Không yêu cầu chạy toàn bộ lab cho một sửa lỗi chính tả. Với thay đổi mạng, trust anchor, mode hoặc DNS→HTTP, phải chạy lại các ca tích hợp chịu ảnh hưởng.

### Develop vào main

Tạo PR `develop` → `main`, dùng **Create a merge commit**, không squash/rebase nhánh tích hợp dài hạn. Chốt bản chính khi:

- Baseline: hai nhánh đến website đúng, secure có AD.
- Attack: plain nhận IP giả và truy cập website giả lập thật.
- Secure ở trạng thái attack: từ chối DNS, không gửi HTTP.
- RRSIG/log/đối chứng khớp với lời giải thích.
- Recovery: hai nhánh trở về website đúng, không dùng preview cũ.
- README chạy được trên máy trình bày và có evidence/video dự phòng.

Sau merge, đưa lịch sử `main` trở lại `develop` bằng merge thông thường nếu cần; không reset `develop` để khớp `main`.

```powershell
git fetch origin
git switch develop
git pull --ff-only origin develop
git merge origin/main
git push origin develop
```

Nếu nhánh được bảo vệ không cho push trực tiếp, thực hiện bước đồng bộ qua PR riêng thay vì bỏ bảo vệ nhánh.

## 8. Cập nhật nhánh đang làm và xử lý conflict

Để giữ lịch sử dễ theo dõi, nhóm dùng **merge develop vào nhánh nhiệm vụ**, không force push nhánh đang chia sẻ:

```powershell
git fetch origin
git switch feature/dashboard-api
git merge origin/develop
```

Nếu conflict:

1. Chạy `git status`, đọc từng tệp bị xung đột.
2. Trao đổi với người sửa phần đó; ghép theo hành vi đúng, không chọn toàn bộ “ours/theirs” chỉ để hết lỗi.
3. Bỏ các dấu `<<<<<<<`, `=======`, `>>>>>>>`, giữ nội dung cuối cùng.
4. Chạy lại kiểm tra phần liên quan rồi `git add <tep>` và `git commit`.
5. `git push` để cập nhật PR.

Nếu chưa muốn giải quyết và merge chưa hoàn tất, dùng `git merge --abort` để quay lại trước lần merge. Không dùng `git reset --hard` hoặc `git clean -fd` để xử lý conflict thông thường.

## 9. Chốt phiên bản và sửa khẩn cấp

Sau khi PR `develop` → `main` được duyệt và merge, tạo tag tại commit đúng trên `main`:

```powershell
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m "DNSSEC Visual Lab demo-ready"
git push origin v1.0.0
```

Chỉ tạo tag nếu chưa có tên đó. `v0.1.0` có thể dùng cho lab DNS chạy được, `v0.2.0` cho DNS→HTTP đạt, `v1.0.0` cho bản trình diễn hoàn chỉnh; đây là gợi ý, không phải các phiên bản đã có.

Nếu phát hiện lỗi ở bản ổn định:

1. Tạo `hotfix/<ten-loi>` từ `main` mới nhất.
2. Sửa tối thiểu, chạy ca liên quan và mở PR vào `main`.
3. Sau merge, tạo tag vá như `v1.0.1`.
4. Đưa cùng sửa đó về `develop` qua một PR đồng bộ, tránh lỗi xuất hiện lại khi phát hành lần sau.

Không thêm chức năng lớn qua hotfix sát giờ trình bày.

## 10. Tệp nên và không nên đưa lên Git

**Nên commit:** code, cấu hình không chứa bí mật, Dockerfile/Compose, tệp phụ thuộc, kiểm thử, README, đặc tả và kịch bản. Các tài nguyên giao diện cần chạy offline cũng thuộc repo.

**Không commit mặc định:** `.venv/`, `__pycache__/`, khóa bí mật `.private`, tệp `.env` chứa giá trị riêng, log runtime, evidence dung lượng lớn và video. Dùng `.env.example` cho giá trị mẫu khi cần.

Đề xuất nội dung `.gitignore` khi bắt đầu code:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.env
*.private
evidence/runs/
*.log
```

Không bỏ qua toàn bộ `*.json` hoặc `*.yaml`: đó có thể là cấu hình và dữ liệu kiểm thử cần giữ. Có thể commit một bộ evidence mẫu đã rà soát trong thư mục riêng và gắn nhãn rõ; nó không thay thế kết quả live.

Với `Specification.docx`, Git không ghép nội dung Word tốt như mã nguồn. Chỉ một người sửa file tại một thời điểm. Ghi thay đổi kỹ thuật trong Markdown cùng PR nếu cần review rõ, rồi cập nhật Word theo phiên bản đã thống nhất.

## 11. Checklist ngắn trước khi kết thúc buổi làm

- Đang đúng nhánh nhiệm vụ, không làm trực tiếp trên `main`.
- Đã xem `git diff` và danh sách tệp trước khi commit.
- Không đưa khóa/log/tệp môi trường không cần thiết vào repo.
- Commit đã push để nhóm không mất công việc nếu máy có sự cố.
- PR/issue ghi phần đã xong, đang vướng và bước tiếp theo.
- Nếu đổi API, IP, Compose hoặc schema, người phụ thuộc đã được báo.

**Luồng nhớ nhanh:** nhận việc → cập nhật develop → tạo nhánh → làm và kiểm tra → push → PR vào develop → người khác review → squash merge → kiểm thử tích hợp → PR develop vào main → merge commit → tag bản demo.
