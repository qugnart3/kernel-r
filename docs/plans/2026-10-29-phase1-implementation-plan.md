# Kernel-R Phase 1 Implementation Plan (Chromium C++ core)

> **For agentic workers:** dùng superpowers:subagent-driven-development (mỗi task một subagent + reviewer) hoặc superpowers:executing-plans. Tick `- [ ]` khi xong.

**Goal:** Chromium fork mà mỗi lần mở sinh một "máy" ngẫu nhiên, nhất quán, xác định theo seed, ở mọi ngữ cảnh.

**Architecture:** Generator (Python) -> `profile.json` -> browser process nạp/kiểm -> truyền xuống tiến trình con -> singleton `FingerprintProfile` trong Blink -> các điểm hook gọi singleton. Nhiễu xác định bằng SipHash theo seed.

**Tech Stack:** Chromium (tag ghim), C++20, GN/Ninja, gtest/blink_unittests/web_tests, Python 3.12 (pydantic, jsonschema, pytest), Playwright (harness).

**Spec:** `docs/plans/2026-10-29-design-spec.md`

**Global Constraints (từ spec):**
- G2 cùng seed ⇒ cùng đầu ra; G3 mọi profile qua Validator; G5 không dấu vết JS; G6 patch nhỏ, tách module.
- Phase 1 chỉ giả trong họ Windows (D3); GPU tier <= tier máy chủ (D4).
- Không có nhiễu/giá trị ngẫu nhiên ngoài `DeterministicNoise` và `FingerprintProfile`.
- Đường dẫn dưới đây là điểm bắt đầu tìm tại tag ghim; **xác minh bằng `git grep` trước khi sửa**, ghi lệch vào `NOTES.md`.

**Review Focus (5 ca dễ sót nhất, mỗi ca có test sở hữu):**
1. Worker / SharedWorker / ServiceWorker trả thông số khác main thread -> T3, T6, T12 (`ContextMatrix.*`).
2. `toDataURL`/`getImageData` không ổn định giữa hai lần gọi -> T8 (`CanvasNoise.Idempotent`).
3. UA, Client Hints và `navigator.platform` mâu thuẫn -> T5 (`UaConsistency.*`).
4. Profile quá lớn vượt giới hạn dòng lệnh -> T1 (`ProfileLoader.RejectsOversize`).
5. Hook làm hỏng hành vi khi profile tắt (regression cho Chromium thường) -> T3 (`Disabled.PassThrough`).

---

## Trạng thái (cập nhật 2026-10-30; chi tiết ở `CHANGELOG.md`)

| Task | Trạng thái | Ghi chú khác kế hoạch |
|---|---|---|
| T0 Baseline build | Xong | SDK 28000, siso, không chạy lại `gclient sync` |
| T16 Generator/corpus/capture | Xong (corpus mới 1 GPU đo thật) | Capture mở rộng (WebGL2/WebGPU/font 95 tên); thêm importer |
| T1 Switch + loader | Xong | Không nén, base64 |
| T2 Validator C++ | Xong (một phần) | Chỉ quy tắc nội tại |
| T3 FingerprintProfile | Xong | Nạp lười từ command line |
| T4 DeterministicNoise | Xong | SipHash tự cài |
| T5 UA/Client Hints | Xong | Chỉ `platformVersion` |
| T6 Navigator/Screen | Xong (+ isExtended 0027, getScreenDetails 0028, 2026-11-01) | Ngôn ngữ bằng cờ |
| T7 Timezone/Locale | Xong | |
| T8 Canvas | Xong; đã KHÔI PHỤC về trước drift/gamma (nhiễu bật mặc định, xem CHANGELOG 2026-10-31) | Không gian nhiễu unpremul |
| T9 WebGL/WebGPU | Xong cơ bản (T9b) | Cần dữ liệu GPU từ máy khác |
| T10 Audio | Xong | AnalyserNode thời gian thực chưa kiểm trên trình duyệt |
| T11 Fonts | Xong | Không làm `metric_salt` |
| T12 Ma trận ngữ cảnh | Xong | Harness `check_contexts.py`; không cần patch C++ |
| T13 WebRTC | Xong | Cờ chính sách IP phải vá cho chrome.exe (patch 0014); thiết bị cắt theo profile (patch 0015); chưa thử với proxy thật |
| T14 TLS/H2 ngang bằng stock | Xong | Giống hệt Chrome stock 157 (ClientHello + H2); 0 tệp `net/` bị chạm; harness `check_tls.py` |
| T15 Chống rò rỉ cấu hình | Xong (có giới hạn) | Phần JS đã sạch sẵn; sửa nhãn UA-CH và kết nối tự phát tới Google (đo bằng NetLog). Còn: Widevine. Dòng lệnh tiến trình con đã hết mang cấu hình (T15b, vùng nhớ chia sẻ, patch 0017; D23); siết quyền tiến trình chống đọc bộ nhớ cùng người dùng (T15c, patch 0018; D24) |
| T17 Launcher tích hợp | Xong (Phase 1) | `main.py --proxy`, `kr.manager` (pool 1 IP ↔ 1 profile, UI), tường lửa; còn: A/B tường lửa, IPv6, chạy trong VM (Phase 2) |

