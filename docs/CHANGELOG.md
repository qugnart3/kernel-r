# CHANGELOG — Kernel-R

## 2026-11-16 — H8+H10: Permissions API + Touch consistency

### Sửa
- **permissions.cc**: Override `TaskComplete()` — khi permissions toggle enabled, force `result->status = mojom::blink::PermissionStatus::ASK` → tất cả `navigator.permissions.query()` trả "prompt" thay vì real permission state
- **web_view_impl.cc**: Override `RuntimeEnabledFeatures::SetTouchEventFeatureDetectionEnabled()` — khi screen toggle enabled, set `has_touch = (max_touch_points > 0)` từ profile → `"ontouchstart" in window` khớp với `navigator.maxTouchPoints`
- **test_toggles.html**: Thêm 2 test cards mới: H8 Permissions API, H10 Touch Consistency

### Thiết kế
- H8: Override tại callback level (`TaskComplete`) — mỗi query() trả "prompt" bất kể permission thật. Không cần mock PermissionService, chỉ override result status
- H10: `ontouchstart` property existence controlled bởi `TouchEventFeatureDetection` runtime flag. Override flag trong `ApplyFingerprintSettings()` (web_view_impl.cc) — cùng chỗ maxTouchPoints đã được set bởi H4

### Context
- hCaptcha cross-check: `"ontouchstart" in window` vs `navigator.maxTouchPoints > 0` — nếu không khớp → red flag
- hCaptcha check permissions: nếu trả "granted" cho camera/microphone trên fresh profile → suspicious

## 2026-11-16 — H6-H7: Voices filter + Storage quota noise

### Sửa
- **speech_synthesis.cc**: Filter voices trong `OnSetVoiceList()` — nếu profile có explicit voice list, chỉ giữ voices matching tên. Nếu không, filter theo locale language prefix (e.g., "en" từ "en-US"). Giữ original list nếu filter xoá hết
- **storage_manager.cc**: Apply deterministic noise ±5% lên real quota (thay vì fixed value override)
- **fingerprint_profile.h/.cc**: Thêm `NoisedQuota(int64_t real_quota)` — dùng DeterministicNoise(seed, "storage_quota") để tạo noise factor 0.95-1.05
- **profile_loader.cc**: Thêm parse `storage_quota` từ JSON (giữ lại cho backward compat, nhưng không dùng nữa)
- **test_toggles.html**: Thêm 4 test cards mới: H3 Connection, H4 maxTouchPoints, H6 Voices, H7 Storage Quota Noise

### Thiết kế
- Voices: Filter tại `OnSetVoiceList` (Mojo callback) — chỉ filter 1 lần khi OS voices arrive. Profile voices empty → filter by locale prefix
- Storage quota v1 (REVERTED): Fixed value override — bị hCaptcha detect vì giá trị không khớp disk thật
- Storage quota v2 (CURRENT): Deterministic noise ±5% quanh quota thật. Luôn bật khi profile active. Mỗi profile seed → factor khác nhau → mỗi instance quota khác nhau nhưng realistic

## 2026-11-16 — H3-H4: hCaptcha signal gaps (connection + maxTouchPoints)

### Sửa
- **network_information.cc**: Override `effectiveType()`, `rtt()`, `downlink()`, `saveData()` — return profile connection values khi network toggle enabled. Map effectiveType string ("4g"/"3g"/"2g"/"slow-2g") sang V8EffectiveConnectionType enum
- **navigator_events.cc**: Override `maxTouchPoints()` — return profile `max_touch_points` khi screen toggle enabled

### Thiết kế
- Connection: Early-return pattern trước Chromium logic (holdback, observing, notifier). Profile values cố định — không thay đổi khi mạng thật thay đổi, tránh fingerprint instability
- maxTouchPoints: Đọc từ Settings object (set bởi browser process) → override bằng profile value trong renderer

