# Kế hoạch vá lỗ hổng fingerprint phát hiện qua phân tích hCaptcha HSW

Ngày: 2026-11-02. Cập nhật: 2026-11-11 (thêm H8-H11 từ deep HSW reverse engineering).
Trạng thái: **ĐÃ TRIỂN KHAI** H1-H7 C++ + harness + schema done, chờ build + verify.
**MỚI** H8-H11 (GOPD integrity, ws timing, toString, brand check) — KẾ HOẠCH, chưa làm.

## Bối cảnh

Phân tích script `hsw_downloaded.js` (proof-of-work challenge của hCaptcha) và bảng string đã giải mã
(`all_decoded_strings.json`) cho thấy HSW thu thập ~30 nhóm tín hiệu fingerprint. So với kernel-r
(41 patch, schema v1), có **7 lỗ hổng fingerprint** (H1-H7) — tín hiệu HSW đọc mà kernel-r chưa
kiểm soát, và **4 lỗ hổng integrity** (H8-H11) — phát hiện qua deep reverse engineering WASM
import functions (197 imports, 108+ GOPD checks, Reflect.get/set/apply bridge, brand check pattern).

Mục tiêu: **nhất quán với máy thật**, không phải "qua hCaptcha". Mỗi task đo bằng số, đối chứng
với Chrome stock trên cùng máy.

## Nguyên tắc (giữ nguyên từ phase 3)

1. Không đo được thì không sửa.
2. Ít trường giả hơn là tốt hơn.
3. Giá trị nào đo thật, nào giả định — ghi rõ.
4. Ngoài tầm trình duyệt thì chỉ ghi nhận.

---

## Danh sách task

### H1 — `speechSynthesis.getVoices()` — HIGH

**Vấn đề:** HSW thu thập danh sách giọng nói (`lang`, `localService`, `voiceURI`). Danh sách này
thay đổi theo OS locale, bản cài, và phần mềm TTS bổ sung. kernel-r chưa đụng.

**Strings HSW:** 248 (`speechSynthesis`), 249 (`getVoices`), 250 (`lang`), 251 (`localService`),
252 (`voiceURI`), 253 (`onvoiceschanged`).

**Kế hoạch:**
- **PLAN:** Filter danh sách voice trong Blink theo profile locale. Mỗi `lang` trong danh sách
  voice phải khớp `locale.languages` của profile (giữ `en-US`, `en-GB`, bỏ `ja-JP` nếu profile
  không có tiếng Nhật). Giọng `localService: true` (hệ thống) giữ; giọng cloud bỏ hết (không phụ
  thuộc cài đặt). Không cần thêm trường profile — suy từ `locale.languages`.
- **Điểm hook:** `third_party/blink/renderer/modules/speech/speech_synthesis.cc` —
  `SpeechSynthesis::voiceList()` hoặc `OnSetVoiceList()`. Filter trước khi trả cho JS.
- **TEST:**
  1. Unit test (blink_unittests): `SpeechSynthesisVoiceFilter.*` — profile VN chỉ có voice vi/en;
     profile US chỉ có voice en.
  2. Harness `check_voices.py`: mở chrome thật, đọc `speechSynthesis.getVoices()`, so với bản kr
     cùng locale — tập voice bản kr phải là tập con hợp lệ.
- **BUILD:** 1 patch Blink, ~30 dòng. Không đổi schema.

### H2 — `navigator.connection` (NetworkInformation) — HIGH

**Vấn đề:** HSW đọc `navigator.connection.rtt`, `.type`, `.downlink`, `.downlinkMax`. Giá trị phản
ánh mạng thật (WiFi/Ethernet, tốc độ, độ trễ). Khi chạy qua proxy, `rtt` cao bất thường so với
`type: "wifi"`.

**Strings HSW:** 55 (`connection`), 56 (`type`), 65 (`rtt`), 661 (`NetworkInformation`),
662 (`downlinkMax`).

**Kế hoạch:**
- **PLAN (a — ưu tiên): Spoof giá trị cố định theo loại kết nối của profile.**
  Thêm trường `net.connection` vào profile: `{type, downlink, rtt, downlinkMax}`.
  Generator gán mặc định hợp lý: desktop Windows → `type: "wifi"`, `downlink: 10`, `rtt: 50`,
  `downlinkMax: null` (Wi-Fi không có). Giá trị là tĩnh, không mô phỏng dao động.