## Thứ tự thực hiện

`T0 → T16(generator) → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12 → T13 → T14 → T15 → T17(tích hợp)`

---

### Task T0: Baseline build và baseline test

**Files:**
- Create: `kernel-r/NOTES.md`, `kernel-r/baseline/` (kết quả)

**Interfaces:** Produces: `out\Dev\chrome.exe` sạch, danh sách test baseline (pass/fail trước khi patch).

- [ ] Làm xong `environment-setup.md` mục 7 (Definition of Ready).
- [ ] Chạy `autoninja -C out\Dev chrome blink_unittests unit_tests`. Kỳ vọng: build thành công.
- [ ] Chạy `out\Dev\blink_unittests.exe --gtest_filter=*Navigator*:*Canvas*` lưu kết quả vào `baseline/`. Kỳ vọng: ghi lại số pass/fail.
- [ ] Chụp 1 file kết quả thu thập fingerprint của Chrome sạch (xem T16 `kr-capture`) làm mốc đối chiếu.
- [ ] Commit: `kr: baseline: record pinned version and test results`.

---

### Task T16: Generator, corpus, capture, validator (Python)

**Files:**
- Create: `kernel-r/tools/kr/{__init__,schema,constraints,generator,capture,calibrate,cli}.py`
- Create: `kernel-r/corpus/{os,gpu,fonts,screens,locales}/*.json`, `kernel-r/tools/kr/schema/profile.v1.json`
- Test: `kernel-r/tools/kr/tests/test_{schema,constraints,generator,determinism,distribution}.py`

**Interfaces:**
- Produces: `generate(seed: bytes, *, host_tier: int, allow_synthetic: bool=False) -> dict` (profile v1)
- Produces: `validate(profile: dict) -> list[Violation]` (rỗng = hợp lệ)
- Produces: CLI `kr gen --seed <hex|random> --out profile.json`, `kr capture --out device.json`, `kr calibrate`.
- Consumes: không (task đầu).

**Steps:**
- [ ] Test `test_schema.py::test_example_validates` + `test_rejects_missing_field`: JSON Schema draft 2020-12 từ spec 4.1. Chạy: `pytest -k schema` ⇒ FAIL (chưa có schema). Viết `profile.v1.json`. Chạy lại ⇒ PASS.
- [ ] Test `test_constraints.py`, mỗi quy tắc một test (viết trước, thấy FAIL):
  - `ua_platform` khớp `os.family`; `platform_version` khớp `os.build`.
  - `angle_renderer` có định dạng ANGLE Direct3D11 đúng cho vendor.
  - `unmasked_*` khớp `gpu.vendor`.
  - `avail_h <= h`, `dpr` thuộc tập hợp hợp lệ của độ phân giải đó.
  - `device_memory_gb` thuộc {0.25,0.5,1,2,4,8}; `cores` thuộc tập thật; `device_memory <= ram`.
  - Font `installed` là siêu tập của bộ font mặc định của đúng build Windows đó.
  - `timezone` hợp lệ IANA, `languages[0]` thuộc locale hợp lệ.
  - `gpu.tier <= host_tier` (D4).
