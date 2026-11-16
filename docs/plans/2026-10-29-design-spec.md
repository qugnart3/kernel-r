# Kernel-R Design Spec

Ngày: 2026-10-29. Trạng thái: **ĐÃ DUYỆT 2026-10-29**; cập nhật lần cuối 2026-10-30 (xem mục 8: thay đổi so với đặc tả gốc).

## 1. Ý định

Xây một bản Chromium fork trong đó mỗi lần khởi chạy:
1. Sinh một seed ngẫu nhiên (CSPRNG).
2. Từ seed, chọn một "máy" hoàn chỉnh và nhất quán (OS, GPU, RAM, màn hình, font, ngôn ngữ, múi giờ...).
3. Mọi API của engine trả thông tin theo máy đó, ở tầng C++.
4. Phase 2: chạy toàn bộ trong một VM/Sandbox riêng, định danh phần cứng ảo cũng lấy từ cùng seed.

Kết quả mong muốn: hai lần mở bất kỳ cho ra hai "thiết bị" khác nhau, trong khi mỗi thiết bị tự nhất quán
giữa mọi ngữ cảnh (main thread, iframe, Worker, ServiceWorker, OffscreenCanvas).

## 2. Mục tiêu / Phi mục tiêu

Mục tiêu:
- G1. Provider duy nhất (`FingerprintProfile`) là nguồn sự thật cho mọi thông tin máy.
- G2. Tính xác định: cùng seed ⇒ cùng toàn bộ đầu ra (byte-for-byte với canvas/audio).
- G3. Tính nhất quán: mọi profile phát sinh phải qua `Validator` (bộ ràng buộc) trước khi dùng.
- G4. Đa dạng: phân bố profile bám sát phân bố phần cứng thực tế, không đồng đều giả tạo.
- G5. Không có dấu vết tầng JS (không `defineProperty`, không hook bằng script).
- G6. Patch tối thiểu, tách module, rebase được lên bản Chromium mới trong <= 1 ngày.
- G7. Chế độ `ephemeral` (mặc định, seed mới mỗi lần) và `persistent` (seed lưu theo profile).

Phi mục tiêu:
- N1. Không giả attestation phần cứng (TPM, Play Integrity, Private Access Tokens, DBSC).
- N2. Không viết driver / sửa kernel OS.
- N3. Không giả hiệu năng thật (xem rủi ro R1) ngoài việc giới hạn lớp cấu hình theo năng lực máy chủ.
- N4. Không hỗ trợ giả OS khác họ với máy chủ ở Phase 1 (xem D3).
- N5. Không có tính năng né các hệ thống anti-cheat / anti-fraud cụ thể.

## 3. Kiến trúc

```
                        ┌──────────────────────────────┐
  launcher (Python) ───►│ Profile Generator            │
  seed (CSPRNG)         │  corpus/*.json + constraints │
                        └──────────────┬───────────────┘
                                       │ profile.json (đã qua Validator)
                                       ▼
 Browser process  ── components/fingerprint ── nạp, kiểm lại schema, hash
        │                                         │
        │  (switch --kr-profile-b64 / shared mem) │ truyền xuống con
        ▼                                         ▼
 Renderer / GPU / Utility / Worker  ── blink platform: FingerprintProfile::Get()
        │
        ├─ Navigator, Screen, WorkerNavigator          (nhóm A: giá trị)
        ├─ Canvas2D, OffscreenCanvas, WebGL 1/2, WebGPU (nhóm B: render + nhiễu)
        ├─ WebAudio                                     (nhóm B)
        ├─ Font enumeration / measurement               (nhóm C: tài nguyên)
        ├─ Timezone/ICU, Intl locale                    (nhóm A)
        ├─ WebRTC ICE / IP                              (nhóm D: mạng)
        └─ net/: TLS ClientHello, HTTP/2 SETTINGS, header order (nhóm D)
```