- **PLAN (b — đơn giản hơn nếu a quá lớn): Tắt NetworkInformation API.**
  `navigator.connection` trả `undefined`. Chrome desktop Windows thật trả giá trị, nên tắt sẽ
  KHÁC Chrome thật → chỉ dùng nếu a không khả thi.
- **Điểm hook:** `third_party/blink/renderer/modules/netinfo/network_information.cc` — override
  các getter `type()`, `downlink()`, `rtt()`, `downlinkMax()`.
- **TEST:**
  1. Unit test: `NetworkInformation.ProfileOverride` — profile có `net.connection` → getter trả
     giá trị profile, không trả giá trị OS.
  2. Harness `check_netinfo.py`: đọc `navigator.connection` trong browser, verify giá trị khớp
     profile. So sánh stock: stock trả giá trị thật, kr trả giá trị profile.
- **BUILD:** 1 patch Blink (~40 dòng). Schema v1 thêm `net.connection` (optional). Generator thêm
  default. Constraints thêm rule `rtt > 0`, `downlink > 0`.

### H3 — CSS Media Feature queries — MEDIUM

**Vấn đề:** HSW dùng `matchMedia()` để probe ~15 media features:
`prefers-color-scheme`, `prefers-contrast`, `forced-colors`, `prefers-reduced-motion`,
`prefers-reduced-transparency`, `color-gamut`, `monochrome`, `inverted-colors`,
`display-mode`, `any-hover`, `any-pointer`, `hover`, `pointer`.

kernel-r spoof `device-width/height/dpr` (P20) nhưng KHÔNG kiểm soát theme/accessibility.
Kết quả phụ thuộc cài đặt Windows thật của host.

**Strings HSW:** 521-554.

**Kế hoạch:**
- **PLAN:** Không thêm trường profile cho từng media feature (quá nhiều, ít đa dạng).
  Thay vào đó, cờ `--kr-force-media-defaults` cưỡng nhóm giá trị phổ biến nhất:
  `prefers-color-scheme: light`, `prefers-contrast: no-preference`,
  `forced-colors: none`, `prefers-reduced-motion: no-preference`,
  `prefers-reduced-transparency: no-preference`, `color-gamut: srgb`,
  `inverted-colors: none`, `any-hover: hover`, `any-pointer: fine`,
  `pointer: fine`, `hover: hover`, `display-mode: browser`, `monochrome: 0`.
  Đây là giá trị mặc định cho ~90% máy Windows desktop, Chrome, không bật accessibility.
- **Điểm hook:** `third_party/blink/renderer/core/css/media_query_evaluator.cc` hoặc
  `third_party/blink/renderer/core/frame/settings.cc` — override các hàm trả giá trị media.
  Một số (`prefers-color-scheme`) đã có setting path qua `WebPreferences`.
- **TEST:**
  1. Harness `check_media_features.py`: chạy `matchMedia()` cho tất cả 15 features, verify
     bản kr trả giá trị mặc định. So sánh stock: stock trả giá trị host.
  2. Edge case: host bật dark mode → kr vẫn phải trả `light`.
- **BUILD:** 1 patch Blink. Có thể dùng cờ Chromium sẵn có (`--force-dark-mode` ngược lại);
  kiểm tra trước. Nếu `WebPreferences` đã cover hết → chỉ cần set cờ, KHÔNG cần patch.
  Nếu thiếu → patch nhỏ.

### H4 — `performance.memory.jsHeapSizeLimit` — MEDIUM

**Vấn đề:** HSW đọc `performance.memory.jsHeapSizeLimit`. Giá trị này phụ thuộc RAM thật của
host (V8 set heap limit theo RAM). Khác RAM → khác limit → fingerprint.

**Strings HSW:** 236 (`memory`), 237 (`jsHeapSizeLimit`).

**Kế hoạch:**
- **PLAN:** Override `jsHeapSizeLimit` trả giá trị chuẩn cho RAM bucket trong profile.
  Mapping: 4GB→2.17GB, 8GB→4.29GB, 16GB→4.29GB, 32GB→4.29GB (Chrome cap ở ~4.29GB cho
  x64 khi RAM >= 8GB). Xác minh bằng đo Chrome stock trên các config RAM khác nhau trước.