- [ ] Viết `constraints.py` cho đến khi toàn bộ PASS.
- [ ] Test `test_generator.py::test_always_valid_1000_seeds`: 1000 seed ⇒ `validate()` rỗng.
- [ ] Test `test_determinism.py::test_same_seed_same_profile`; `test_diff_seed_diff_profile`.
- [ ] Test `test_distribution.py`: trên 10 000 seed, tần suất GPU/độ phân giải/RAM nằm trong sai số 10% so với trọng số corpus (G4).
- [ ] Viết `generator.py`: chọn OS build theo trọng số → chọn GPU từ corpus còn hợp lệ với OS và `host_tier` → chọn màn hình, RAM, cores tương thích → chọn font set theo OS → chọn locale/timezone (độc lập hoặc theo proxy nếu có) → gán `metric_salt`.
- [ ] `capture.py`: trang HTML thu `navigator`, `screen`, WebGL (mọi `getParameter`, extensions, precision), canvas/audio hash, danh sách font thử, `Intl`, timezone; chạy bằng Playwright trên Chrome stock; ghi `corpus/*` với `confidence: measured`.
- [ ] Thu thập thật: máy hiện tại (RTX 5060 Ti) là bản ghi `measured` đầu tiên; thuê VM GPU theo giờ để bổ sung thêm họ GPU (xoá VM sau khi lấy dữ liệu).
- [ ] `calibrate.py`: benchmark WebGL/Canvas ngắn ⇒ xếp `host_tier` (1..5); ghi cache.
- [ ] Commit: `kr: tools: generator, validator, capture`.

---

### Task T1: Switch và ProfileLoader phía browser

**Files:**
- Create: `components/kr_fingerprint/{BUILD.gn,kr_switches.h,kr_switches.cc,profile_loader.h,profile_loader.cc}`
- Modify: `content/browser/renderer_host/render_process_host_impl.cc` (mảng `kSwitchNames`), `content/browser/gpu/gpu_process_host.cc` (`kSwitchNames`), `chrome/browser/chrome_content_browser_client.cc` (`AppendExtraCommandLineSwitches`)
- Test: `components/kr_fingerprint/profile_loader_unittest.cc`

**Interfaces:**
- Produces: `namespace kr { constexpr char kProfileB64[] = "kr-profile-b64"; constexpr char kEnabled[] = "kr-enabled"; }`
- Produces: `std::optional<ProfileBlob> LoadProfileFromCommandLine(const base::CommandLine&)`; `struct ProfileBlob { std::string json; std::array<uint8_t,32> sha256; }`
- Produces: `std::string EncodeForChildren(const ProfileBlob&)` (deflate + base64).

**Steps:**
- [ ] Test `ProfileLoader.RoundTrip`: encode → decode ⇒ cùng JSON, cùng SHA-256.
- [ ] Test `ProfileLoader.RejectsOversize`: blob nén > 12 KB ⇒ `nullopt` + log lỗi (Review Focus 4).
- [ ] Test `ProfileLoader.RejectsMalformedJson`, `RejectsWrongSchemaVersion`.
- [ ] Chạy: `autoninja -C out\Dev kr_fingerprint_unittests` ⇒ FAIL (chưa có target). Viết code ⇒ PASS.
- [ ] Browser đọc file từ `--kr-profile=<path>` (chỉ browser process), mã hoá và đặt `--kr-profile-b64` cho con. Thêm hai switch vào `kSwitchNames` renderer + GPU.
- [ ] Nếu không có `--kr-enabled`: toàn bộ module trả "tắt" (pass-through).
- [ ] Commit: `kr: switches: add profile switches and loader`.

---

### Task T2: Validator C++ khớp test vector với Python

**Files:**
- Create: `components/kr_fingerprint/profile_validator.{h,cc}`, `components/kr_fingerprint/test_data/vectors/*.json` (sinh từ Python)
- Test: `profile_validator_unittest.cc`

**Interfaces:** Produces: `std::vector<std::string> ValidateProfile(const base::Value::Dict&)`; Consumes: JSON schema/vectors từ T16.

**Steps:**
- [ ] Python xuất `vectors/valid_*.json` (200 file) và `invalid_*.json` (có nhãn quy tắc bị vi phạm) bằng `kr export-vectors`.
- [ ] Test `ProfileValidator.AllValidVectorsPass`, `ProfileValidator.AllInvalidVectorsFailWithExpectedRule` ⇒ FAIL; viết validator ⇒ PASS.
- [ ] Browser từ chối khởi động (thoát mã 78) khi profile không hợp lệ; test `ProfileValidator.BrowserRefusesInvalid` (browser_test).
- [ ] Commit: `kr: validator: cpp validator with shared vectors`.