### 3.1 Phân tầng mã (tránh vi phạm dependency Chromium)
- `components/kr_fingerprint/` (browser-side): `ProfileLoader`, `ProfileValidator`, switch definitions. Không phụ thuộc Blink.
- `third_party/blink/renderer/platform/kr_fingerprint/`: `FingerprintProfile` (singleton bất biến, thread-safe sau khởi tạo), `DeterministicNoise`.
- Điểm hook trong Blink chỉ gọi `FingerprintProfile::Get().Xxx()` rồi quay về logic gốc nếu profile tắt.
- `tools/kr/` (ngoài cây Chromium, repo riêng `kernel-r/`): generator, corpus, validator Python, harness test.

### 3.2 Truyền profile xuống tiến trình con
Renderer bị sandbox, **không đọc được file**. Lộ trình:
- P1a: browser đọc JSON, nén + base64, truyền bằng switch `--kr-profile-b64` (giới hạn dòng lệnh Windows 32 767 ký tự ⇒ profile nén <= 12 KB).
  Thêm switch vào danh sách `kSwitchNames` của `RenderProcessHostImpl` và `GpuProcessHost`.
- P1b (nếu vượt giới hạn hoặc cần giấu khỏi `chrome://version`): chuyển sang shared-memory region được kế thừa handle, theo mẫu `--field-trial-handle`.
- Worker/ServiceWorker chạy trong renderer process nên dùng chung singleton. SharedWorker/Utility process kiểm tra riêng (task T11).

### 3.3 Nhiễu xác định (DeterministicNoise)
`noise = SipHash-2-4(key = seed, data = domain_tag || context_bytes)`, với `domain_tag` khác nhau cho canvas, webgl, audio, font-metrics.
Nhiễu phải:
- Nhỏ (canvas: tối đa +-1 LSB trên một tập pixel thưa, chọn theo hash vị trí, không đồng đều toàn ảnh).
- Không phụ thuộc thứ tự gọi (stateless theo toạ độ/mẫu).
- Idempotent: gọi `toDataURL` hai lần cho cùng bytes.

## 4. Mô hình dữ liệu

### 4.1 `profile.json` (schema v1, rút gọn)
```json
{
  "schema": 1,
  "seed": "hex32",
  "os": {"family": "windows", "version": "10.0.22631", "build": 22631, "arch": "x86_64", "ua_platform": "Windows", "platform_version": "15.0.0"},
  "browser": {"major": 0, "full": "0.0.0.0", "brands": [["Chromium","0"],["Not.A/Brand","99"]]},
  "cpu": {"cores": 8, "device_memory_gb": 8},
  "screen": {"w": 1920, "h": 1080, "avail_w": 1920, "avail_h": 1040, "dpr": 1.0, "color_depth": 24},
  "gpu": {"vendor": "Intel", "angle_renderer": "...", "unmasked_vendor": "...", "unmasked_renderer": "...",
          "webgl": {"max_texture_size": 16384, "extensions": ["..."], "params": {"...": 0}}, "tier": 2},
  "fonts": {"installed": ["Arial", "..."], "metric_salt": "hex"},
  "locale": {"languages": ["en-US","en"], "timezone": "America/New_York"},
  "net": {"tls_profile": "chrome_win", "h2_settings": {"...": 0}},
  "noise": {"canvas": true, "audio": true, "webgl": true},
  "provenance": {"corpus_ids": ["gpu:..", "fonts:..."], "confidence": "measured|public|synthetic"}
}
```
Các số `major/full` **không hardcode**: lấy từ bản Chromium đã ghim lúc build (`browser.*` do build step ghi vào).

### 4.2 Corpus (dữ liệu nguồn)
Ba bậc độ tin cậy, generator mặc định chỉ dùng `measured` và `public`:
- `measured`: thu từ máy thật qua `kr-capture` (Chrome stock chạy trang thu thập). Nguồn: máy của bạn (RTX 5060 Ti), VM GPU cloud thuê theo giờ (ví dụ nhóm instance có GPU NVIDIA/AMD) để có thêm họ GPU thật mà không phải mua máy.
- `public`: dữ liệu công khai (khảo sát phần cứng Steam, DB thông số GPU, mã nguồn Chromium cho định dạng chuỗi).
- `synthetic`: suy ra bằng quy tắc; chỉ bật bằng cờ `--allow-synthetic`, ghi vào `provenance`.