- **Điểm hook:** `third_party/blink/renderer/core/timing/memory_info.cc` —
  `MemoryInfo::totalJSHeapSize()` / `jsHeapSizeLimit()`.
  Lưu ý: Chrome đã quantize giá trị này (bước 10MB) để chống timing attack. Chỉ cần override
  base value, giữ quantization.
- **TEST:**
  1. Harness `check_heap_limit.py`: đọc `performance.memory.jsHeapSizeLimit` trong browser,
     verify giá trị khớp bucket theo `cpu.ram_gb` trong profile.
  2. So sánh stock: stock trả giá trị thật.
- **BUILD:** 1 patch Blink (~15 dòng). Không cần đổi schema (suy từ `cpu.ram_gb`).

### H5 — `StorageManager.estimate()` quota — MEDIUM

**Vấn đề:** HSW gọi `navigator.storage.estimate()` để đọc `quota` và `usage`. `quota` phụ
thuộc dung lượng ổ đĩa thật (~60% dung lượng trống). Khác ổ → khác quota → fingerprint.

**Strings HSW:** 198 (`storage`), 199 (`estimate`), 200 (`usageDetails`), 201 (`quota`),
202 (`usage`).

**Kế hoạch:**
- **PLAN:** Override `quota` trả giá trị chuẩn. Chrome thật:
  `quota ≈ min(diskFreeSpace * 0.6, maxQuota)`. Spoof: trả một giá trị cố định hợp lý
  (ví dụ 300GB = 322122547200 bytes — tương đương ổ 500GB trống 500GB, rất phổ biến).
  `usage` giữ nguyên (thấp, khác nhau không đáng kể trên profile mới).
  Thêm `net.storage_quota_gb` vào profile (optional, default suy từ một giá trị cố định).
- **Điểm hook:** `content/browser/storage/storage_manager.cc` hoặc
  `storage/browser/quota/quota_manager_impl.cc` — override `GetUsageAndQuota` result.
- **TEST:**
  1. Harness `check_storage_quota.py`: gọi `navigator.storage.estimate()`, verify `quota`
     khớp profile. So sánh stock.
- **BUILD:** 1 patch `content/` hoặc `storage/` (~20 dòng). Schema v1 không bắt buộc đổi
  (hardcode giá trị chuẩn, hoặc thêm trường optional).

### H6 — `Permissions.query()` states — MEDIUM

**Vấn đề:** HSW gọi `navigator.permissions.query()` cho ~25 permission names và thu thập
`state` (`granted`/`denied`/`prompt`). Trên profile mới, tất cả nên là `prompt`. Nhưng nếu
user trước đó đã grant/deny trên origin khác, giá trị có thể leak.

**Strings HSW:** 141-170 (danh sách permissions), 165 (`granted`), 166 (`denied`),
167 (`default`), 168 (`permissions`), 169 (`query`), 171 (`state`).

**Kế hoạch:**
- **PLAN:** Khi kr bật và profile là ephemeral, override `Permissions.query()` trả `prompt`
  cho MỌI permission (trừ `notifications` trả `default`). Lý do: profile mới = chưa hỏi gì.
  Persistent profile giữ nguyên (permission state lưu theo profile data dir).
- **Điểm hook:**
  `third_party/blink/renderer/modules/permissions/permissions.cc` — `Permissions::query()`.
  Hoặc ở tầng browser: `content/browser/permissions/permission_service_impl.cc`.
  Tầng browser an toàn hơn (không bypass được từ JS).
- **TEST:**
  1. Harness `check_permissions.py`: query tất cả 25 permissions HSW probe, verify tất cả
     trả `prompt` trên ephemeral profile. So sánh stock (stock trả state thật).
  2. Edge case: sau khi user grant camera trên một trang → ephemeral profile vẫn trả `prompt`.
- **BUILD:** 1 patch `content/` (~25 dòng). Không cần đổi schema.

### H7 — `window.outerWidth/Height` và `innerWidth/Height` — LOW-MEDIUM

**Vấn đề:** HSW đọc `outerWidth/Height`, `innerWidth/Height`. kernel-r spoof `screen.*` và
CSS `device-width/height` nhưng window dimensions follow kích thước cửa sổ thật. Nếu cửa sổ
maximize trên màn hình 2560x1440 thật nhưng profile nói 1920x1080 → `outerWidth > screen.width`.