---

### Task T3: Singleton `FingerprintProfile` trong Blink

**Files:**
- Create: `third_party/blink/renderer/platform/kr_fingerprint/{BUILD.gn,fingerprint_profile.h,fingerprint_profile.cc}`
- Modify: `content/renderer/render_thread_impl.cc` (khởi tạo sớm), `third_party/blink/public/platform/` (cầu nối public nếu cần), `content/gpu/gpu_main.cc` (khởi tạo ở GPU process)
- Test: `.../fingerprint_profile_test.cc`

**Interfaces:**
- Produces: `class FingerprintProfile { static const FingerprintProfile& Get(); bool Enabled() const; const Os& os() const; const Cpu& cpu() const; const Screen& screen() const; const Gpu& gpu() const; const Fonts& fonts() const; const Locale& locale() const; uint64_t Seed() const; }`
- Produces: `static void InitFromJson(const std::string&)` (gọi một lần, trước khi thread phụ khởi chạy).

**Steps:**
- [ ] Test `FingerprintProfile.ParsesAllSections`, `FingerprintProfile.ThreadSafeReadAfterInit` (TSAN-style nhiều thread đọc).
- [ ] Test `Disabled.PassThrough`: không có `--kr-enabled` ⇒ `Enabled()==false` và các hook ở task sau trả giá trị gốc (Review Focus 5).
- [ ] Viết singleton bất biến; truy cập trước `InitFromJson` ⇒ CHECK fail trong dcheck, `Enabled()==false` trong release.
- [ ] Khởi tạo ở renderer và GPU process sớm nhất có thể (trước khi Blink khởi tạo frame/worker).
- [ ] Commit: `kr: blink: FingerprintProfile singleton`.

---

### Task T4: DeterministicNoise

**Files:**
- Create: `.../kr_fingerprint/deterministic_noise.{h,cc}`
- Test: `deterministic_noise_test.cc`

**Interfaces:** Produces: `uint64_t NoiseU64(Domain d, uint64_t a, uint64_t b=0)`; `float NoiseUnit(Domain d, uint64_t a, uint64_t b=0)` trong [-1,1]; `enum class Domain { kCanvas, kWebGL, kAudio, kFontMetrics }`. Dùng `base::SipHash24`.

**Steps:**
- [ ] Test `Noise.Deterministic`, `Noise.DomainSeparation` (khác domain ⇒ khác giá trị), `Noise.UniformEnough` (chi-square 10^6 mẫu), `Noise.OrderIndependent`.
- [ ] Viết ⇒ PASS. Commit: `kr: blink: deterministic noise`.

---

### Task T5: User-Agent và Client Hints

**Files:**
- Modify: `components/embedder_support/user_agent_utils.cc` (`GetUserAgentMetadata`, `GetUserAgent`/`BuildUserAgentFromProduct`), `components/version_info/` nếu cần
- Test: `components/embedder_support/user_agent_utils_unittest.cc`; web test `kr/ua-consistency.html`

**Interfaces:** Consumes `FingerprintProfile::os()/browser`; Produces: UA string, `sec-ch-ua*` headers, `navigator.userAgentData` (low + high entropy) đều từ cùng nguồn.

**Steps:**
- [ ] Test `UaConsistency.UaStringMatchesPlatform`, `UaConsistency.ClientHintsMatchUa`, `UaConsistency.HighEntropyValuesMatch` (Review Focus 3) ⇒ FAIL.
- [ ] Sửa các hàm ⇒ PASS. Nguyên tắc: UA string đóng băng theo định dạng "reduced UA" hiện hành của Chromium (không phát minh định dạng).
- [ ] Web test: so sánh `navigator.userAgent`, `navigator.userAgentData`, header thực (qua server echo) ⇒ khớp.
- [ ] Commit: `kr: ua: profile-driven UA and client hints`.

---

### Task T6: Navigator, WorkerNavigator, Screen

**Files:**
- Modify: `third_party/blink/renderer/core/frame/navigator.cc`, `.../navigator_concurrent_hardware.cc`, `.../modules/device_memory/navigator_device_memory.cc`, `.../core/frame/navigator_language.cc`, `.../core/frame/screen.cc`, `.../core/workers/worker_navigator.cc`, `.../core/frame/window_or_worker_global_scope` (nếu cần)
- Test: `navigator_unittest`, web test `kr/navigator-context-matrix.html`