### Context
- hCaptcha `interrogateNavigator()` dump TẤT CẢ navigator properties qua `for..in` loop — bao gồm `navigator.connection.*` và `navigator.maxTouchPoints`
- Connection values khác giữa các instance có thể dùng để correlate sessions
- maxTouchPoints=10 (mặc định máy này) cần configurable cho profiles giả lập máy không touch

## 2026-11-16 — T15: Anti-config-leak (D21 + D22)

### Thêm
- **chrome/app/chrome_main_delegate.cc** (D21): Khi `--kr-profile` active, append `AimEnabled,AimServerEligibilityEnabled,AimServerRequestOnStartupEnabled,PreconnectToSearch` vào `--disable-features` — tắt Google background connections (Aim eligibility pings, search preconnect) để tránh leak fingerprint qua side-channel
- **chrome/browser/ui/webui/version/version_ui.cc** (D22): Filter tất cả `kr-*` switches khỏi chrome://version Command Line display. Windows: rebuild CommandLine object bỏ kr-prefixed switches. Non-Windows: filter argv entries bắt đầu `--kr-`
- **test_antileak.html**: Test page kiểm tra 5 mặt: toString integrity (17 functions), GOPD descriptor integrity (9 properties), KR string leak scan (6 patterns × 5 objects + chrome.kr + UA), brand check (wrong-this TypeError), chrome://version manual check instructions

### Thiết kế
- D21: Dùng `RemoveSwitch` + `AppendSwitchASCII` để merge với existing `--disable-features` — không ghi đè user flags
- D22: Reconstruct CommandLine thay vì string replace — robust với quoted paths và special characters
- toString/GOPD: KR patches ở C++ level (Blink IDL getters) nên `Function.prototype.toString` tự động trả `[native code]` — không cần thêm code
- KR string scan: Verify không có property nào chứa "kr-profile", "kr_fingerprint", "kernel-r", "KernelR" trong window/navigator/screen/document

### Vấn đề
- Features disabled: `AimEnabled` + `AimServerEligibilityEnabled` + `AimServerRequestOnStartupEnabled` (omnibox AI suggestions, gọi Google servers) + `PreconnectToSearch` (preconnect tới search engine khi mở new tab)
- chrome://version: Chỉ ẩn trên UI — `base::CommandLine::ForCurrentProcess()` vẫn giữ nguyên switches cho internal use

## 2026-11-16 — T14: TLS/H2 fingerprint parity (verification only)

### Xác minh
- **0 file `net/` bị sửa** — `git diff --name-only b8c2be851f | grep ^net/` → empty
- **0 file `boringssl/` bị sửa** — confirmed
- **43 files total** — tất cả trong `components/kr_fingerprint/`, `third_party/blink/renderer/`, `chrome/browser/`, `content/browser/`, `build/config/`
- TLS ClientHello, cipher suites, extensions, curves, ALPN → 100% stock Chromium 158
- HTTP/2 SETTINGS: HEADER_TABLE_SIZE=65536, ENABLE_PUSH=0, INITIAL_WINDOW_SIZE=6291456, MAX_HEADER_LIST_SIZE=262144
- HTTP/2 WINDOW_UPDATE: 15663105
- Chrome 110+ extension shuffle: JA3 hash thay đổi mỗi session (by design), ciphers/curves cố định

### Thêm
- **test_tls.html**: Test page fetch tls.peet.ws/api/all, tự động so sánh ciphers/extensions/curves/H2 vs expected Chrome values
- **HANDOVER.md**: T14 chuyển sang HOÀN THÀNH, thêm lesson learned #8

### Kết luận
- T14 là verification task — không cần code changes vì TLS stack thừa hưởng nguyên từ Chromium 158
- Chỉ cần đảm bảo KHÔNG BAO GIỜ sửa file trong `net/` hoặc `third_party/boringssl/`

## 2026-11-16 — T13: WebRTC IP leak prevention (webrtc)