## 5. Quyết định thiết kế

| ID | Quyết định | Lý do | Đánh đổi |
|----|-----------|-------|----------|
| D1 | Fork Chromium, không viết engine | Dùng toàn bộ web platform thật | Build nặng, rebase định kỳ |
| D2 | Một provider bất biến | Tránh chỗ sót, tránh random lệch nhau | Phải truyền xuống mọi process |
| D3 | Phase 1 chỉ giả trong họ Windows (10/11, nhiều build) | Font/raster/API của OS khác sẽ lộ khi giả chéo họ | Chưa có macOS/Linux; làm ở Phase 2 bằng VM thật |
| D4 | Cấu hình GPU bị chặn theo `tier` <= tier máy chủ | Hiệu năng/độ chính xác render phải khớp thông số | Đa dạng GPU bị giới hạn khi chưa có VM GPU khác |
| D5 | Generator ngoài engine (Python) | Dễ đổi corpus, test độc lập | Hai nơi cùng chứa quy tắc ⇒ Validator C++ kiểm lại bằng cùng test vectors |
| D6 | Mặc định `ephemeral` | Đúng yêu cầu "mỗi lần mở là máy khác" | Mất trạng thái; `persistent` là tuỳ chọn |
| D7 | Hash seed vào `DeterministicNoise` bằng SipHash | Nhanh, có sẵn trong base/ | Không phải mật mã mạnh (không cần) |
| D8 | Patch dưới dạng series (`patches/*.patch`) + script áp dụng | Rebase dễ, review dễ | Cần kỷ luật tách commit |

## 6. Rủi ro và việc chưa rõ

| ID | Rủi ro | Giảm thiểu |
|----|--------|-----------|
| R1 | Hiệu năng thật không khớp thông số khai báo (GPU, timing) | D4; thêm benchmark tự hiệu chuẩn `kr-calibrate` xác định tier máy chủ |
| R2 | Sót ngữ cảnh (Worker, OffscreenCanvas, SW, `about:blank` iframe) | Bảng ma trận ngữ cảnh trong test-strategy, test tự động từng ô |
| R3 | Rò rỉ qua `chrome://version`, `--` switch, crash report, devtools | Task T14 (che switch, tắt reporting) |
| R4 | Chromium đổi API/đường dẫn khi nâng phiên bản | Ghim tag, patch nhỏ, CI rebase hằng tháng |
| R5 | Dữ liệu GPU tự bịa sai ở tham số WebGL | Chỉ dùng `measured`/`public` mặc định (mục 4.2) |
| R6 | Dung lượng ổ C | Xem environment-setup mục 2 |
| R7 | Giấy phép Windows cho VM ở Phase 2 | Xem phase2 mục 1 |
| R8 | TLS: Chromium hiện hoán vị thứ tự extension nên JA3 không ổn định | Chỉ kiểm JA4-kiểu bất biến thứ tự; xem T12. **Verified HSW:** hCaptcha CycleTLS config confirm Chrome 110+ shuffle behavior — ext 0 first, 21 last, 14 middle shuffled |
| R9 | **WASM execution timing vs hardwareConcurrency (verified HSW 2026-11-11):** spoof cores quá thấp → WASM benchmark chạy nhanh hơn khai báo → phát hiện bất nhất quán qua `ws` fingerprint. Formula: `speedFactor = cores>=12?0.7 : cores>=8?0.85 : cores>=6?1.0 : 1.2` | Ràng buộc generator: `cpu.cores >= max(realCores-4, 4)` khi `realCores >= 6`. Phase 2 VM: CPU = profile → tự khớp. Xem `hsw-gaps-plan H9` |
| R10 | **GOPD / brand-check / toString integrity (verified HSW 2026-11-11):** HSW WASM kiểm tra 108+ property descriptors, gọi method với wrong `this` (brand check), kiểm `Function.prototype.toString` native format. C++ hook ở tầng IDL nên SHOULD pass, nhưng cần systematic verification | Harness `check_gopd_integrity.py`, `check_brandcheck.py`, `check_tostring.py`. Xem `hsw-gaps-plan H8/H10/H11` |