**Interfaces:** Consumes `cpu()`, `screen()`, `locale()`; Produces `hardwareConcurrency`, `deviceMemory`, `platform`, `languages`, `screen.*`, `devicePixelRatio`, `matchMedia(resolution)` nhất quán.

**Steps:**
- [ ] Test `ContextMatrix.NavigatorEqualAcrossMainWorkerIframeSW` (Review Focus 1) ⇒ FAIL.
- [ ] Sửa từng file. Lưu ý `window.devicePixelRatio`, `screen.availWidth/Height`, `outerWidth/innerWidth` phải thoả quan hệ hình học với `screen`.
- [ ] `matchMedia('(min-resolution: Xdppx)')` và CSS `resolution` khớp `dpr`.
- [ ] Commit: `kr: navigator: profile-driven navigator and screen`.

---

### Task T7: Timezone và Locale

**Files:**
- Modify: `third_party/blink/renderer/core/timezone/timezone_controller.cc` (hoặc nơi ICU default timezone được đặt), `content/renderer/render_thread_impl.cc`, nơi `Intl.DateTimeFormat().resolvedOptions()` lấy locale
- Test: web test `kr/timezone.html`

**Interfaces:** Consumes `locale()`; Produces `Date`, `Intl.*`, `getTimezoneOffset()` theo timezone profile, bao gồm DST đúng mốc lịch sử.

**Steps:**
- [ ] Test: với 30 timezone, `new Date(2026,0,1).getTimezoneOffset()` và `…(2026,6,1)` khớp dữ liệu IANA; `Intl.DateTimeFormat().resolvedOptions().timeZone` đúng; trong Worker cũng đúng.
- [ ] Sửa. Commit: `kr: locale: timezone and Intl from profile`.

---

### Task T8: Canvas 2D và OffscreenCanvas

**Files:**
- Modify: `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc` (`getImageData`), `.../core/html/canvas/html_canvas_element.cc` (`toDataURL`/`toBlob`), `.../modules/canvas/offscreencanvas/offscreen_canvas.cc` (`convertToBlob`)
- Test: `canvas_noise_test.cc`, web test `kr/canvas.html`

**Interfaces:** Consumes `NoiseU64(kCanvas, x, y)`; Produces ảnh đọc ra có nhiễu thưa (+-1 LSB), pixel hiển thị trên màn hình **không** đổi.

**Steps:**
- [ ] Test `CanvasNoise.Idempotent` (Review Focus 2): hai lần `toDataURL` ⇒ cùng chuỗi.
- [ ] Test `CanvasNoise.SameSeedSameOutput`, `CanvasNoise.DifferentSeedDiffers`, `CanvasNoise.BoundedDelta` (|delta| <= 1), `CanvasNoise.NotUniform` (tỉ lệ pixel bị chạm < 5%).
- [ ] Test `CanvasNoise.WorkerParity`: OffscreenCanvas trong Worker ⇒ cùng kết quả với main.
- [ ] Áp nhiễu ở **đường đọc** (readback), không ở đường vẽ ⇒ không ảnh hưởng người dùng nhìn thấy.
- [ ] Commit: `kr: canvas: deterministic readback noise`.

---

### Task T9: WebGL / WebGL2 / WebGPU

**Files:**
- Modify: `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc` (`getParameter`, `getSupportedExtensions`, `getShaderPrecisionFormat`, `readPixels`), `.../webgl_debug_renderer_info.cc`, `.../modules/webgpu/gpu_adapter.cc` (`info`), GPU process: chuỗi ANGLE trả về từ `gpu/config/gpu_info_collector*`
- Test: `webgl_profile_test.cc`, web test `kr/webgl.html`

**Interfaces:** Consumes `gpu()`; Produces `UNMASKED_VENDOR/RENDERER_WEBGL`, `VENDOR/RENDERER/VERSION`, mọi `getParameter(pname)` có trong `gpu.webgl.params`, extension list, precision format, `readPixels` có nhiễu.