### Thêm
- **profile_data.h**: Thêm `webrtc` toggle vào `TogglesData` (default true)
- **profile_loader.cc**: Parse `webrtc` toggle từ JSON
- **fingerprint_profile.cc**: Thêm `"webrtc"` vào `IsToggleEnabled()`
- **renderer_preferences_util.cc**: Lớp 1 — override WebRTC IP handling policy thành `kDefaultPublicInterfaceOnly` khi `--kr-profile` active (browser process)
- **rtc_peer_connection.cc**: Lớp 2 — filter ICE candidates chứa private IP (10.x, 192.168.x, 172.16-31.x, 169.254.x, 127.x, fc/fd, fe80:, ::1) khi webrtc toggle enabled (renderer process, belt-and-suspenders)
- **chrome/browser/BUILD.gn**: Thêm dependency `//components/kr_fingerprint`
- **test_profile.json**: Thêm `"webrtc": true`
- **test_webrtc.html**: Test page kiểm tra WebRTC IP leak

### Thiết kế
- Lớp 1 (browser): Chromium tự chặn enumerate local interfaces, chỉ dùng default route → ICE candidates chỉ có public IP
- Lớp 2 (renderer): Drop candidate nếu address là private IP → phòng trường hợp policy bị bypass

## 2026-11-16 — H2: Accept-Language header override (locale_tz)

### Sửa
- **profile_network_context_service.cc**: Override `ComputeAcceptLanguage()` — return profile languages khi locale_tz toggle enabled, thay vì dùng browser pref
- **chrome/browser/net/BUILD.gn**: Thêm dependency `//components/kr_fingerprint`

### Audit kết quả
- locale_tz toggle đã cover: navigator.language, navigator.languages, Intl timezone, Date TZ, Worker TZ
- Accept-Language HTTP header là gap cuối cùng — giờ đã patch
- Vấn đề P0 thực sự: timezone trong profile phải khớp IP geolocation (profile generator job)

## 2026-11-16 — H1: Screen leak fixes (innerWidth/outerWidth/DPR/matchMedia)

### Sửa
- **local_dom_window.cc**: Patch `innerWidth()`, `innerHeight()`, `outerWidth()`, `outerHeight()` — return profile values khi screen toggle enabled
- **local_dom_window.cc**: Patch `devicePixelRatio()` — return profile `dpr` khi screen toggle enabled
- **media_values.cc**: Patch `CalculateDevicePixelRatio()` — return profile `dpr` cho tất cả CSS media queries (matchMedia)

### Thêm
- **local_dom_window.cc**: Include `kr_fingerprint/fingerprint_profile.h`
- **media_values.cc**: Include `kr_fingerprint/fingerprint_profile.h`
- **test_toggles.html**: Thêm card "Window / DPR" kiểm tra innerWidth, outerWidth, outerHeight, innerHeight, devicePixelRatio, matchMedia DPR queries

### Vấn đề đã giải quyết
- hCaptcha phát hiện screen toggle vì `screen.width` = 3840 nhưng `outerWidth` = real value (1920) — inconsistency
- `matchMedia('(resolution: 1.5dppx)')` trả false vì DPR thật = 1.0 — giờ đã patch tại CSS media query level
- `document.documentElement.clientWidth` trả viewport thật — hCaptcha dùng `Math.min(innerWidth, clientWidth)` → giờ đã patch trong element.cc
- Profile 4K (3840x2160) gây flagged do server-side hardware plausibility check — đổi sang 1920x1080 → pass
- **Lesson**: screen values phải gần thực tế, vì CSS layout viewport (getBoundingClientRect, vw/vh units) không thể spoof

## 2026-11-16 — hCaptcha Reverse Engineering: Full Signal Map

### Thêm
- **reverse/HCAPTCHA_SIGNALS.md**: Tài liệu đầy đủ về tất cả fingerprint signals mà hCaptcha thu thập
- **reverse/hcaptcha.html**: Downloaded iframe content (698KB) — chứa VM bytecode interpreter + fingerprint logic
- **reverse/api.js**: Downloaded outer frame script (420KB) — motion data collector + check-api bridge

