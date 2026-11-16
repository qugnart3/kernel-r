# Kernel-R Handover — 2026-11-16

## Dự án là gì
Chromium 158 fork browser (tag 158.0.8127.37, branch kr/base). Mỗi lần launch, load fingerprint profile từ JSON file qua `--kr-profile` switch. Profile chứa fake values cho screen, navigator, GPU, timezone, fonts, canvas noise, audio noise, v.v. Mục tiêu: mỗi instance có fingerprint riêng biệt, realistic, consistent across contexts (Main/Worker/iframe).

## Máy build
- Xeon E5-2696v3 18C/36T, 64GB RAM, GTX 1070 8GB, Win10 LTSC 2019 build 18363
- Chromium source: `C:\src\chromium\src` 
- Build output: `C:\src\chromium\src\out\KernelR`
- depot_tools: `C:\depot_tools`
- Project files: `C:\src\kernel-r` (profiles, test pages, scripts, reverse engineering)
- Plans/docs: `C:\Users\h\Desktop\Build_Browser`

## Build command
```powershell
$env:vs2022_install = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
cd C:\src\chromium\src
C:\depot_tools\autoninja.bat -C out/KernelR chrome
```
**QUAN TRỌNG**: Phải set `$env:vs2022_install` TRƯỚC MỖI LẦN build. Phải kill tất cả chrome.exe trước khi build (v8_context_snapshot_generator bị lock file).

## args.gn (`out/KernelR/args.gn`)
```
is_debug = false
is_component_build = false
is_official_build = false
dcheck_always_on = false        # Quan trọng — DCHECK crash trên file:// URLs nếu true
target_cpu = "x64"
blink_symbol_level = 0
symbol_level = 1
chrome_pgo_phase = 0
use_thin_lto = false
windows_sdk_path = "C:\\Program Files (x86)\\Windows Kits\\10"
```

## Kiến trúc KR Fingerprint

### Profile system
- **Profile JSON**: `C:\src\kernel-r\test_profile.json` — chứa tất cả fake values + toggles bật/tắt từng nhóm
- **Profile loader**: `components/kr_fingerprint/profile_loader.cc` — đọc JSON, parse vào `ProfileData` struct
- **ProfileData**: `components/kr_fingerprint/profile_data.h` — struct chứa screen, navigator, gpu, locale, fonts, voices, connection, toggles
- **FingerprintProfile singleton**: `blink/platform/kr_fingerprint/fingerprint_profile.h/.cc` — singleton trong renderer process, accessors: `fp.screen()`, `fp.navigator()`, `fp.gpu()`, `fp.locale()`, `fp.fonts()`, `fp.seed()`, `fp.IsToggleEnabled("group_name")`
- **DeterministicNoise**: `components/kr_fingerprint/deterministic_noise.h/.cc` — SipHash-2-4 wrapper (BoringSSL), domain-separated, deterministic theo seed+domain
- **kr_switches**: `components/kr_fingerprint/kr_switches.h/.cc` — define `--kr-profile` switch

### Initialization flow
1. `blink_initializer.cc::InitializeCommon()` — load profile từ `--kr-profile` switch
2. `GetBlinkInitializer().Initialize()` → `CoreInitializer::Initialize()` → `TimeZoneController::Init()`
3. SAU đó: `TimeZoneController::SetTimeZoneOverride()` với timezone từ profile (RAII handle leaked intentionally)
4. Switch propagation: `render_process_host_impl.cc` whitelist `--kr-profile` để truyền từ browser → renderer process

### Chrome 158 API notes
- `base::DictValue`, `base::ListValue`, `base::JSONReader::ReadDict()`
- `String::FromUtf8()` (không phải FromUTF8)
- `base::NoDestructor` cho singleton lifetime
- `base::EqualsCaseInsensitiveASCII()` cho string compare

## Trạng thái các task (T = Task, H = Hotfix từ hCaptcha audit)