Câu hỏi mở cho người duyệt:
1. Ghim bản Chromium nào (stable hiện tại tại thời điểm bắt đầu)?
2. Có chấp nhận D3 (chỉ họ Windows ở Phase 1) không?
3. Có ổ dư >= 300 GB (ổ khác) để build thoải mái không?
4. Nhiễu canvas/audio mặc định bật hay tắt?

## 8. Trạng thái và thay đổi so với đặc tả gốc (cập nhật 2026-10-30)

Nguồn chi tiết: `CHANGELOG.md`. Mục này giữ đặc tả khớp thực tế; sửa ngay khi quyết định đổi (`CLAUDE.md` mục 2).

### 8.1 Trả lời câu hỏi mở (mục 6)
1. Bản Chromium ghim: **157.0.8103.27** (stable Windows ngày 2026-10-29, tag đã xác minh).
2. D3 (chỉ họ Windows ở Phase 1): **đồng ý**.
3. Ổ build: `C:\src` (ổ C, còn ~110–160 GB); không đặt trong OneDrive.
4. Nhiễu canvas/audio mặc định: **bật**.

### 8.2 Quyết định bổ sung / thay đổi

| ID | Quyết định | Lý do | Ghi chú |
|----|-----------|-------|---------|
| D9 | Nhiễu canvas ở không gian 8888 **unpremultiplied**, chọn kênh theo **màu logic** (R/G/B), tính theo toạ độ canvas | Premul làm `toBlob` ≠ `toDataURL`; BGRA ≠ RGBA làm OffscreenCanvas ≠ HTMLCanvas | T8 |
| D10 | Ẩn font bằng cách `FontCache` trả `nullptr` cho họ trong `fonts.hidden` (chỉ tra theo tên) | Giữ font dự phòng theo ký tự (CJK/emoji) | T11; chỉ ẩn được font host có |
| D11 | Corpus mặc định chỉ dùng dữ liệu **đo thật**; GPU khác host cần gói `kr.capture` từ máy thật | Không có dữ liệu WebGL theo GPU công khai tải được; số bịa sẽ lộ | T9b; `docs/collecting-gpu-data.md` |
| D12 | Ngôn ngữ điều khiển bằng cờ `--lang/--accept-lang` (không vá C++); kích thước cửa sổ bằng `--window-size/position` | Chrome đã hỗ trợ; ít patch hơn | T6, T12 |
| D13 | ~~Launcher tắt riêng sandbox dịch vụ mạng~~ **ĐÃ GỠ (2026-10-30)**: nguyên nhân gốc là thư mục chứa `chrome.exe` thiếu quyền AppContainer (S-1-15-2-1/2); sửa bằng `scripts/fix-sandbox-acl.ps1`; mọi sandbox bật đầy đủ | Chrome stock 157 cũng sập ở cùng vị trí; hết sập sau khi cấp quyền | Phải áp lại quyền cho thư mục build mới |
| D14 | Chỉ đổi `platformVersion` trong UA-CH; UA string Windows cố định | UA Windows luôn `Windows NT 10.0; Win64; x64` | T5 |

| D15 | WebRTC: chính sách IP điều khiển bằng `--force-webrtc-ip-handling-policy` (patch cho chrome.exe) + mặc định an toàn `default_public_interface_only` khi bật kr; có proxy → `disable_non_proxied_udp` | Cờ gốc chỉ hoạt động trong content_shell; đo thật xác nhận | T13 |
| D16 | Thiết bị đa phương tiện: profile quy định số mic/loa/camera; cắt danh sách và báo `NotFoundError` khi thiếu | `enumerateDevices` phản ánh phần cứng thật | T13; không tăng được quá số thật |

| D17 | Chạy qua proxy bằng `kr-gateway` cục bộ (SOCKS5 không đăng nhập → upstream HTTP/SOCKS5 có xác thực); profile sinh SAU khi đo IP thoát; fail-closed khi proxy hỏng; loopback không đi qua proxy | Chromium không nhận user/mật khẩu qua cờ; tránh lộ DNS/IP thật | Đã kiểm chứng với proxy HTTP thật; có tường lửa chặn đi thẳng (`scripts/fw-rules.ps1`, đã kiểm chứng) |

