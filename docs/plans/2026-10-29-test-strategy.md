# Kernel-R Test Strategy

Spec: `2026-10-29-design-spec.md`. Plan: `2026-10-29-phase1-implementation-plan.md`.

## 1. Nguyên tắc
- Test trước, thấy FAIL, rồi mới viết code (TDD) cho mọi task.
- Mỗi tầng kiểm một loại lỗi, không chồng chéo.
- Tiêu chí chính là **tính nhất quán và tính xác định**, không phải "qua được trang X".
- Tự đánh giá bằng các thư viện fingerprinting mã nguồn mở và công cụ phòng thí nghiệm nội bộ để *đo độ nhất quán của chính mình*; không nhắm vào hệ thống phát hiện cụ thể của bên thứ ba.

## 2. Kim tự tháp test

| Tầng | Công cụ | Phạm vi | Chạy khi |
|------|---------|---------|----------|
| L1 Unit (Python) | pytest | schema, ràng buộc, generator, phân bố | mỗi commit |
| L2 Unit (C++) | gtest: `kr_fingerprint_unittests`, `blink_unittests`, `unit_tests` | loader, validator, noise, hook từng hàm | mỗi task |
| L3 Web tests | Blink `web_tests` (virtual suite `kr/`) | hành vi JS API trong renderer | mỗi task |
| L4 Browser tests | `browser_tests` | khởi động, switch, từ chối profile hỏng | T1, T2, T15 |
| L5 Harness (Playwright) | Python | ma trận ngữ cảnh, ổn định, đa dạng, nhất quán, hiệu năng | nightly + trước release |
| L6 Net | server TLS/H2 cục bộ | ClientHello (JA3: extension 0 first, 21 last, 14 middle extensions shuffled — verified từ HSW CycleTLS config), SETTINGS (`1:65536;2:0;3:1000;4:6291456;6:262144` — verified), WINDOW_UPDATE (`15663105` — verified), PRIORITY `m,s,a,p` — verified), header order | T14 |
| L7 Regression | stock Chromium so sánh | khi profile tắt, hành vi = stock | mỗi task |

## 3. Tính chất cần chứng minh (property)

| Mã | Tính chất | Cách kiểm |
|----|-----------|-----------|
| P1 | Xác định: cùng seed ⇒ cùng "fingerprint bundle" | Chạy 50 lần/seed, so hash |
| P2 | Đa dạng: khác seed ⇒ khác bundle | 1000 seed, tỉ lệ va chạm hash toàn bundle = 0; entropy từng thành phần >= ngưỡng |
| P3 | Nhất quán nội bộ: bundle qua `Validator` | 100% trên 10 000 seed |
| P4 | Nhất quán ngữ cảnh | Ma trận mục 4 xanh hoàn toàn |
| P5 | Ổn định trong phiên | Gọi API 1000 lần/phiên ⇒ không đổi |
| P6 | Không dấu vết JS | So snapshot descriptor/`toString`/prototype với stock. Chi tiết: (a) GOPD descriptor type (data vs accessor) khớp stock cho MỌI property bị hook — verified qua HSW WASM 108+ GOPD checks, xem `hsw-gaps-plan H8`; (b) `Function.prototype.toString` trả native format cho mọi API function bị hook — xem H10; (c) brand check: gọi DOM method với wrong `this` → throw đúng TypeError — xem H11 |
| P7 | Pass-through | Tắt `--kr-enabled` ⇒ bundle = stock cùng phiên bản |
| P8 | Không hồi quy hiển thị | Ảnh chụp trang chuẩn giữa stock và kr: diff pixel = 0 |
| P9 | Không khai vượt năng lực | Giá trị khai <= khả năng thật (WebGL caps). Bổ sung: `hardwareConcurrency` không chênh quá 4 core so với thật để WASM execution timing tương quan — verified qua HSW `ws` fingerprint formula, xem `hsw-gaps-plan H9` |
| P10 | Không rò rỉ thông tin thật | Quét IP LAN, tên máy, GPU thật, timezone thật trong mọi đầu ra |

## 4. Ma trận ngữ cảnh (T12)

Hàng = ngữ cảnh. Cột = nhóm API. Mỗi ô là một test tự động.

| Ngữ cảnh | navigator | screen/dpr | UA+CH | tz/Intl | canvas | WebGL | audio | fonts | WebRTC |
|---|---|---|---|---|---|---|---|---|---|
| main frame | x | x | x | x | x | x | x | x | x |
| iframe same-origin | x | x | x | x | x | x | x | x | – |
| iframe cross-origin | x | x | x | x | x | x | x | x | – |
| iframe sandbox | x | x | x | x | x | x | x | x | – |
| about:blank / srcdoc | x | x | x | x | x | x | x | x | – |
| popup (window.open) | x | x | x | x | x | x | x | x | – |
| DedicatedWorker | x | – | x | x | OffscreenCanvas | x | – | – | – |
| SharedWorker | x | – | x | x | – | – | – | – | – |
| ServiceWorker | x | – | x | x | – | – | – | – | – |
| Worklet (Audio/Paint) | – | – | – | – | – | – | x | – | – |
| Header HTTP thực | – | – | x | – | – | – | – | – | – |

Điều kiện đạt: trường chung giữa mọi ngữ cảnh **bằng nhau tuyệt đối**.

## 5. Harness (L5) cấu trúc

```
kernel-r/harness/
  pages/collect.html        # thu mọi tín hiệu, trả JSON
  pages/worker_collect.js    # cùng logic trong worker
  runner.py                  # khởi chạy N phiên (kr run), Playwright connect CDP
  tests/test_determinism.py  # P1, P5
  tests/test_diversity.py    # P2 + thống kê entropy
  tests/test_coherence.py    # P3, P9
  tests/test_contexts.py     # P4
  tests/test_native_look.py  # P6
  tests/test_passthrough.py  # P7
  tests/test_visual.py       # P8
  tests/test_leaks.py        # P10
  tests/test_perf.py         # chi phí hook: <= 2% trên Speedometer/JetStream so với stock
```

Cách chạy: `pytest harness -x -q --kr-binary C:\src\chromium\src\out\Dev\chrome.exe`.

## 6. Dữ liệu và công cụ tham chiếu
- Thư viện fingerprint mã nguồn mở (ví dụ FingerprintJS bản OSS) chạy trong harness để xem tín hiệu nào lệch giữa các ngữ cảnh.
- Trang công khai chỉ dùng để quan sát độ nhất quán của chính mình (lab thủ công), không đưa vào CI.
- Baseline stock: `baseline/` từ T0; so sánh từng trường.

## 7. Cổng chất lượng (gate)

| Gate | Điều kiện |
|---|---|
| Per-task | L1-L3 liên quan xanh, L7 pass-through xanh, patch xuất được |
| Phase 1 done | P1-P10 xanh trên 1000 seed; perf hook <= 2%; nightly xanh 7 ngày liên tiếp; rebase thử lên bản stable kế tiếp <= 1 ngày |
| Release nội bộ | Quét rò rỉ P10 sạch; `Out\Rel` build; checksum + ghi `PINNED_VERSION` |

## 8. Báo cáo
Mỗi lần nightly xuất `reports/YYYY-MM-DD.html`: bảng P1-P10, ma trận ngữ cảnh, top 10 trường lệch, chênh lệch hiệu năng. Lỗi mới ⇒ tạo mục trong `NOTES.md` với seed tái hiện.