**Strings HSW:** 341 (`outerWidth`), 342 (`outerHeight`), 353 (`innerWidth`), 354 (`innerHeight`).

**Kế hoạch:**
- **PLAN:** Clamp `outerWidth/Height` không vượt `screen.w/h` của profile. `innerWidth/Height`
  đã theo cửa sổ thật (nếu cửa sổ nhỏ hơn screen thì ok). Chỉ cần clamp khi maximize.
  Cách tốt nhất: launcher set `--window-size` <= profile screen, đã làm ở `main.py`.
  Kiểm tra: `outerWidth <= screen.w` và `outerHeight <= screen.h` luôn đúng.
- **Điểm hook:** Nếu launcher đã set đúng → KHÔNG CẦN PATCH. Chỉ cần verify bằng harness.
  Nếu vẫn vượt (maximize trên multi-monitor) → patch
  `third_party/blink/renderer/core/frame/local_dom_window.cc` clamp `outerWidth/Height`.
- **TEST:**
  1. Harness `check_window_dims.py`: verify `outerWidth <= screen.width`,
     `outerHeight <= screen.height`, `innerWidth <= outerWidth`, `innerHeight <= outerHeight`.
  2. Edge case: maximize trên màn hình lớn hơn profile.
- **BUILD:** Có thể 0 patch (nếu launcher đã đủ). Nếu cần: 1 patch Blink (~10 dòng).

### H8 — GOPD property descriptor integrity (108+ checks) — HIGH

**Vấn đề:** HSW WASM gọi `Object.getOwnPropertyDescriptor()` hơn 108 lần trên các property của
`window`, `navigator`, `screen`, `document`, v.v. để phân biệt DATA descriptor (có `value`) vs
ACCESSOR descriptor (có `get/set`) vs `undefined`. Nếu kernel-r override property bằng cách thay
đổi kiểu descriptor (vd: Chrome stock dùng getter cho `navigator.hardwareConcurrency` nhưng patch
tạo data property, hoặc ngược lại), HSW phát hiện sai lệch.

**Verified:** Phân tích WASM cho thấy 197 import functions, trong đó nhóm lớn nhất route qua
`Reflect.get/set/apply` bridge, bao gồm GOPD checks. File `test-brandcheck.mjs` trong HCaptchaV2
xác nhận HSW kiểm tra descriptor type trên nhiều property.

**Kế hoạch:**
- **PLAN:** kernel-r patch ở tầng C++ (Blink internal), KHÔNG dùng `Object.defineProperty` từ JS.
  Do đó descriptor type PHẢI khớp Chrome stock tự nhiên. Nhưng cần KIỂM CHỨNG hệ thống cho MỌI
  property bị hook.
- **CHECKLIST cần verify:**
  - `navigator.hardwareConcurrency`: stock = accessor (getter trên NavigatorConcurrentHardware IDL) → kr phải giữ accessor
  - `navigator.deviceMemory`: stock = accessor → kr phải giữ accessor
  - `navigator.platform`: stock = accessor → kr phải giữ accessor
  - `navigator.userAgent`: stock = accessor → kr phải giữ accessor
  - `navigator.language/languages`: stock = accessor → kr phải giữ accessor
  - `screen.width/height/colorDepth/pixelDepth`: stock = accessor → kr phải giữ accessor
  - `screen.availWidth/availHeight`: stock = accessor → kr phải giữ accessor
  - Canvas `getContext/toDataURL/toBlob`: stock = data (value on prototype) → kr phải giữ data
  - `AudioContext/OfflineAudioContext`: constructor và prototype methods
  - `navigator.connection.*`: stock = accessor → kr phải giữ accessor (xem H2)
  - `window.devicePixelRatio`: stock = accessor → kr phải giữ accessor
  - `Date.prototype.getTimezoneOffset`: stock = data (value on prototype) → kr phải giữ data
  - `Intl.DateTimeFormat.prototype.resolvedOptions`: stock = data → kr phải giữ data
