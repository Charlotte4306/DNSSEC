# Evidence và nghiệm thu backend

Nhánh `feature/evidence-tests` tạo từ develop đúng GitFlow. Phần này có thể làm
song song với dashboard-layout. Không sửa HTML/CSS/JavaScript, không deploy lại
VPS và chưa nhận là đã hoàn thành các kiểm tra UI/UX.

## Kết quả của feature

- Mỗi POST /api/run lấy và lưu đối chiếu A/RRSIG khi vẫn giữ khóa tác vụ.
- Mỗi run có checksums.json để kiểm tra các tệp raw, log, proof, preview và summary.
- GET /api/runs/<id>/integrity trả trạng thái xác minh tệp.
- Audit offline so khớp worker/summary/body/log/proof và phát hiện bằng chứng lẫn run.
- Bộ nghiệm thu local chạy T01–T08 và lỗi E01–E09; phân biệt live với unit test.
- Lỗi bootstrap mode thiếu changed_at được sửa cùng regression test khởi tạo.

Các thay đổi deploy chưa commit trước khi chuyển nhánh đã được giữ ở bản sao
và patch riêng bên ngoài repo. deploy/, dashboard/wsgi.py và .vscode/ đang là
tệp ngoài phạm vi feature; không đưa vào commit evidence. Không phục hồi nguyên
app.py từ bản sao cũ đè lên phần evidence mới: khi quay lại layout cần ghép các
thay đổi deploy vào code mới. Website trên VPS vẫn dùng bản đã deploy trước đó.

## Chạy kiểm tra

Dừng app.py/Gunicorn local trước khi chạy nghiệm thu; single_server lock ngăn
hai bộ điều phối cùng sửa lab. Docker Desktop phải đang chạy Linux containers,
lab đã sẵn sàng và .venv đã cài dashboard/requirements.txt.

```powershell
docker compose up -d --build
.\.venv\Scripts\python.exe -m unittest discover -s tests/dashboard -v
.\verify.ps1 -Faults
```

Lệnh tương đương, dùng cả trên Linux:

```bash
.venv/bin/python tools/acceptance.py --faults
```

`--faults` cố ý pause tamper hoặc stop client/web-good/plain trong project lab
local hiện tại. Script ghi thao tác cần undo, khôi phục trong finally và đo một
lần recovery cuối. Nó không tắt Docker daemon, không gọi SSH, không gọi API VPS,
và từ chối Docker endpoint TCP/SSH. Nếu tiến trình bị kill cứng, cần kiểm tra
docker compose ps và unpause/start dịch vụ còn dừng trước khi chạy demo tiếp.

Chạy `tools/acceptance.py` không có --faults chỉ chạy các ca chính/unit: E01–E06
bị SKIP, báo PARTIAL, mã thoát 2. Mã 0 chỉ khi backend đã đủ ca và đạt; mã 1 là
có lỗi. Kiểm tra UI luôn ghi SKIP theo yêu cầu hiện tại, không biến thành PASS.

## Các tệp evidence

```text
evidence/runs/<run_id>/
  worker.json             # DNS/HTTP gốc, gồm body HTTP gốc
  http-access.json        # log đúng run_id/branch
  dns-context.log         # log Unbound/relay trong cửa sổ thời gian
  proof.json              # A/RRSIG lấy bổ sung cùng revision, nếu thu được
  preview-plain.html      # chỉ khi có body HTTP 200
  preview-secure.html     # không có khi nhánh không HTTP
  checksums.json          # SHA-256 của tập tệp giới hạn
  result.json             # summary và bằng chứng, xuất bản cuối

evidence/runs/acceptance-<UTC>-<id>/
  report.json
  report.md
  diagnostics.json        # truy vấn authority/control/NXDOMAIN/TCP thật
  host-unit.log
  client-unit.log
```

Nếu không lấy được proof/log, result ghi collection_errors và proof=null thay
vì tự tạo dữ liệu. Đối chiếu được lấy trong khóa run; snapshot trước/worker/sau
và sau proof phải nhất quán. Khi external CLI đổi mode giữa chừng, run bị đánh
dấu inconsistent, interpretation inconclusive và không cấp preview.

`proof.json` chứa run-adjacent queries, không phải cùng gói DNS của worker.
consistent_with_run chỉ khẳng định cùng revision ổn định. Log DNS vẫn ghi rõ
time_window_only_not_exact_run_id; một dòng signature crypto failed trong cửa
sổ thời gian chưa tự chứng minh thuộc đúng truy vấn nào. Không chỉ từ SERVFAIL
mà tự gán nguyên nhân lỗi chữ ký.

## Integrity khác với tính xác thực

checksums.json chỉ cho biết byte của tệp còn khớp lúc ghi. Người có thể sửa cả
tệp và manifest vẫn có thể làm hash khớp; đây không phải chữ ký số, bằng chứng
chống chối bỏ hoặc bước xác thực DNSSEC độc lập.

API chỉ kiểm tra tên tệp trong allowlist, không cho manifest đọc đường dẫn tùy
ý, từ chối symlink và giới hạn kích thước. Nếu tệp có manifest bị đổi/mất, GET
result và preview trả 409 EVIDENCE_CORRUPT. Result được xuất bản sau khi các tệp
và manifest đã ghi xong; thư mục ghi dở không được coi là một run hoàn thành.

Run cũ trước feature không có manifest vẫn đọc được để tương thích, nhưng
integrity báo unavailable/verified=false, audit không coi là đã xác minh.

## Audit offline

Chạy từ thư mục gốc repo; công cụ dùng stdlib, không cần Docker đang chạy:

```powershell
python tools/audit_evidence.py evidence/runs/<run_id>
```