**Steps:**
- [ ] Test `WebGL.UnmaskedMatchesProfile`, `WebGL.ParamsMatchProfileExactly` (lặp mọi pname), `WebGL.ExtensionsMatchAndOrdered`, `WebGL.WorkerParity`, `WebGL.ReadPixelsIdempotent`.
- [ ] Test `WebGL.ProfileNeverExceedsRealCaps`: giá trị khai báo `max_texture_size` <= giá trị thật của GPU máy chủ (tránh khai gian vượt khả năng ⇒ lỗi render thật).
- [ ] Sửa `getParameter`: nếu pname nằm trong profile ⇒ trả giá trị profile (clamp vào khả năng thật), ngược lại gọi hàm gốc.
- [ ] `getSupportedExtensions`: lọc danh sách thật ∩ profile (không khai extension máy thật không có).
- [ ] WebGPU: `adapter.info` / `requestAdapterInfo` khớp `gpu`, giới hạn (`limits`) lấy min(profile, thật).
- [ ] Commit: `kr: webgl: profile-driven parameters and extensions`.

---

### Task T10: WebAudio

**Files:**
- Modify: `third_party/blink/renderer/modules/webaudio/audio_buffer.cc`, `analyser_node.cc`, `offline_audio_context.cc` / `offline_audio_destination_node.cc`, `audio_context.cc` (`sampleRate`, `baseLatency`)
- Test: `audio_noise_test.cc`

**Interfaces:** Consumes `NoiseUnit(kAudio, …)`, `profile.audio` (sampleRate/latency nếu thêm vào schema v1.1).

**Steps:**
- [ ] Test `AudioNoise.OfflineRenderDeterministic`, `AudioNoise.BoundedAmplitude` (<= 1e-7 tương đối), `AudioNoise.DifferentSeedDiffers`, `AudioNoise.RealtimeOutputUntouched` (không nhiễu vào loa thật).
- [ ] Áp nhiễu ở đường đọc dữ liệu (`getChannelData`, `getFloatFrequencyData`, kết quả `OfflineAudioContext`).
- [ ] Commit: `kr: audio: deterministic readback noise`.

---

### Task T11: Fonts

**Files:**
- Modify: `third_party/blink/renderer/platform/fonts/font_cache.cc` / `win/font_cache_skia_win.cc` (hàm tra cứu họ font), `.../modules/font_access/` (Local Font Access), đo `measureText`/`offsetWidth`
- Test: web test `kr/fonts.html`

**Interfaces:** Consumes `fonts().installed`, `metric_salt`.

**Steps:**
- [ ] Test `Fonts.UnlistedFamilyFallsBack`: họ font ngoài danh sách ⇒ hành xử như chưa cài (rơi về font mặc định, đo chiều rộng giống font fallback).
- [ ] Test `Fonts.ListedFamilyResolves` cho mọi font trong profile **mà máy chủ có thật**; font có trong profile nhưng máy chủ không có ⇒ validator T16 phải loại (chỉ dùng font thật có trên host, hoặc bundle font vào thư mục `fonts/` kèm giấy phép).
- [ ] Test `Fonts.MeasureTextStable`: cùng seed ⇒ cùng `measureText`; sai khác giữa seed chỉ qua vi chỉnh `metric_salt` <= 0.01px, không đổi layout hiển thị.
- [ ] Commit: `kr: fonts: restrict and perturb font visibility`.

---

### Task T12: Ma trận ngữ cảnh đầy đủ (SharedWorker, ServiceWorker, Utility, about:blank, srcdoc, cross-origin iframe)

**Files:** Modify theo kết quả test; Test: `harness/tests/test_context_matrix.py` (Playwright) và web tests.

**Interfaces:** Produces bảng 12x? (xem test-strategy mục 4) toàn xanh.

**Steps:**
- [ ] Viết trang thu thập chạy trong mọi ngữ cảnh, trả JSON; test assert mọi trường chung bằng nhau.
- [ ] Sửa các ô đỏ. Đặc biệt kiểm `SharedWorker` (có thể là process khác), `ServiceWorker`, iframe `sandbox` và `about:blank` mới tạo.
- [ ] Commit: `kr: contexts: close context matrix gaps`.

---

### Task T13: WebRTC

**Files:**
- Modify: `content/renderer/media/webrtc/` (ICE candidate), `third_party/blink/renderer/modules/peerconnection/`, `services/network/p2p/` (địa chỉ local)
- Test: web test `kr/webrtc.html`