- **TEST:**
  1. Harness `check_gopd_integrity.py`: cho MỖI property kernel-r đã hook, so sánh
     `Object.getOwnPropertyDescriptor(obj, prop)` giữa bản kr và bản stock:
     - Cùng `configurable`, `enumerable`
     - Cùng kiểu: cả hai đều có `get/set` HOẶC cả hai đều có `value/writable`
     - Nếu accessor: `typeof get === 'function'` và `get.toString()` trả native format
  2. Unit test C++: verify rằng IDL-generated code vẫn sinh accessor cho các property đã hook.
- **BUILD:** Nếu tất cả descriptor khớp → 0 patch (chỉ thêm test). Nếu phát hiện sai lệch → sửa
  cách hook trong C++ để giữ đúng descriptor type.

### H9 — ws (WASM fingerprint) timing phải tương quan hardwareConcurrency — HIGH

**Vấn đề:** HSW sinh WASM fingerprint (`ws` field trong getcaptcha/checkcaptcha) bằng cách đo thời
gian thực thi một số WASM microbenchmark. Thời gian này tương quan với số core CPU: nhiều core =
nhanh hơn. Công thức verified:
```
speedFactor = cores >= 12 ? 0.7 : cores >= 8 ? 0.85 : cores >= 6 ? 1.0 : 1.2
timing[i] = round((base[i] + jitter) * speedFactor)
```
Cấu trúc ws: `[[8,2,1,3,4],[1,1,1,1],20,[t1,t2,t3,t4,t5]]`

Nếu kernel-r spoof `navigator.hardwareConcurrency` thành 4 core nhưng máy thật có 14 core, WASM
sẽ chạy nhanh (timing ~0.7x) trong khi khai báo chỉ 4 core (nên timing ~1.2x). Server so sánh ws
timing với hardwareConcurrency → phát hiện bất nhất quán.

**Verified:** `hcaptcha.js:240-255` — hàm `wasmFingerprint(coreCount)` với công thức speedFactor
chính xác như trên. Giá trị base: `[61, 52, 66, 44, 48]` ms. Jitter: gaussian σ=3.

**Kế hoạch:**
- **PLAN (a — ưu tiên):** KHÔNG spoof hardwareConcurrency xuống thấp hơn máy thật. Chỉ spoof
  XUỐNG (vd: máy 14 core khai 8 core — WASM chạy nhanh hơn khai báo, nhưng chênh nhỏ) hoặc giữ
  nguyên. Cụ thể: generator chỉ sinh `hardwareConcurrency ∈ {realCores, realCores - 2}` cho bucket
  >= 6; không bao giờ sinh 2 core trên máy 16 core.
- **PLAN (b — Phase 2/VM):** Trong VM, CPU core thật = profile core → timing tự khớp.
- **Ràng buộc mới cho Validator:** `ws_timing_range(profile.cpu.cores)` phải overlap với
  WASM benchmark thật trên máy (đo bằng harness).
- **TEST:**
  1. Harness `check_wasm_timing.py`: chạy WASM microbenchmark (dùng benchmark tương tự HSW) trong
     kernel-r browser, so timing với hardwareConcurrency đã khai. Verify: `timing * speedFactor^-1`
     nằm trong khoảng hợp lý (±30% so với base values).
  2. Unit test: Validator reject profile có `cpu.cores: 2` trên máy `realCores >= 8`.
- **BUILD:** Sửa generator (Python): thêm ràng buộc `min_cores = max(realCores - 4, 4)` nếu
  `realCores >= 6`. Sửa Validator: thêm rule. Không cần patch C++.

### H10 — Function.prototype.toString native format — MEDIUM

**Vấn đề:** HSW kiểm tra `Function.prototype.toString.call(fn)` trên nhiều API function để verify
chúng trả `"function X() { [native code] }"`. JS-level hook (proxy, wrapper function) sẽ trả source
code thật thay vì native format → bị phát hiện.

**Verified:** `test-brandcheck.mjs` trong HCaptchaV2 cho thấy phải tạo extensive `nativeFns` set
và patch `Function.prototype.toString` để hide JS wrappers trong môi trường jsdom. HSW kiểm tra
toString trên: `Document.createElement`, `navigator.userAgent` getter, `Element.getBoundingClientRect`,
`HTMLCanvasElement.getContext`, `WebAssembly.instantiate`, v.v.

**Kế hoạch:**
- **PLAN:** kernel-r hook ở tầng C++ (WebIDL / Blink internal) nên `toString()` TỰ NHIÊN trả
  native format. NHƯNG cần verify hệ thống rằng KHÔNG có JS-level hook nào bị lọt.