| D18 | Pool proxy + Manager: SQLite, mật khẩu mã hoá DPAPI, `profiles.proxy_id` UNIQUE (1 IP ↔ 1 profile), Manager bằng `http.server` + UI tĩnh, không thêm phụ thuộc | Giữ phụ thuộc tối thiểu; bảo mật bí mật | Đã kiểm chứng đầu-cuối (proxy thật) và UI bấm thật |

| D19 | Parity mạng: bản build giống Chrome stock cùng nhánh về ClientHello và HTTP/2; không vá `net/`, `boringssl`, `services/network`. **Verified HSW (2026-11-11):** hCaptcha dùng CycleTLS match Chrome JA3 — ext shuffle [0,...14 exts...,21], ciphers `4865-...`, curves `29-23-24`; H2fp `1:65536;2:0;3:1000;4:6291456;6:262144|15663105|0|m,s,a,p` (chi tiết tại `network-and-manager-plan.md` N5) | Mọi bản vá chỉ chạm tầng Blink/browser, nên dấu vân tay TLS/H2 thừa hưởng nguyên từ Chromium | Đã đo bằng `harness/check_tls.py` (T14) |

| D20 | UA-CH có nhãn `Google Chrome` khi kr bật (patch 0016); thuật toán nhãn dùng chung của Chromium | Đo: Chrome thương hiệu Google luôn có nhãn này, bản Chromium không; là dấu hiệu nhận ra trên mọi trang đọc Client Hints | Khớp Chrome 156 thật theo công thức; không che được Widevine |
| D21 | Tắt tính năng tự gọi Google (`AimEnabled`, `AimServerEligibilityEnabled`, `AimServerRequestOnStartupEnabled`, `PreconnectToSearch`); gộp thành MỘT cờ `--disable-features` | Đo bằng NetLog: Chrome tự gọi `www.google.com` lúc khởi động và gửi ngôn ngữ/quốc gia của profile | Khác Chrome thật ở hành vi mạng nền (chỉ máy chủ Google thấy) |
| D22 | Ẩn cờ `kr-*` khỏi `chrome://version` và net-export (`kr::CommandLineStringForDisplay`) | Tránh lộ cấu hình trên giao diện | Tiến trình khác trên máy vẫn đọc được dòng lệnh của tiến trình con |
| D23 | Profile truyền cho renderer/GPU bằng vùng nhớ chia sẻ chỉ-đọc (`--kr-profile-handle`), tệp tạm xoá sau khi nạp; `kr_fingerprint` thành `component()`; bỏ giới hạn 24 000 ký tự | Dòng lệnh tiến trình con đọc được bởi mọi tiến trình cùng máy (WMI); static lib nhân bản theo DLL ở component build làm kho rỗng | Không chống được đọc bộ nhớ/nhân bản handle cùng người dùng; dòng lệnh browser còn `--kr-enabled`, `--kr-profile=`; DB Manager vẫn lưu profile |
| D24 | Siết DACL tiến trình Chrome (từ chối đọc/ghi bộ nhớ, tạo luồng, sửa DACL); vùng chia sẻ riêng cho từng renderer, huỷ sau khi tạo; GPU không nhận handle | Tiến trình cùng người dùng đọc bộ nhớ hoặc nhân bản handle để lấy profile (đã mô phỏng) | Không chống Administrator/kernel; DUP_HANDLE phải mở; crashpad không dump được |
| D25 | Không proxy thì dùng `out\Dev-direct` (hard link của `Dev`, đường dẫn khác nên không bị luật tường lửa); có proxy thì dùng `Dev` bị khoá | Người dùng cần một bản có mạng gốc mà không phải gỡ luật tường lửa hay build lần hai | Bản không proxy lộ IP thật; phải đồng bộ lại sau mỗi lần build |
| D26 | Mục `features` trong profile (7 nhóm) tắt từng nhóm giả lập; nhóm tắt đi đường gốc | Người dùng muốn bật/tắt từng nhóm trong UI | Tắt nhóm lộ giá trị thật; có thể mâu thuẫn với nhóm còn bật |
| D27 | Nhiễu canvas: bỏ vùng phẳng, đặt bit thấp nhất theo băm (lũy đẳng), `getImageData` đọc viền 1 pixel | Đo: nhiễu +-1 làm khối tô đặc ra 7 màu và vòng toDataURL lệch ~680 điểm; Chrome thật không có | Ranh giới hình hai màu vẫn lệch 1 đơn vị; canvas đơn giản có thể không đổi hash |
| D28 | Sổ nguồn gốc canvas: chỉ nhiễu canvas 2D đã vẽ nội dung khử răng cưa; `putImageData` làm canvas "exact" vĩnh viễn | Đo bằng bộ phát hiện: nhiễu lúc đọc bị 6/8 phép thử bắt (put/get, gradient, hai màu, fillRect) | Vùng chính xác lẫn trong canvas có chữ vẫn có nhiễu ở ranh giới; canvas chỉ có fillRect không đổi hash |
| D29 | [ĐÃ HOÀN TÁC] Canvas: drift dưới pixel tất định (±0.0008 px, miền `kCanvasDrift`, `context_id`=0) áp lên hình học path/cung/đường và vị trí chữ; canvas ≤ 4x4 không nhiễu buffer; bóng mờ đánh dấu khử răng cưa lúc vẽ | Đo `check_canvas_drift`: 1377/160000 giá trị kênh đổi, theo seed, xác định; không dùng `translate` (cộng dồn), không dùng địa chỉ con trỏ (ASLR). Rủi ro: lệch tối đa 6 mức, chưa đo GPU |
| D30 | [ĐÃ HOÀN TÁC] Canvas: nhiễu TẮT mặc định; drift C++ TẮT (`kCanvasDriftEnabled=false`); đa dạng bằng `rendering.{text_gamma,text_contrast}` -> cờ `--text-gamma/--text-contrast` | Đo: nhiễu và drift làm hash không có ở máy thật và lệch hằng số raster (D29 bị thay thế); cờ Skia giữ nguyên hình học (ngưỡng cạnh 0.0039057731628, glyph 0.125/0.375 khớp Chrome thật). Rủi ro: phân bố tham số là giả định |

