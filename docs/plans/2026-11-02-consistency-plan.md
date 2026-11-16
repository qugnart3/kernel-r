# Kế hoạch giai đoạn 3: "1 Browser = 1 PC" nhất quán và đo được (T20–T29)

Trạng thái: KẾ HOẠCH, chưa làm. Ngày 2026-11-02.

## Mục tiêu và phạm vi
Mỗi lần chạy là một "PC + trình duyệt" khác nhau nhưng tự nhất quán và giống một máy thật cùng bản Chromium. Phục vụ QA, nghiên cứu, nhiều tài khoản hợp lệ.
Ngoài phạm vi (giữ nguyên từ đầu): né chống gian lận/chống bot/anti-cheat, giấu proxy hay hypervisor khỏi trang kiểm tra. Mọi task dưới đây đo tính nhất quán
và đúng với máy thật, KHÔNG đo "trang X có chấp nhận hay không".

## Nguyên tắc
1. Không đo được thì không sửa: mỗi task có tiêu chí đạt bằng số.
2. Ít trường giả hơn là tốt hơn: mỗi trường ghi đè là một chỗ có thể lệch với phần còn lại. Chỉ đổi những gì có lý do.
3. Giá trị nào là đo thật, giá trị nào là giả định phải ghi trong dữ liệu (provenance), không để lẫn.
4. Những thứ ngoài tầm trình duyệt (IP, độ trễ, dấu vân tay TCP/TLS của proxy) chỉ ghi nhận, không hứa.

## Danh sách task
| Task | Nội dung | Tiêu chí đạt | Phụ thuộc |
|---|---|---|---|
| T20 Định nghĩa "ổn" | `docs/consistency-criteria.md`: danh sách API, trường nào cố ý đổi, trường nào phải bằng Chrome thật, trường nào ngoài tầm | Mỗi trường có một trong 3 nhãn; người dùng duyệt | Không |
| T21 Đối chứng với bản gốc | `harness/diff_vs_stock.py`: chạy bản không hook (đủ nhóm tắt, hoặc build không patch) và bản kr, so từng API | Mọi khác biệt nằm trong danh sách "cố ý đổi" của T20; 0 khác biệt ngoài danh sách | T20; cần bản đối chứng |
| T22 Luật nhất quán chéo | Gom các kiểm tra rải rác thành một bảng luật (UA/UA-CH/platform, GPU/WebGL, font/OS, màn hình/DPR/cửa sổ, tz/ngôn ngữ/IP, **hardwareConcurrency vs WASM timing — verified H9**) chạy trên profile sinh ra VÀ trên trình duyệt đang chạy. Bổ sung luật từ HSW analysis: `cpu.cores >= max(realCores-4, 4)` (H9); `outerWidth <= screen.width` (H7); GOPD descriptor type khớp stock (H8) | 0 vi phạm trên 500 seed và trên 20 phiên thật | T20; `hsw-gaps-plan H7-H9` |
| T23 Bề mặt API | Thứ tự thuộc tính, `toString` native (H10), tên getter, chuỗi prototype, stack lỗi, **brand check — gọi method với wrong `this` phải throw TypeError (H11)** | `check_surface.py` mở rộng, so với bản đối chứng T21. Bao gồm `check_tostring.py` và `check_brandcheck.py` từ `hsw-gaps-plan` | T21 |
| T24 Ngữ cảnh | iframe, Worker, SharedWorker, ServiceWorker, OffscreenCanvas cho ra cùng giá trị với trang chính | `check_contexts.py` mở rộng, 0 khác biệt | T22 |
| T25 Nguồn gốc dữ liệu | Corpus ghi `measured`/`assumed` theo từng trường; chế độ mặc định chỉ dùng `measured`; thêm quy trình import máy thật khác | Không có trường `assumed` trong chế độ mặc định, hoặc có thì in cảnh báo | Cần máy khác để đo |
| T26 Mạng khớp hồ sơ | Ngôn ngữ, múi giờ, `Accept-Language` theo IP thoát (đã có `align_to_egress`); kiểm đa múi giờ; DNS qua proxy | Kiểm thử với ≥2 proxy khác quốc gia | Cần ≥2 proxy |
| T27 Ổn định theo thời gian | Cùng seed ra cùng cấu hình qua các bản phát hành; khóa cấu hình đã sinh trong DB | Test hồi quy: seed cũ => cấu hình byte-giống | Không |
| T28 Cổng hồi quy | `scripts/qa.ps1` chạy pytest, gtest, toàn bộ harness, xuất báo cáo JSON; chạy sau mỗi build | Một lệnh, một kết quả đạt/lỗi | T21–T24 |
| T29 Lớp VM | Làm tiếp `2026-10-29-phase2-vm-layer-plan.md`: mỗi profile một VM cho phần thuộc hệ điều hành (font cài, GPU ảo, mạng/TUN) | Theo kế hoạch VM | Quyền admin, proxy UDP |

## Thứ tự đề xuất
T20 → T21 → T22 → T28 (khung đo) → T23/T24 (sửa lỗi tìm được) → T27 → T25/T26 (cần dữ liệu/proxy khác) → T29.

## Giới hạn đã biết
- Chỉ có MỘT máy đo thật (OS 26200, RTX 5060 Ti): mọi cấu hình khác là giả định cho đến khi đo thật (T25).
- Bản đối chứng "không hook" cùng phiên bản chưa có; cách rẻ nhất là tắt toàn bộ nhóm bằng `features`, cách đúng nhất là build không patch (tốn thời gian).
- Hiệu năng và thời gian (timing) của máy thật không bắt chước được.
- **WASM execution timing tương quan CPU core (verified HSW H9):** spoof `hardwareConcurrency` quá thấp so với máy thật sẽ bị phát hiện qua WASM microbenchmark timing. Ràng buộc: không spoof xuống < `realCores - 4` khi `realCores >= 6`. Phase 2 VM giải quyết triệt để (VM CPU = profile CPU).