- **Kiểm tra:** grep toàn bộ patch set cho pattern `ExecuteJavaScript`, `EvaluateScript`,
  `ContentSecurityPolicy::AddEval` — nếu có JS injection, nó PHẢI pass toString check.
- **TEST:**
  1. Harness `check_tostring.py`: cho MỖI API function mà kernel-r override, gọi
     `Function.prototype.toString.call(fn)` và verify output match `/^function \w*\(\) \{ \[native code\] \}$/`.
  2. Kiểm thêm: `fn.toString === Function.prototype.toString` (không bị shadow).
- **BUILD:** Nếu tất cả pass → 0 patch (chỉ thêm test). Nếu phát hiện lỗi → sửa hook C++.

### H11 — Brand check / this context TypeError — MEDIUM

**Vấn đề:** HSW WASM gọi DOM method với `this` SAI context để kiểm tra chúng throw đúng TypeError
("Illegal invocation"). Ví dụ: lấy `Document.prototype.createElement` rồi gọi với `this = {}`
thay vì `this = document`. Chrome thật throw TypeError; môi trường giả (jsdom, Puppeteer
evaluate polyfill) có thể không throw hoặc throw message khác.

**Verified:** `test-brandcheck.mjs` trong HCaptchaV2 cho thấy phải bypass brand checks cho:
- `Document.createElement/querySelector/querySelectorAll`
- `Node.appendChild/removeChild/insertBefore`
- `Element.append/prepend/remove/setAttribute/getAttribute`
- `Navigator.userAgent` getter
- `HTMLIFrameElement.contentWindow` getter
- `PluginArray.item`

HSW dùng pattern: `Reflect.apply(fn, wrongThis, args)` → expect TypeError → nếu không throw = giả.

**Kế hoạch:**
- **PLAN:** kernel-r IS Chrome, nên brand check TỰ NHIÊN hoạt động đúng (IDL binding sinh code
  kiểm `this` type). NHƯNG nếu kernel-r override method bằng C++ wrapper mà quên kiểm `this`
  context, brand check sẽ KHÔNG throw → bị phát hiện.
- **TEST:**
  1. Harness `check_brandcheck.py`: cho MỖI API method mà kernel-r override:
     - Gọi `method.call({})` → phải throw TypeError
     - Gọi `method.call(correctObject)` → phải thành công
     - Verify error message chứa "Illegal invocation" hoặc "is not a function" (đúng Chrome format)
  2. Edge case: getter trên Navigator prototype gọi với `this = {}`.
- **BUILD:** Nếu tất cả pass → 0 patch (chỉ thêm test). Nếu hook C++ nào bỏ qua this-check →
  sửa bằng cách giữ IDL dispatch path, chỉ thay đổi giá trị trả về bên trong.

---

## Thứ tự thực hiện

```
H8 (GOPD integrity) ─┐
H9 (ws timing)  ─────┤── ƯU TIÊN CAO, chạy trước vì ảnh hưởng generator/validator
H10 (toString) ──────┤── song song, chủ yếu là verify + thêm test
H11 (brand check) ───┘
     │
     ▼
H1 (voices) ──┐
H2 (netinfo) ─┤── song song, không phụ thuộc nhau
H4 (heap) ────┘
     │
     ▼
H3 (media features) ── có thể không cần patch, kiểm tra cờ sẵn trước
     │
     ▼
H5 (storage quota) ─── patch content/, cần cẩn thận dependency
H6 (permissions) ───── patch content/, cùng tầng với H5
     │
     ▼
H7 (window dims) ──── verify trước, patch nếu cần
```

**Ước tính tổng:** 5-6 patch Blink/content (~150-200 dòng C++), sửa generator/validator (Python,
~50 dòng), 11 harness script mới. H8/H10/H11 có thể cần 0 patch nếu verify đạt (chỉ thêm test).
H9 cần sửa generator Python. Không có patch nào đụng `net/` hay `boringssl`.

## Schema v1 changes

| Trường mới | Bắt buộc | Mặc định | Task |
|-----------|---------|---------|------|
| `net.connection.type` | Không | `"wifi"` | H2 |
| `net.connection.downlink` | Không | `10` | H2 |
| `net.connection.rtt` | Không | `50` | H2 |
| `net.connection.downlink_max` | Không | `null` | H2 |