| D35 | Canvas đa dạng tự nhiên bằng `font_render.gamma/contrast` trong profile → override DirectWrite gamma/enhancedContrast trong Skia `SkTypeface_win_dw.cpp::onFilterRec`. Thay D30 (hoàn tác). Noise canvas/audio/webgl tắt mặc định | **Verified HSW (2026-11-11):** bisect hCaptcha xác nhận post-hoc noise (±1 bit trên ImageData) bị HSW detect qua so sánh nhiều lần đọc cùng canvas. Gamma/contrast đổi hash chữ tự nhiên vì thay đổi rendering pipeline DirectWrite, giống máy thật khác ClearType settings. Không drift, không cờ CLI | Audio/WebGL chưa có pipeline-level variation; phân bố gamma/contrast là giả định |
| D31 | Kịch bản thao tác chạy trong browser process: named pipe riêng cho từng lượt chạy (`--kr-control-pipe`, ẩn như D22), input bằng `RenderWidgetHost::Forward*Event`, DOM bằng JS trong isolated world; không dùng CDP; không sửa Blink | Cổng CDP làm `webdriver=true` và để lại dấu Playwright (NOTES); Mojo/Blink mới thì patch lớn, trái G6 | **ĐÃ LÀM (2026-11-01)**, patch 0030-0032, `docs/automation.md`. Thực tế khác kế hoạch: không có main world (API public chỉ cho trên chrome://); không OOPIF (cần `RenderWidgetHostInputEventRouter`, không public: trả `unsupported_cross_origin_frame`); không `kr run` nạp file; cần 3 cờ chống occluded khi nhiều cửa sổ. Không thay đổi hành vi thời gian của input; chưa so với chuột thật |

### 8.3 Thay đổi schema `profile.v1` so với mục 4.1
- `os` có thêm `id`; `screen` có `phys_w/phys_h`, `device_memory_gb` cho phép 16/32/64 (trần 8 là giả định sai: máy thật đo được 32).
- `gpu.webgl`: `params` (khoá = mã GL enum), `extensions`, `precision`, `v2{params,extensions,precision}`; `gpu.webgpu{vendor,architecture,device,description}`.
- `fonts.hidden` (danh sách font bị giấu).
- `noise`: `canvas/audio/webgl`.
- `font_render`: thêm `gamma` (float 1.0-3.0) và `contrast` (float 0.0-1.0) cho DirectWrite override per-seed (D35).
- `media {audioinput,audiooutput,videoinput}` (T13).

### 8.4 Thay đổi kiến trúc so với mục 3
- Không dùng deflate; truyền profile bằng base64 qua `--kr-profile-b64` (giới hạn 24000 ký tự).
- `FingerprintProfile::Get()` tự nạp lười từ command line (không cần cầu nối content→renderer); khởi tạo ở mọi tiến trình qua danh sách switch của `RenderProcessHostImpl`/`GpuProcessHost` (literal, vì `content/` không phụ thuộc `components/`).
- Validator C++ chỉ kiểm quy tắc nội tại; quy tắc cần corpus (font, locale, platformVersion) chỉ ở Python.
- SipHash-2-4 tự cài (Chromium 157 `base` không có).

### 8.5 Rủi ro đã hiện thực hoá
- R1/R5 (GPU): render pixel và thời gian chạy vẫn là GPU thật; corpus đo thật mới có 1 GPU.
- R6 (ổ C): sát giới hạn; đã giảm bằng giới hạn job và một thư mục `out`.
- Build bị dừng do thiếu RAM 3 lần: `scripts/build.ps1` dùng `-local_jobs 2`; đặt `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1`.
- Mới: dịch vụ mạng sập trong sandbox (D13): đã tìm ra nguyên nhân (thiếu quyền AppContainer trên thư mục chứa chrome.exe) và sửa.

- 2026-11-01 (D31): `Screen::isExtended()` được hook (patch 0027) trả `false` khi nhóm `kScreen` bật; trước đó bị bỏ sót nên lộ số màn hình thật. `getScreenDetails()` chưa xét.
- 2026-11-01 (D32): `getScreenDetails()` chỉ trả màn hình hiện tại, nhãn/DPR/isPrimary theo profile (patch 0028). `isInternal`, HDR, primaries màu còn là của máy thật.
- 2026-11-01 (D33): proxy được ghi cứng trong trình duyệt (`net.proxy_server` của profile → `ProxyConfigMonitor`, patch 0029) thay cho cờ `--proxy-server`; extension/chính sách/PAC không ghi đè được. Gateway cục bộ vẫn là đường ra duy nhất.
- 2026-11-01 (D34): HOÀN TÁC D33 theo yêu cầu người dùng: proxy lại truyền bằng cờ `--proxy-server` tới gateway cục bộ; patch 0036 (revert của 0029). Vẫn giữ việc từ chối extension có quyền `proxy`. D33 giữ lại ở trên làm lịch sử.
- 2026-11-03 (D35): Canvas đa dạng bằng gamma/contrast qua profile (thay D30 bị hoàn tác). Bisect hCaptcha xác nhận: post-hoc noise (canvas/audio/webgl) bị detect, tắt noise → pass. `font_render.gamma/contrast` override DirectWrite rendering params trong Skia (`SkTypeface_win_dw.cpp`), mỗi seed hash canvas khác tự nhiên. Pipeline: profile JSON → browser parse gamma/contrast → `--kr-text-gamma/--kr-text-contrast` switches → propagated to GPU + renderer → GPU gọi `SkKrSetFontGammaContrast()` trong `GpuMain()`. Cần command-line switches vì canvas GPU rasterize text ở GPU process (không có Blink, không đọc profile từ shared memory). Đã xác nhận 5/5 seeds → 5 distinct hashes trên chrome.exe thật. Audio/WebGL noise vẫn tắt; chưa có pipeline-level audio variation.