### Phân tích
- Decoded VM bytecode: 63,533 opcodes, 4,106 decoded strings từ base64-encoded string table (`_eEubans8`)
- VM dùng stack-based interpreter với registers: `_sqgIzP` (IP), `_1SaXxmI` (stack), `_9sogX7` (locals)
- Opcode 22 decode strings: `decodeURIComponent(atob(slice)) + char shift` — ẩn property names
- `interrogateNavigator()`: `for (var i in window.navigator)` — dump TẤT CẢ navigator properties
- `getScreenDimensions()`: `for (var e in window.screen)` — dump TẤT CẢ screen properties
- `dpr()`: Đọc `window.devicePixelRatio` trực tiếp
- `getWindowDimensions()`: `Math.min(innerWidth, clientWidth)`
- `Mt()` hook DOM query methods để collect stack traces → phát hiện automation

### Vấn đề phát hiện (tại sao toggle bị flagged)
- **locale_tz**: Timezone ↔ IP geolocation mismatch (P0)
- **screen**: innerWidth/outerWidth/devicePixelRatio CHƯA PATCH → leak giá trị thật (P0)
- **screen**: matchMedia leak DPR thật (P0)
- **fonts**: Whitelist quá nhỏ (17 fonts, bình thường 150+) (P1)
- **cpu_memory**: Giá trị không khớp GPU tier (P1)
- **T8/T9/T10 safe**: Chỉ thêm noise, không tạo inconsistency

## 2026-11-16 — T12: Context Matrix — timezone consistency fix

### Sửa
- **blink_initializer.cc**: Di chuyển timezone override từ block sớm (trước CoreInitializer) sang SAU `GetBlinkInitializer().Initialize()` — đảm bảo `TimeZoneController::Init()` đã chạy
- **blink_initializer.cc**: Thay `icu::TimeZone::adoptDefault()` bằng `TimeZoneController::SetTimeZoneOverride()` — API đúng, gọi `SetIcuTimeZoneAndNotifyV8()` để thông báo tất cả Worker threads
- **blink_initializer.cc**: Lưu RAII `TimeZoneOverride` handle vào static unique_ptr — override active suốt process lifetime
- **blink_initializer.cc**: Thay include `icu/timezone.h` bằng `timezone_controller.h`

### Vấn đề đã giải quyết
- Worker và iframe trả `Intl.DateTimeFormat().resolvedOptions().timeZone` = `Etc/GMT-7` (timezone thật) thay vì `America/Los_Angeles` (profile). Root cause: `adoptDefault()` chỉ set ICU default mà không notify V8 isolates trong Workers

## 2026-11-15 — T11: Font enumeration whitelist

### Thêm
- **profile_data.h**: Thêm `std::vector<std::string> fonts` vào ProfileData — danh sách font cho phép
- **profile_loader.cc**: Parse mảng `fonts` từ JSON profile
- **fingerprint_profile.h**: Thêm accessor `fonts()` 
- **font_cache.cc**: Hook `IsPlatformFamilyMatchAvailable()` — nếu profile active + toggle "fonts" + font list không rỗng, chỉ return true cho font có trong whitelist (case-insensitive). Font không trong list → return false → `document.fonts.check()` báo không có

### Sửa
- **test_profile.json**: Thêm danh sách 17 font phổ biến Windows (Arial, Verdana, Times New Roman, Segoe UI, Calibri, etc.)

## 2026-11-15 — T10: WebAudio fingerprint noise