Tất cả trường khác (H1, H3, H4, H5, H6, H7, H8, H10, H11) suy từ profile hiện có, không cần
thêm trường.

**Ràng buộc mới cho Validator (H9):** `cpu.cores >= max(realCores - 4, 4)` khi `realCores >= 6`.
Đây không phải trường mới mà là ràng buộc trên trường `cpu.cores` hiện có, để đảm bảo WASM
execution timing tương quan với hardwareConcurrency khai báo.

## Rủi ro

| ID | Rủi ro | Giảm thiểu |
|----|--------|-----------|
| RH1 | Voice list trên Windows thay đổi theo bản cập nhật / cài TTS → corpus cần cập nhật | Capture thêm trên Windows 11 23H2/24H2; filter theo locale không cần danh sách cố định |
| RH2 | `performance.memory` có thể thay đổi quantization giữa Chrome versions | Đo trên Chrome 157 stock trước, hardcode bucket |
| RH3 | `StorageManager.estimate()` override ở tầng `content/` có thể ảnh hưởng ServiceWorker cache | Test với SW registration + cache.add |
| RH4 | Chrome mới có thể thay đổi NetworkInformation API (đã có proposal deprecate) | Kiểm mỗi lần nâng Chromium |
| RH5 | GOPD check list có thể thay đổi qua các phiên bản HSW (WASM binary cập nhật) | Harness check all kr-hooked properties, không hardcode danh sách HSW |
| RH6 | WASM benchmark timing biến thiên do thermal throttling, load hệ thống | H9 dùng khoảng ±30%, không so chính xác |
| RH7 | Nếu kernel-r thêm JS-level hook trong tương lai (vd: isolated world), toString/brand-check sẽ fail | Policy: KHÔNG inject JS vào main/isolated world trừ automation (đã có rào G5) |

## Items LOW priority (không làm đợt này, theo dõi)

- **`Element.getClientRects()` DOMRect sub-pixel** — cần hiểu sâu rendering pipeline; rủi ro
  patch sai cao. Theo dõi xem có site nào dùng riêng DOMRect.
- **`canvas.measureText()` font metrics** — khác biệt nhỏ, phụ thuộc font rendering stack;
  P13 (font hiding) đã giảm bề mặt. Làm nếu đo được khác biệt lớn.
- **`SVGTextContentElement.getComputedTextLength()`** — tương tự measureText.
- **`Intl.DisplayNames/ListFormat/...`** — follow locale, likely ok.
- **Audio/Video codec support** — standard trên cùng Chrome version.
- **WebRTC codec capabilities** — standard.
- **Performance timing entries** — real timing, không spoof được mà không phá.
- **pdc (25 detection counter fields)** — 25 trường timing gửi trong `checkcaptcha` (verified:
  `hcaptcha.js:573-599`). Đây là tầng APPLICATION (hCaptcha client code), không phải tầng browser.
  kernel-r không cần xử lý; ứng dụng gọi hCaptcha API tự sinh pdc phù hợp. Ghi nhận cấu trúc:
  `{s, n, bfp, bfc, bfa, bek, bef, bei, big, bpt, gca, gci, p, gcs, gcad, gcid, gces, gcee,
  gcds, gcde, gce, t, l, o, c}`.
- **pem (performance metrics)** — 4 trường timing liên quan checksiteconfig latency (verified:
  `hcaptcha.js:258-266`): `{csc, csch, cscrt, cscft}`. Cũng là tầng APPLICATION.
- **clientOptions (12 fields)** — config object gửi trong getcaptcha/checkcaptcha (verified:
  `hcaptcha.js:463-478`): `{sentry, reportapi, recaptchacompat, custom, hl, tplinks, andint,
  pat, pstissuer, endpoint, theme, size, confirm-nav}`. Tầng APPLICATION, kernel-r không cần.
- **Encrypted request mode** — hCaptcha hỗ trợ msgpack encode → encrypt(JWT) → binary body
  (verified: `hcaptcha.js` + `msgpack.js`). Tầng APPLICATION. Lưu ý: encrypted body dùng
  Content-Type binary → không qua CycleTLS → TLS fingerprint có thể khác (đã ghi nhận trong
  HCaptchaV2/PLAN.md).