Thay <run_id> bằng ID thật. Audit kiểm tra hash tệp, run_id/branch, DNS và HTTP
summary khớp raw, tính lại hash body, IP kết nối đúng IP DNS, site_id khớp đích,
access log đúng Host/path/status, nhánh không HTTP không có body/preview/log.
Nó cũng đối chiếu RRSIG A không rỗng, nguyên văn hai phía và hash chữ ký đã lưu.

Audit dành cho một phép đo ổn định có đủ bằng chứng. Run lỗi hoặc đổi mode có
thể có checksum hợp lệ nhưng audit không đạt: đây là kết quả được ghi lại trung
thực, không phải tự biến thành thí nghiệm thành công. Audit không độc lập xác
thực chữ ký DNSSEC bằng khóa; Unbound mới thực hiện phần xác thực của lab.

## Ma trận nghiệm thu

| Mã | Điều được kiểm tra | Nguồn |
|---|---|---|
| T01 | Baseline hai nhánh .80, HTTP 200/site legitimate, secure AD | Docker thật |
| T02 | Plain nhận .90, kết nối .90, trang giả và access log cùng run | Docker thật |
| T03 | Secure SERVFAIL, không IP/HTTP và không access log | Docker thật |
| T04 | Recovery về .80, có evidence hợp lệ, khác run ID trước | Docker thật |
| T05 | A gốc .80, relay .90, RRSIG không rỗng/giữ nguyên và lưu theo run | Docker thật + audit |
| T06 | control.demo.test vẫn được secure xác thực khi attack | Docker thật |
| T07 | BIND trực tiếp vẫn trả .80 khi relay sửa dữ liệu | Docker thật |
| T08 | NXDOMAIN có AD ở baseline, TCP/UDP nhất quán ở baseline/attack | Docker thật |
| E01 | Stop client: health/API lỗi hạ tầng, không báo run mới đạt | Docker thật |
| E02 | Pause relay sau flush: DNS timeout, AD/rcode null, không HTTP | Docker thật |
| E03 | Stop web-good: DNS vẫn thành công, HTTP lỗi đúng tầng | Docker thật |
| E04 | Stop plain làm flush lỗi: mode thực attack nhưng chưa ready | Docker thật |
| E05 | Trong run thật, scenario/run khác nhận 409 | Docker thật + thread đồng thời |
| E06 | CLI đổi mode trong cửa sổ request: run inconsistent, không preview | Docker thật + hook chỉ để định thời điểm |
| E07 | Redirect không có request thứ hai, IP ngoài allowlist bị chặn trước kết nối | Unit test có mock HTTP |
| E08-API | Run bị chặn không có preview, nội dung cũ chỉ truy cập qua ID cũ | Docker thật/API |
| E08-UI | Nhãn cũ/iframe trên giao diện | SKIP, quay lại cùng UI/UX |
| E09 | SERVFAIL không có log crypto chỉ mang nhãn blocked chung | Unit test có runner giả |

E06 không fake kết quả DNS: hook đợi compare thật hoàn thành rồi đổi relay bằng
CLI trước snapshot cuối. Đây là phép thử cửa sổ request, không tuyên bố đã chèn
chính xác vào thời điểm giữa DNS và HTTP của worker.

## Kết quả đã chạy

- Host: 32 test đạt sau khi bổ sung các ca corruption/legacy/reporting.
- Trong vòng acceptance live: 28 host test lúc đó và 25 client test đã đạt.
  Client suite gồm cả một số phép thử DNS/HTTP thật trong Docker.
- Acceptance --faults: 23 ca PASS, 0 FAIL, 1 SKIP (E08-UI).
- Audit offline run attack thật: 20 điều kiện đạt.
- Mọi dịch vụ local đã running/healthy trở lại; relay attack=false sau final recovery.
- Không thay đổi dịch vụ trên VPS trong feature này.

Báo cáo runtime:
`evidence/runs/acceptance-20261029T091820Z-2e438554/report.md`.
Run attack dùng cho audit: `c7db2456-bd37-4734-acb3-3247b3900f56`.
Các tệp runtime ở evidence/runs đã được gitignore, không đưa vào commit.

## Tệp code và kiến thức trọng tâm

| Tệp | Vai trò |
|---|---|
| dashboard/services/scenario_service.py | Tự lấy proof trong cùng lock và kiểm tra revision sau proof. |
| dashboard/services/evidence_service.py | Ghi đủ artifact trước khi công bố result; từ chối evidence hỏng. |
| dashboard/services/evidence_integrity.py | Manifest SHA-256 có allowlist/kích thước, tương thích run cũ. |
| dashboard/services/evidence_audit.py | So khớp các lớp raw, summary, HTTP body, log và proof offline. |
| tools/audit_evidence.py | CLI audit một run. |
| tools/acceptance.py | Chạy ma trận T/E, phân loại live/unit/skip và khôi phục local lab. |
| verify.ps1 | Lệnh chạy thuận tiện trên Windows. |
| tests/dashboard/test_evidence.py | Hỏng tệp, thiếu log/proof, lẫn run ID, ghi dở, legacy JSON lỗi. |
| tests/dashboard/test_acceptance_report.py | Bỏ qua ca live phải là PARTIAL, không được báo đạt đủ. |

## Điểm commit

Commit riêng feature evidence trên feature/evidence-tests; PR vào develop.
Không thêm deploy/, dashboard/wsgi.py hoặc .vscode/ vào commit này. Sau khi
review/merge, bước kế tiếp theo GitFlow là docs/demo-handover; phần UI/UX vẫn
để lại cho lượt quay lại dashboard-layout theo yêu cầu.