### Thêm
- **audio_noise.cc/h** (blink/platform/kr_fingerprint): Hàm `ApplyAudioNoise()` — dùng DeterministicNoise (SipHash) domain "audio" để perturb float samples ±1e-7, skip 0.0f, deterministic theo seed
- **audio_buffer.h**: Thêm `kr_noised_` flag để tránh double-noise
- **audio_buffer.cc**: Hook `getChannelData()` và `copyFromChannel()` — apply noise lần đầu truy cập channel data, noise tất cả channels cùng lúc
- **platform/BUILD.gn**: Thêm audio_noise.cc/h vào sources

## 2026-11-15 — T9: WebGL fingerprint spoofing

### Sửa
- **webgl_rendering_context_base.cc**: Override `getParameter()`:
  - `UNMASKED_VENDOR_WEBGL` → profile gpu.vendor
  - `UNMASKED_RENDERER_WEBGL` → profile gpu.renderer
  - 10 GL_MAX_* params (texture_size, cube_map, texture_image_units, vertex_attribs, vertex_uniform_vectors, fragment_uniform_vectors, renderbuffer_size, varying_vectors, vertex_texture_image_units, combined_texture_image_units) → profile gpu values

## 2026-11-15 — T8: Canvas 2D fingerprint noise

### Thêm
- **canvas_noise.cc/h** (blink/platform/kr_fingerprint): Hàm `ApplyCanvasNoise()` — dùng DeterministicNoise (SipHash) để perturb RGB pixels ±1, skip 0/255, deterministic theo seed+domain "canvas"
- **base_rendering_context_2d.cc**: Hook `getImageDataInternal()` — apply noise sau khi đọc pixels, trước khi return ImageData
- **image_data_buffer.cc**: Hook `EncodeImage()` — apply noise trên copy của pixel buffer trước khi encode (covers toDataURL + toBlob)
- **unsafe_buffers_paths.txt**: Thêm exemption cho `image_data_buffer.cc` và `blink/platform/kr_fingerprint/`

## 2026-11-15 — T7: Timezone/Locale patches

### Sửa
- **blink_initializer.cc**: Sau khi load profile, gọi `TimeZoneController::SetTimeZoneOverride()` với timezone từ profile (e.g. "America/Los_Angeles") — ảnh hưởng `Intl.DateTimeFormat`, `Date.getTimezoneOffset()`, tất cả Date operations
- **navigator_language.cc**: Override `language()` và `languages()` — trả về profile.locale.language/languages khi profile active + toggle "locale_tz"
- **navigator_language.h**: Thêm `kr_languages_` member để cache languages vector

### Thêm
- Include `timezone_controller.h` trong `blink_initializer.cc`
- Include `fingerprint_profile.h` trong `navigator_language.cc`

## 2026-11-15 — Fix: --kr-profile switch propagation to renderer

### Sửa
- **content/browser/renderer_host/render_process_host_impl.cc**: Thêm `kr::switches::kKrProfile` vào `kSwitchNames[]` whitelist trong `PropagateBrowserCommandLineToRenderer()` để switch `--kr-profile` được truyền từ browser process sang renderer process
- **content/browser/renderer_host/render_process_host_impl.cc**: Thêm `#include "components/kr_fingerprint/kr_switches.h"`
- **content/browser/BUILD.gn**: Thêm dep `"//components/kr_fingerprint"`

### Vấn đề
- Root cause: browser process lọc command-line switches trước khi truyền sang renderer. `--kr-profile` không nằm trong whitelist nên bị drop, khiến `blink_initializer.cc` không thấy switch → profile không được load → tất cả fingerprint values đều là giá trị thật

## 2026-11-14 — T6: Navigator/Screen patches

### Sửa
- **navigator_concurrent_hardware.cc**: `hardwareConcurrency()` → profile.navigator.cores
- **navigator_device_memory.cc**: `deviceMemory()` → profile.navigator.device_memory
- **screen.cc**: `width()/height()/availWidth()/availHeight()/colorDepth()` → profile.screen.*

## 2026-11-14 — T5: UA/Client Hints + navigator patches