### HOÀN THÀNH
| Task | Mô tả | Files chính | Toggle |
|------|--------|------------|--------|
| T1-T3 | Infrastructure (switches, loader, profile) | `components/kr_fingerprint/*` | — |
| T4 | DeterministicNoise (SipHash) | `components/kr_fingerprint/deterministic_noise.*` | — |
| T5 | UA/Client Hints, navigator.platform, webdriver | `navigator.cc`, `navigator_ua_data.cc` | `screen` |
| T6 | Screen + CPU/Memory | `screen.cc`, `navigator_concurrent_hardware.cc`, `navigator_device_memory.cc` | `screen`, `cpu_memory` |
| T7 | Timezone/Locale (language, languages, timezone) | `blink_initializer.cc`, `navigator_language.cc` | `locale_tz` |
| T8 | Canvas 2D noise | `canvas_noise.cc/h`, `base_rendering_context_2d.cc`, `image_data_buffer.cc` | `canvas` |
| T9 | WebGL GPU spoofing (vendor, renderer, params) | `webgl_rendering_context_base.cc` | `gpu_webgl` |
| T10 | WebAudio noise | `audio_noise.cc/h`, `audio_buffer.cc/h` | `audio` |
| T11 | Font whitelist (block at render level) | `font_cache.cc` | `fonts` |
| T12 | Context Matrix (timezone Worker/iframe consistency) | `blink_initializer.cc` (TimeZoneController) | `locale_tz` |
| H1 | Screen leak fixes (innerWidth/outerWidth/DPR/matchMedia) | `local_dom_window.cc`, `media_values.cc` | `screen` |
| H2 | Accept-Language header override | `profile_network_context_service.cc` | `locale_tz` |
| T13 | WebRTC IP leak prevention (2 layers) | `renderer_preferences_util.cc`, `rtc_peer_connection.cc` | `webrtc` |
| T14 | TLS/H2 parity — verified stock (0 net/ changes) | Không sửa file — thừa hưởng Chromium 158 stock | — |
| T15 | Anti-config-leak (D21 bg connections + D22 chrome://version) | `chrome_main_delegate.cc`, `version_ui.cc` | — |
| H3 | navigator.connection spoofing (effectiveType/rtt/downlink/saveData) | `network_information.cc` | `network` |
| H4 | maxTouchPoints from profile | `navigator_events.cc` | `screen` |
| H6 | Voices API filter (by name or locale prefix) | `speech_synthesis.cc` | `voices` |
| H7 | Storage quota override | `storage_manager.cc` | — (active + quota>0) |

### Profile cập nhật mới nhất (ĐÃ TEST — PASS 2026-11-16)
- **Fonts**: Mở rộng từ 17 → 71 fonts (Windows 10 default set đầy đủ) ✓
- **CPU/Memory**: cores=8, device_memory=16 (khớp GTX 1070 tier, trước đó cores=6 memory=8) ✓

### CHƯA LÀM
| Task | Mô tả | Priority |
|------|--------|----------|
| ~~T13~~ | ~~WebRTC (local IP leak, ICE candidates)~~ | ~~DONE~~ |
| ~~T14~~ | ~~TLS/H2 (verified stock — 0 net/ changes)~~ | ~~DONE~~ |
| ~~T15~~ | ~~Anti-config-leak (D21+D22)~~ | ~~DONE~~ |
| ~~H3-H4~~ | ~~Connection + maxTouchPoints~~ | ~~DONE~~ |
| ~~H6-H7~~ | ~~Voices filter + Storage quota~~ | ~~DONE~~ |
| T17 | Launcher + Manager UI (production) | Medium |
| H5,H8-H11 | hCaptcha remaining gaps (screenX/Y, permissions — all P2+) | Low |
| A1-A15 | Automation (Named Pipe + SendMessage+HWND) | Later |

### Bài học quan trọng (Lessons Learned)
1. **Screen values phải gần thực tế** — CSS layout viewport (getBoundingClientRect, vw/vh units) không thể spoof. Profile 4K gây flag, 1920x1080 pass
2. **Timezone phải khớp IP** — hCaptcha cross-check timezone vs IP geolocation. Nếu IP VN → dùng Asia/Ho_Chi_Minh
3. **Font list quá ít = suspicious** — 17 fonts bị flag, cần 60-80+ fonts Windows mặc định
4. **cpu_memory phải khớp GPU tier** — GTX 1070 + 6 cores + 8GB RAM = không hợp lý
5. **Noise-only patches (T8/T9/T10) safe** — Chỉ thêm deterministic noise, không tạo cross-signal inconsistency
6. **`icu::TimeZone::adoptDefault()` không đủ** — Phải dùng `TimeZoneController::SetTimeZoneOverride()` để notify V8 trong Workers
7. **`document.fonts.check()` không detect system fonts** — Phải block tại `FontCache::GetFontPlatformData()` level
8. **TLS/H2 parity = verification, not implementation** — Nếu 0 file `net/`/`boringssl` bị sửa → TLS fingerprint tự động khớp stock. Chrome 110+ shuffle extension order mỗi session → JA3 hash thay đổi, nhưng ciphers/curves/H2 SETTINGS cố định

## hCaptcha Reverse Engineering
- Full analysis: `C:\src\kernel-r\reverse\HCAPTCHA_SIGNALS.md`
- Downloaded JS: `C:\src\kernel-r\reverse/hcaptcha.html` (iframe, 698KB), `reverse/api.js` (outer, 420KB)
- VM bytecode interpreter: 63,533 opcodes, 4,106 decoded strings
- Key fingerprint functions: `interrogateNavigator()`, `getScreenDimensions()`, `dpr()`, `getWindowDimensions()`, `Mt()` (DOM hook detection)
- hCaptcha dumps ALL navigator and screen properties via `for..in` loop — any missing/extra property is detectable

## Test tools
- **Test dashboard**: `C:\src\kernel-r\test_toggles.html` — verification dashboard cho tất cả toggle groups
- **Context matrix**: `C:\src\kernel-r\test_context_matrix.html` — Main vs Worker vs iframe consistency
- **TLS/H2 verify**: `C:\src\kernel-r\test_tls.html` — fetch tls.peet.ws, compare JA3/JA4/H2 vs Chrome expected
- **Anti-leak verify**: `C:\src\kernel-r\test_antileak.html` — toString integrity, GOPD, KR string scan, brand check, chrome://version
- **Launcher UI**: `C:\src\kernel-r\launcher.py` — Python HTTP server (port 7700) cho bật/tắt toggles + relaunch Chrome
  - Chạy: `"C:\Users\h\AppData\Local\Programs\Python\Python312\python.exe" "C:\src\kernel-r\launcher.py"`
  - Mở: `http://localhost:7700`

## RÀNG BUỘC TUYỆT ĐỐI
- **KHÔNG dùng Playwright, Puppeteer, CDP, hay bất kỳ external automation tool nào**
- Automation sẽ qua 2-tier system: Named Pipe C++ (logic) + SendMessage+HWND (input, OS level)
- Tất cả thay đổi chưa commit (T1-T12, H1-H2 đều local changes)

## Files đã sửa (chưa commit)
```
components/kr_fingerprint/
  BUILD.gn, deterministic_noise.cc/h, kr_switches.cc/h, 
  profile_data.h, profile_loader.cc

third_party/blink/renderer/controller/
  blink_initializer.cc

third_party/blink/renderer/core/frame/
  navigator.cc, navigator_concurrent_hardware.cc, navigator_device_memory.cc,
  navigator_language.cc/h, navigator_ua_data.cc, screen.cc,
  local_dom_window.cc

third_party/blink/renderer/core/css/
  media_values.cc

third_party/blink/renderer/core/timezone/
  (không sửa, chỉ dùng API)

third_party/blink/renderer/platform/kr_fingerprint/
  fingerprint_profile.cc/h, canvas_noise.cc/h, audio_noise.cc/h

third_party/blink/renderer/platform/fonts/
  font_cache.cc

third_party/blink/renderer/platform/BUILD.gn

third_party/blink/renderer/modules/webaudio/
  audio_buffer.cc/h

third_party/blink/renderer/modules/webgl/
  webgl_rendering_context_base.cc

third_party/blink/renderer/modules/peerconnection/
  rtc_peer_connection.cc

third_party/blink/renderer/modules/netinfo/
  network_information.cc

third_party/blink/renderer/core/events/
  navigator_events.cc

third_party/blink/renderer/modules/speech/
  speech_synthesis.cc

third_party/blink/renderer/modules/quota/
  storage_manager.cc

content/browser/renderer_host/
  render_process_host_impl.cc
content/browser/BUILD.gn

chrome/browser/
  renderer_preferences_util.cc, BUILD.gn

chrome/browser/net/
  profile_network_context_service.cc, BUILD.gn

chrome/browser/ui/webui/version/
  version_ui.cc

chrome/app/
  chrome_main_delegate.cc

build/config/unsafe_buffers_paths.txt
```