**Interfaces:** Consumes proxy/egress IP từ launcher (tham số `--kr-egress-ip` tuỳ chọn).

**Steps:**
- [ ] Test `WebRtc.NoRealLocalIpLeak`: candidates chỉ là mDNS `.local` hoặc địa chỉ egress đã cấu hình; không có IP LAN thật.
- [ ] Test `WebRtc.EnumerateDevicesMatchesProfile` (số camera/mic/loa khai theo profile, nhãn rỗng khi chưa cấp quyền).
- [ ] Commit: `kr: webrtc: no local ip leak, consistent devices`.

---

### Task T14: Mạng: TLS, HTTP/2, thứ tự header

**Files:**
- Modify: `net/socket/ssl_client_socket_impl.cc`, `net/ssl/ssl_config.*`, `net/spdy/spdy_session.cc` (SETTINGS), `net/http/http_network_transaction.cc`/`http_request_headers.cc` (thứ tự header), liên quan `third_party/boringssl` (chỉ cấu hình, không vá lõi nếu tránh được)
- Test: `net/` unittests; harness chạy server TLS local ghi ClientHello

**Interfaces:** Consumes `net.tls_profile`, `net.h2_settings`.

**Steps:**
- [ ] Test: server local ghi ClientHello và SETTINGS; assert khớp `chrome_win` của đúng phiên bản ghim; đo bằng đặc trưng bất biến theo thứ tự extension (R8) thay vì chuỗi JA3 thô.
- [ ] Thứ tự header HTTP/1.1 và pseudo-header HTTP/2 khớp Chromium gốc (không đổi so với stock). Mục tiêu chính ở task này là **không phát sinh sai khác** với Chromium stock cùng phiên bản, không phải giả trình duyệt khác.
- [ ] Commit: `kr: net: tls/h2 parity with pinned stock`.

---

### Task T15: Chống rò rỉ cấu hình

**Files:** Modify: `chrome/browser/ui/webui/version/` (che switch), crash/metrics reporting, `chrome/common/chrome_switches.*`, devtools about

**Steps:**
- [ ] Test `Leaks.VersionPageHidesKrSwitches`; `Leaks.NoKrStringsInJsVisibleApis` (quét `Object.getOwnPropertyNames` trên `window`, `navigator`, `chrome`, v.v. so với stock).
- [ ] Tắt crash reporting/metrics/Google API keys; không gửi seed ra ngoài.
- [ ] Test `NativeLook.ToStringIsNative`: các hàm bị đổi hành vi vẫn trả `function x() { [native code] }`, descriptor khớp stock (bằng cách snapshot so stock).
- [ ] Commit: `kr: hardening: leak review`.

---

### Task T17: Launcher và tích hợp

**Files:**
- Create: `kernel-r/tools/kr/launcher.py`, `kernel-r/scripts/kr-run.ps1`

**Interfaces:** Produces: `kr run [--persistent <name>] [--proxy …] [--url …]`: sinh seed ⇒ generate ⇒ validate ⇒ ghi profile vào file tạm ACL hạn chế ⇒ chạy `chrome.exe --kr-enabled --kr-profile=… --user-data-dir=<tmp>` ⇒ xoá tmp khi thoát (ephemeral).

**Steps:**
- [ ] Test `test_launcher.py::test_two_launches_differ` (hash tổng hợp khác nhau), `test_same_persistent_name_same_profile`, `test_tmp_dir_removed_on_exit`.
- [ ] Chạy toàn bộ bộ test strategy mục 7 ⇒ báo cáo.
- [ ] Commit: `kr: launcher: ephemeral and persistent modes`.

---

## Self-review

- Mỗi yêu cầu spec ↔ task: G1→T3; G2→T4,T8,T10; G3→T2,T16; G4→T16 distribution; G5→T15; G6→quy trình patch; G7→T17.
- Tên/kiểu thống nhất: `FingerprintProfile::Get()`, `NoiseU64`, `Domain::kCanvas…`, switch `kr-enabled/kr-profile/kr-profile-b64`.
- Mỗi Review Focus có test sở hữu (đã ghi trong từng task).
- Độ dài tương xứng; chi tiết thân hàm giữ ở mức chữ ký + giá trị cố định, thuật toán nằm ở spec.