### Sửa
- **third_party/blink/renderer/core/frame/navigator.cc**: patch `platform()` → đọc từ FingerprintProfile, patch `webdriver()` → return false khi profile active
- **third_party/blink/renderer/core/frame/navigator_ua_data.cc**: patch `platform()` getter cho Client Hints, fix `getHighEntropyValues` dùng getter thay vì raw member

## 2026-11-14 — BUILD.gn + T4 DeterministicNoise

### Thêm
- **components/kr_fingerprint/BUILD.gn**: GN build target cho ProfileLoader, ProfileData, DeterministicNoise
- **components/kr_fingerprint/deterministic_noise.h/.cc**: SipHash-2-4 wrapper (domain-separated) dùng BoringSSL SIPHASH_24, SHA-256 key derivation từ seed+domain
- **third_party/blink/renderer/platform/BUILD.gn**: thêm kr_fingerprint/fingerprint_profile.cc/.h vào component("platform"), thêm dep //components/kr_fingerprint

### Sửa
- Không cần BUILD.gn riêng cho blink/platform/kr_fingerprint — files được add trực tiếp vào platform component

## 2026-11-14 — Xây dựng lại MASTER-PLAN.md

### Sửa
- **GPU**: xác nhận GTX 1070, cập nhật từ "cần kiểm tra" → "GTX 1070 8GB VRAM tier 2"
- **heap_limits**: device_memory=4 sửa từ 4.3GB → 2.2GB (đánh dấu cần đo thật)
- **Taskbar**: bỏ 60px, chỉ giữ 40/48px (Win10/Win11)
- **chrome_h**: sửa từ randint(135,175) → choice([74, 102]) (tab+toolbar / +bookmarkbar)
- **GPU_DB**: đánh rõ PLACEHOLDER, hiện có 0 GPU đo thật, RTX 3060 example → GTX 1070
- **platformVersion**: thêm 13.0.0 (Win11 21H2), 14.0.0 (Win11 22H2), sửa mapping
- **StorageManager quota**: thay randint(5B,50B) → tier dựa trên disk size thật
- **Not-A.Brand**: đánh dấu cần verify cho Chrome 158
- **Entropy**: tính lại — N GPU × 89,100,000 (N=1 → 89M, N=50 → 4.5B)
- **Chromium tag**: nâng từ 157.0.8103.27 → 158.0.8127.37 (stable mới nhất)
- **Consistency rule**: availHeight sửa "30≤diff≤60" → "40 or 48px"
- **Consistency rule**: heapSizeLimit sửa mô tả cho đúng device_memory mapping
- **R1 risk**: cập nhật GPU = GTX 1070

### Thêm
- **Section 11.6**: "Giá trị CẦN ĐO THẬT" — 12 mục M1-M12, workflow đo corpus
- **Phi mục tiêu**: thêm "CÓ né fingerprint detection tầng web" (mục tiêu chính)
- **Mục tiêu mở rộng Phase 3+**: TPM attestation, kernel driver, HWID spoof
- **Automation 2 tầng**: Tầng 1 named pipe (logic), Tầng 2 SendMessage+HWND (input OS level)
- **Canvas 2 chế độ**: native (GPU thật) / spoofed (gamma/contrast)
- **VM layer**: hv_sock truyền profile mã hoá, GPU-P canvas native, build 1 lần trên host
- **Locale**: giới hạn en-US + vi-VN, LOCALE_MAP thay GEO_TZ_MAP
- **Profile schema**: thêm `toggles` 11 nhóm bật/tắt fake, 3 preset
- **Manager UI**: Dashboard + Profile Editor + 3 chế độ (All Native/Spoofed/Custom)
- **CLAUDE.md rule 5**: Changelog — ghi lại mọi thay đổi

### Xóa
- **Phi mục tiêu**: bỏ "Không né anti-cheat/anti-fraud cụ thể" (mâu thuẫn với mục tiêu)
- **Phi mục tiêu**: bỏ "Không giả attestation phần cứng" (chuyển sang Phase 3+)
- **Phi mục tiêu**: bỏ "Không viết driver/sửa kernel OS" (chuyển sang Phase 3+)
- **GEO_TZ_MAP**: bỏ multi-country (GB, DE...), chỉ giữ US + VN

### Thêm (tiếp)
- **Section 8b**: kr-remote gateway — WebSocket server thay CDP, 1 cổng N instance, TLS + token + IP whitelist
- **A13**: SendMessage + HWND task trong roadmap
- **A14-A15**: kr-remote gateway + client SDK tasks trong roadmap
- **CLAUDE.md rule 5**: Changelog bắt buộc
- **CHANGELOG.md**: Tạo file, ghi lại toàn bộ thay đổi hôm nay

## 2026-11-14 — Triển khai cấu trúc & skeleton

### Thêm
- **C:\src\kernel-r\**: tạo cấu trúc thư mục (patches, scripts, tools/kr, corpus/*, harness, ui, vm, docs)
- **C:\src\kernel-r\PINNED_VERSION**: file chứa tag "158.0.8127.37"
- **C:\src\kernel-r\corpus\capture.html**: trang capture fingerprint M1-M12 (GPU, canvas, audio, fonts, memory, storage, UA-CH, voices, plugins, window)
- **C:\src\kernel-r\tools\kr\generator.py**: Python profile generator skeleton — SeededRNG (SHA-256 domain-separated), gen_screen, gen_navigator, gen_gpu, gen_locale, gen_canvas, gen_connection, gen_toggles, generate_profile()

### Sửa
- **Python**: cài Python 3.12.10 via winget
- **shallow.lock**: xoá stale lock file lần 2, kill git processes, retry fetch

### Test
- **generator.py**: chạy OK — random seed sinh profile đúng format, fixed seed deterministic, VN locale → Asia/Ho_Chi_Minh + vi-VN

## 2026-11-14 — Build Chrome 158 thành công

### Thêm
- **Windows SDK 10.0.28000.2957**: cài base + servicing update + Debugging Tools
- **out/KernelR/args.gn**: GN args (release, x64, no LTO, symbol_level=1)
- **chrome.exe**: build thành công từ tag 158.0.8127.37, branch kr/base

### Sửa
- **crypto/user_verifying_key_win.cc**: patch KeyCredentialStatus_AlgorithmNotSupported (SDK thiếu enum)
- **ui/accessibility/platform/uia_client_info_source_win.cc**: thêm `#include <objbase.h>` + `<UIAutomationCore.h>` (SDK servicing mới có IUIAutomationClientInfoSource)
- **args.gn**: bỏ `enable_nacl` (Chrome 158 đã xoá NaCl)

## 2026-11-14 — Capture fingerprint baseline GTX 1070

### Thêm
- **corpus/gpu/gpu_db.json**: entry GTX 1070 — 40+ WebGL params, 33 extensions
- **corpus/baseline_capture.json**: full baseline M1-M12

### Phát hiện từ data thật
- **jsHeapSizeLimit**: 3,760,000,000 (device_memory=32) — cần update heap_limits
- **StorageQuota**: 10GB (disk 476GB)
- **Not.A/Brand**: v24 confirmed cho Chrome 158
- **Voices**: 3 en-US (David, Mark, Zira) — Win10 LTSC default
- **Taskbar**: 40px confirmed
- **platformVersion**: 8.0.0 = Win10 1903
- **maxTouchPoints**: 10 — BẤT NGỜ trên máy không touch!
- **chrome_height**: 95px — plan có 74/102

### Vấn đề pending
- R11: Win10 LTSC 2019 (build 18363) có thể không tương thích Chrome 158 — verify sau checkout
- Voices vi-VN: chưa liệt kê, cần đo trên Windows tiếng Việt
- Fonts vi-VN: chưa kiểm tra font set tiếng Việt trên Windows
- kr-remote gateway: đã thảo luận, chưa thêm vào plan
