# Kernel-R: Master Plan — Build Chromium Trực Tiếp

> Tài liệu hợp nhất từ 10 plan gốc. Ngày tạo: 2026-11-14.
> Máy build: **Xeon E5-2696v3 18C/36T, 64 GB RAM, Windows 10 LTSC 2019, ổ C trống 429 GB**.
> Trạng thái: **BẮT ĐẦU TỪ ZERO** — chưa cài gì, chưa checkout Chromium.

---

## 1. Tổng quan dự án

**Kernel-R** là một Chromium fork trong đó mỗi lần khởi chạy sinh ra một "máy tính ảo" hoàn chỉnh và nhất quán — OS, GPU, RAM, màn hình, font, ngôn ngữ, múi giờ — tất cả từ một seed ngẫu nhiên, tại tầng C++ của engine.

### Mục tiêu cốt lõi
| ID | Mục tiêu |
|----|----------|
| G1 | Một provider duy nhất (`FingerprintProfile`) là nguồn sự thật |
| G2 | Xác định: cùng seed ⇒ cùng đầu ra byte-for-byte |
| G3 | Nhất quán: mọi profile qua Validator trước khi dùng |
| G4 | Đa dạng: phân bố bám sát phần cứng thực tế |
| G5 | Không dấu vết JS (không defineProperty, không hook script) |
| G6 | Patch tối thiểu, tách module, rebase ≤ 1 ngày |
| G7 | Ephemeral (mặc định) và persistent mode |

### Phi mục tiêu (Phase 1)
- Phase 1: không giả OS khác họ Windows (Phase 2 dùng VM thật)

### Mục tiêu mở rộng (Phase 3+)
- **Né fingerprint detection tầng web** (hCaptcha, CreepJS, FingerprintJS, Cloudflare) — mục tiêu chính Phase 1
- **Giả attestation phần cứng** (TPM, Play Integrity) — Phase 3+, cần driver kernel-mode
- **Driver / kernel-level spoofing** (hardware ID, HWID, disk serial) — Phase 3+, cần WDM/KMDF driver

### Ràng buộc công cụ (QUAN TRỌNG)
- **KHÔNG dùng Playwright, Puppeteer, CDP, hoặc bất kỳ công cụ automation bên ngoài nào**
- Mọi tương tác trình duyệt qua **named pipe C++ nội bộ** (`kr_automation`)
- Harness test dùng **Python thuần + named pipe** (không qua DevTools protocol)
- Capture dữ liệu dùng **trang HTML tự viết** mở bằng chrome.exe, đọc kết quả qua file/pipe
- Lý do: CDP để lại `navigator.webdriver=true`, Playwright/Puppeteer để lại nhiều dấu vết phát hiện được

---

## 2. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 1: SINH PROFILE (Python — ngoài engine)                  │
│  seed (CSPRNG) → Generator + Corpus → Validator → profile.json │
│  tools/kr/ : generator, constraints, capture, calibrate        │
│  corpus/   : os, gpu, fonts, screens, locales (measured data)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ profile.json
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 2: BROWSER PROCESS (C++ — components/kr_fingerprint/)    │
│  ProfileLoader: đọc JSON, validate, hash SHA-256               │
│  ProfileValidator: kiểm quy tắc nội tại                       │
│  Truyền profile → renderer/GPU qua shared memory (D23)         │
│  DACL siết tiến trình chống đọc bộ nhớ (D24)                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ FingerprintProfile singleton
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 3: BLINK / RENDERER (C++ — blink/platform/kr_fingerprint)│
│  FingerprintProfile::Get() — singleton bất biến, thread-safe   │
│  DeterministicNoise: SipHash-2-4(seed, domain_tag, context)    │
│                                                                 │
│  NHÓM A (giá trị): Navigator, Screen, WorkerNavigator, UA/CH   │
│  NHÓM B (render):  Canvas2D (gamma/contrast), WebGL, WebAudio  │
│  NHÓM C (tài nguyên): Font enumeration/measurement             │
│  NHÓM D (mạng): WebRTC ICE/IP, TLS/H2 (thừa hưởng stock)     │
│  NHÓM E (mới): SpeechSynthesis, NetworkInfo, MediaFeatures,    │
│                 HeapLimit, StorageQuota, Permissions             │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 4: MẠNG & PROXY                                          │
│  kr-gateway (SOCKS5 cục bộ → upstream có auth)                 │
│  Tường lửa: chrome.exe chỉ nối 127.0.0.1:PORT                 │
│  Preflight: đo IP thoát → sinh locale/tz khớp địa lý          │
│  Pool: 1 IP ↔ 1 profile (SQLite + DPAPI)                      │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 5: AUTOMATION (C++ — chrome/browser/kr_automation/)      │
│  Named pipe JSON: goto, click, type, key, scroll, eval,        │
│  wait_for, screenshot, move, drag, frames, sleep               │
│  Named pipe JSON, isTrusted=true, không dùng công cụ bên ngoài │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 6: MANAGER UI (Python — http.server + HTML tĩnh)        │
│  127.0.0.1:7777 — Dashboard, Profile Editor, Proxies, Runs    │
│  Toggle bật/tắt từng nhóm fake (Screen, CPU, GPU, Canvas...)  │
│  3 chế độ: All Native / All Spoofed / Custom                  │
│  SQLite: profiles, proxies, leases, runs                       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 7: VM LAYER (Phase 2 — Hyper-V + GPU-P)                 │
│  Build chrome.exe 1 lần trên host → copy vào golden image     │
│  Mỗi profile = 1 VM sạch, identity theo seed                  │
│  Profile truyền qua hv_sock (mã hoá, không file, không TCP)   │
│  GPU-P → canvas native, mạng cô lập, reaper dọn dẹp           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Thông số kỹ thuật

### 3.1 Chromium ghim
- **Tag:** 158.0.8127.37 (stable Windows, 2026-10-29)
- **Đường dẫn:** `C:\src\chromium\src`
- **Build:** `out\Dev` (component, is_debug=false, dcheck_always_on=true)
- **Repo công cụ:** `C:\src\kernel-r\` (patches, tools, corpus, harness)

### 3.2 Profile Schema v1 (rút gọn)
```json
{
  "schema": 1,
  "seed": "hex32",
  "os": { "family": "windows", "version": "10.0.22631", "build": 22631,
          "arch": "x86_64", "ua_platform": "Windows", "platform_version": "15.0.0" },
  "browser": { "major": 0, "full": "0.0.0.0", "brands": [...] },
  "cpu": { "cores": 8, "device_memory_gb": 8 },   // ← ví dụ; cores ∈ {4..24}, device_memory ∈ {2,4,8}
  "screen": { "w": 1920, "h": 1080, "avail_w": 1920, "avail_h": 1040,
              "dpr": 1.0, "color_depth": 24 },     // ← avail_h = h - taskbar(40|48)
  "gpu": { "vendor": "...", "angle_renderer": "...", "webgl": {...},
           "webgpu": {...}, "tier": 2 },
  "fonts": { "installed": [...], "hidden": [...] },
  "font_render": { "gamma": 1.8, "contrast": 0.5 },
  "locale": { "languages": ["en-US","en"], "timezone": "America/New_York" },
  "net": { "tls_profile": "chrome_win", "h2_settings": {...},
           "connection": { "type": "wifi", "downlink": 10, "rtt": 50 } },
  "media": { "audioinput": 1, "audiooutput": 1, "videoinput": 1 },
  "noise": { "canvas": false, "audio": false, "webgl": false },
  "toggles": {
    "screen": true, "cpu_memory": true, "gpu_webgl": true,
    "canvas": true, "audio": true, "fonts": true,
    "locale_tz": true, "network": true, "voices": true,
    "permissions": true, "window_size": true
  },  // true=spoofed, false=native; preset: "all_native"/"all_spoofed"/"custom"
  "provenance": { "corpus_ids": [...], "confidence": "measured" }
}
```

### 3.3 Quyết định thiết kế chính

| ID | Quyết định | Đánh đổi |
|----|-----------|----------|
| D1 | Fork Chromium trực tiếp | Build nặng (~2-3h lần đầu trên Xeon 36T), rebase định kỳ |
| D2 | Một provider bất biến duy nhất | Phải truyền xuống mọi process |
| D3 | Phase 1 chỉ Windows 10/11 | macOS/Linux ở Phase 2 bằng VM thật |
| D4 | GPU tier ≤ tier máy chủ | Đa dạng GPU bị giới hạn |
| D5 | Generator Python ngoài engine | Hai nơi cùng chứa quy tắc → Validator C++ kiểm lại |
| D23 | Profile qua shared memory (không command line) | Không chống kernel-level |
| D24 | Siết DACL tiến trình Chrome | Crashpad không dump được |
| D27-D28 | Canvas: bỏ vùng phẳng, chỉ nhiễu viền khử răng cưa | Canvas đơn giản không đổi hash |
| D35 | Đa dạng canvas bằng gamma/contrast DirectWrite | Không drift, tự nhiên như máy khác ClearType |

---

## 4. Trạng thái & Roadmap (máy này — bắt đầu từ zero)

### Giai đoạn 0: Setup môi trường — ⬜ CHƯA LÀM

| Bước | Mô tả | Trạng thái |
|------|-------|-----------|
| S0 | Cài Visual Studio 2022 Build Tools + SDK | ⬜ |
| S1 | Cài depot_tools + Git + Python | ⬜ |
| S2 | Biến môi trường + Defender exclusion | ⬜ |
| S3 | Checkout Chromium 157 (~35-45 GB) | ⬜ |
| S4 | Cấu hình GN args | ⬜ |
| S5 | Build lần đầu (~2-3h với 36 thread) | ⬜ |
| S6 | Verify chrome.exe chạy được | ⬜ |

### Phase 1: Engine C++ — ⬜ CHƯA BẮT ĐẦU

| Task | Mô tả | Trạng thái |
|------|-------|-----------|
| T0 | Baseline build + test | ⬜ |
| T16 | Generator/corpus/capture (Python) | ⬜ |
| T1 | Switch + ProfileLoader | ⬜ |
| T2 | Validator C++ | ⬜ |
| T3 | FingerprintProfile singleton | ⬜ |
| T4 | DeterministicNoise (SipHash) | ⬜ |
| T5 | UA/Client Hints | ⬜ |
| T6 | Navigator/Screen | ⬜ |
| T7 | Timezone/Locale | ⬜ |
| T8 | Canvas 2D (gamma/contrast) | ⬜ |
| T9 | WebGL/WebGPU | ⬜ |
| T10 | WebAudio | ⬜ |
| T11 | Fonts | ⬜ |
| T12 | Ma trận ngữ cảnh | ⬜ |
| T13 | WebRTC | ⬜ |
| T14 | TLS/H2 ngang bằng stock | ⬜ |
| T15 | Chống rò rỉ cấu hình | ⬜ |
| T17 | Launcher + Manager | ⬜ |

**Mục tiêu:** 41 patch, 0 file `net/` hoặc `boringssl` bị chạm.

### HSW Gaps (hCaptcha fingerprint) — ⬜ SAU PHASE 1

| Task | Mô tả | Ưu tiên | Trạng thái |
|------|-------|---------|-----------|
| H1 | speechSynthesis.getVoices() | HIGH | ⬜ |
| H2 | navigator.connection | HIGH | ⬜ |
| H3 | CSS Media Feature queries | MEDIUM | ⬜ |
| H4 | performance.memory.jsHeapSizeLimit | MEDIUM | ⬜ |
| H5 | StorageManager.estimate() quota | MEDIUM | ⬜ |
| H6 | Permissions.query() states | MEDIUM | ⬜ |
| H7 | window.outerWidth/Height clamp | LOW | ⬜ |
| H8 | GOPD property descriptor integrity | HIGH | ⬜ |
| H9 | WASM timing vs hardwareConcurrency | HIGH | ⬜ |
| H10 | Function.prototype.toString native | MEDIUM | ⬜ |
| H11 | Brand check / TypeError | MEDIUM | ⬜ |

### Automation — ⬜ SAU PHASE 1

| Task | Mô tả | Trạng thái |
|------|-------|-----------|
| A1-A3 | Pipe + ops cơ bản + input | ⬜ |
| A4-A4b | Manager + song song | ⬜ |
| A5 | Không để lại dấu | ⬜ |
| A7 | So với chuột thật (SendInput) | ⬜ |
| A9 | Zoom khác 100% | ⬜ |
| A11 | Op move (nội suy Bézier + noise) | ⬜ |
| A12 | Op drag | ⬜ |
| A13 | SendMessage + HWND (input OS level thay ForwardMouseEvent) | ⬜ |
| A14 | kr-remote gateway (WebSocket + TLS + token auth) | ⬜ |
| A15 | kr-remote client SDK (Python) | ⬜ |

### Phase 2: VM Layer — ⬜ SAU PHASE 1 + AUTOMATION

| Task | Mô tả | Trạng thái |
|------|-------|-----------|
| V0 | Windows Sandbox pipeline (test nhanh) | ⬜ |
| V1.1 | Golden image Hyper-V (Windows + chrome.exe built từ host) | ⬜ |
| V1.2 | GPU-P passthrough (canvas native trong VM) | ⬜ |
| V1.3 | hv_sock: truyền profile host→VM (AES-256, không file/TCP) | ⬜ |
| V1.4 | Orchestrator (spin VM, gửi profile, nhận HWND, automation) | ⬜ |
| V1.5 | Mạng cô lập per-VM (mỗi VM 1 proxy) | ⬜ |
| V1.6 | Lifecycle + reaper (tắt VM, xoá diff disk) | ⬜ |

### Phase 3: Consistency — ⬜ SAU PHASE 2

| Task | Mô tả |
|------|-------|
| T20 | Định nghĩa "ổn" (danh sách API + nhãn) |
| T21 | Đối chứng với Chrome stock |
| T22 | Luật nhất quán chéo |
| T23 | Bề mặt API (toString, brand check) |
| T24 | Ngữ cảnh đầy đủ |
| T25 | Nguồn gốc dữ liệu (provenance) |
| T26 | Mạng khớp hồ sơ |
| T27 | Ổn định theo thời gian |
| T28 | Cổng hồi quy (`qa.ps1`) |
| T29 | VM layer tích hợp |

---

## 5. Hướng dẫn Build Chromium

### 5.1 Máy build hiện tại
- **OS:** Windows 10 Enterprise LTSC 2019 (build 18363)
- **CPU:** Intel Xeon E5-2696v3 — 18 core / 36 thread @ 2.30 GHz
- **RAM:** 64 GB
- **Ổ đĩa:** Ổ C trống **429 GB** (dư sức cho checkout + 2 thư mục build)
- **GPU:** NVIDIA GeForce GTX 1070 (8 GB VRAM) — GPU tier 2, corpus GPU đầu tiên
- **Lưu ý LTSC:** Không có Microsoft Store, winget có sẵn (v1.29)

### 5.2 Cài đặt (thứ tự chính xác)

**Bước S0: Visual Studio 2022 Build Tools** (PowerShell Admin)
```powershell
winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --add Microsoft.VisualStudio.Component.VC.ATL --add Microsoft.Component.VC.Runtime.UCRTSDK"
```
Sau khi cài, verify: mở "Developer PowerShell for VS 2022", gõ `cl.exe`.

**Bước S1: depot_tools + Git**
```powershell
# Tải depot_tools
Invoke-WebRequest -Uri "https://storage.googleapis.com/chrome-infra/depot_tools.zip" -OutFile "$env:TEMP\depot_tools.zip"
Expand-Archive "$env:TEMP\depot_tools.zip" -DestinationPath "C:\depot_tools" -Force

# Thêm vào PATH (system, đầu tiên)
$path = [Environment]::GetEnvironmentVariable("Path","Machine")
[Environment]::SetEnvironmentVariable("Path","C:\depot_tools;$path","Machine")

# Chạy gclient lần đầu để depot_tools tự cài Git + Python
# (mở shell MỚI sau khi set PATH)
gclient
```

**Bước S2: Biến môi trường + Defender** (PowerShell Admin)
```powershell
# Biến môi trường
[Environment]::SetEnvironmentVariable("DEPOT_TOOLS_WIN_TOOLCHAIN","0","Machine")
[Environment]::SetEnvironmentVariable("vs2022_install","C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools","Machine")

# Defender exclusion (giảm thời gian build đáng kể)
Add-MpPreference -ExclusionPath 'C:\src','C:\depot_tools'

# Git config (dùng Git của depot_tools)
git config --global core.autocrlf false
git config --global core.filemode false
git config --global branch.autosetuprebase always
git config --global core.longpaths true
```

**Bước S3: Checkout Chromium** (~35-45 GB, 1-3 giờ tuỳ mạng)
```powershell
mkdir C:\src\chromium; cd C:\src\chromium
fetch --nohooks --no-history chromium
cd src
git fetch --tags --depth=1 origin tag 158.0.8127.37
git checkout -b kr/base 158.0.8127.37
gclient sync -D --with_branch_heads --nohooks
gclient runhooks
```

**Bước S4: Cấu hình GN + Build** (~2-3 giờ lần đầu với 36 thread)
```powershell
cd C:\src\chromium\src
gn gen out\Dev
# Dán nội dung args vào editor mở ra (xem bên dưới), lưu, đóng
autoninja -C out\Dev chrome
```

**GN Args (`out\Dev\args.gn`):**
```gn
is_debug = false
is_component_build = true
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
enable_nacl = false
dcheck_always_on = true
is_clang = true
```

**Bước S5: Verify**
```powershell
# chrome.exe phải mở được
out\Dev\chrome.exe --no-first-run about:blank
```

**Bước S6: Áp patch Kernel-R** (sau khi viết patch)
```powershell
cd C:\src\chromium\src
git am --3way C:\src\kernel-r\patches\*.patch
autoninja -C out\Dev chrome
# Fix sandbox ACL (bắt buộc)
powershell C:\src\kernel-r\scripts\fix-sandbox-acl.ps1
```

### 5.5 Quy trình Patch
```
kernel-r/
  PINNED_VERSION          # "158.0.8127.37"
  patches/
    0001-add-kr-switches.patch
    0002-kr-profile-loader.patch
    ... (41 patch hiện tại)
  scripts/
    apply.ps1             # git am --3way
    export.ps1            # git format-patch kr/base..HEAD
    rebase.ps1            # nâng tag mới
    build.ps1             # autoninja wrapper
    fix-sandbox-acl.ps1   # quyền AppContainer
    fw-rules.ps1          # tường lửa
```

---

## 6. Chiến lược Test

### Kim tự tháp
| Tầng | Công cụ | Phạm vi |
|------|---------|---------|
| L1 | pytest (Python) | Schema, constraints, generator, phân bố |
| L2 | gtest (C++) | Loader, validator, noise, hook |
| L3 | Blink web_tests | JS API trong renderer |
| L4 | browser_tests | Khởi động, switch, reject |
| L5 | Harness tự viết (Python + named pipe kr_automation) | Ma trận ngữ cảnh, ổn định, đa dạng |
| L6 | TLS/H2 server cục bộ | ClientHello, SETTINGS |
| L7 | So sánh stock | Regression khi profile tắt |

### 10 tính chất cần chứng minh
| Mã | Tính chất | Cách kiểm |
|----|-----------|-----------|
| P1 | Xác định (cùng seed → cùng bundle) | 50 lần/seed, so hash |
| P2 | Đa dạng (khác seed → khác bundle) | 1000 seed, 0 va chạm |
| P3 | Nhất quán nội bộ (qua Validator) | 10,000 seed |
| P4 | Nhất quán ngữ cảnh (main=Worker=iframe) | Ma trận 11×9 |
| P5 | Ổn định trong phiên (1000 lần gọi) | Không đổi |
| P6 | Không dấu vết JS | Descriptor/toString/prototype = stock |
| P7 | Pass-through (tắt kr = stock) | So sánh byte |
| P8 | Không hồi quy hiển thị | Diff pixel = 0 |
| P9 | Không khai vượt năng lực | WebGL caps ≤ thật |
| P10 | Không rò rỉ thông tin thật | Quét IP/hostname/GPU |

---

## 7. Mạng & Proxy

### Luồng hoạt động
```
1. Chọn proxy từ pool (1 IP ↔ 1 profile)
2. Mở kr-gateway cục bộ (SOCKS5 không auth → upstream có auth)
3. Preflight: đo IP thoát, tra GeoIP cục bộ
4. Generator sinh locale/timezone khớp địa lý IP
5. Tường lửa: chrome.exe chỉ nối 127.0.0.1
6. Kill-switch: upstream chết → đóng cổng → mất mạng (không lộ IP)
```

### 12 kênh rò rỉ đã đóng
DNS, WebRTC/STUN, QUIC/HTTP3, IPv6, dịch vụ nền Chrome, địa lý không khớp, loại IP/ASN, độ trễ/TCP, danh tiếng IP, tái sử dụng IP, LAN host.

### TLS/H2 Parity (Verified)
- **JA3:** ext 0 first, 21 last, 14 middle shuffled (Chrome 110+)
- **H2:** `1:65536;2:0;3:1000;4:6291456;6:262144|15663105|0|m,s,a,p`
- **0 file net/ bị chạm** — thừa hưởng nguyên từ Chromium 157

---

## 8. Automation 2 tầng (không CDP/Playwright/Puppeteer)

### Kiến trúc

```
Manager (Python)
  │
  ├── TẦNG 1: Named Pipe (logic + DOM)
  │   pipe JSON ──► Chrome browser process (C++)
  │                  └── PipeServer (IO thread) → UI thread
  │                  └── goto, wait_for, eval, screenshot, frames
  │                  └── get_hwnd → trả HWND về Python
  │                  └── DOM via ExecuteJavaScriptInIsolatedWorld
  │
  └── TẦNG 2: SendMessage + HWND (input — OS level)
      Python ──SendMessage(hwnd, WM_*)──► OS ──► Chrome window
               └── WM_LBUTTONDOWN/UP     → click
               └── WM_MOUSEMOVE          → move (nội suy Bézier + noise)
               └── WM_KEYDOWN/UP         → type
               └── WM_MOUSEWHEEL         → scroll
               Không cần focus, song song N instance
```

**Tại sao 2 tầng:**
- **Tầng 1 (pipe):** Điều khiển logic bên trong Chrome — trang web không thấy pipe
- **Tầng 2 (SendMessage):** Input đi qua OS giống chuột/phím thật — `isTrusted=true`
- Mỗi Chrome instance trả HWND qua pipe riêng → không nhầm instance

**Pipe:** `\\.\pipe\kr-ctl-<run_id>-<token>`, DACL chỉ user hiện tại
- Không mở cổng TCP, không DevTools agent, không `--remote-debugging-port`

### Luồng hoạt động mỗi instance

```python
# 1. Khởi động Chrome với pipe riêng
pipe = connect("\\.\pipe\kr-ctl-run001-tokenA")

# 2. Lấy HWND từ Chrome
hwnd = pipe.send({"op": "get_hwnd"})["hwnd"]

# 3. Logic qua pipe
pipe.send({"op": "goto", "url": "https://example.com"})
pipe.send({"op": "wait_for", "selector": "#login"})

# 4. Input qua SendMessage + HWND (OS level)
import ctypes
user32 = ctypes.windll.user32
# Click tại (200, 300) — không cần focus
lparam = (300 << 16) | 200
user32.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

# 5. Screenshot qua pipe
img = pipe.send({"op": "screenshot"})
```

### Ops

| Op | Tầng | Mô tả |
|----|------|-------|
| `goto` | Pipe | Navigate URL |
| `wait_for` | Pipe | Đợi selector/condition |
| `eval` | Pipe | JS trong isolated world |
| `screenshot` | Pipe | Capture tab |
| `frames` | Pipe | Chuyển iframe |
| `get_hwnd` | Pipe | Trả HWND cho Python |
| `click` | SendMessage | WM_LBUTTONDOWN/UP → OS → Chrome |
| `type` | SendMessage | WM_KEYDOWN/UP per key |
| `move` | SendMessage | WM_MOUSEMOVE + nội suy Bézier + noise |
| `scroll` | SendMessage | WM_MOUSEWHEEL |
| `drag` | SendMessage | MOVE → DOWN → MOVE... → UP |

### Đặc điểm
- `isTrusted = true` — input qua OS, giống chuột/phím thật
- `navigator.webdriver = false` — không dùng DevTools
- Không cổng TCP, không CDP, không Playwright, không Puppeteer
- **Song song:** mỗi instance có HWND riêng, SendMessage không cần focus
- **Mượt:** N instance chạy cùng lúc, không conflict
- Zoom: hỗ trợ 83%-144%

### Giống người thật
- **Move:** Nội suy Bézier curve, thêm jitter noise, tốc độ thay đổi (nhanh giữa, chậm đầu/cuối)
- **Click:** Random delay 50-150ms giữa down/up
- **Type:** Random delay 80-200ms giữa phím, typo + backspace ngẫu nhiên
- **Scroll:** Nhiều bước nhỏ thay vì 1 bước lớn

### Giới hạn đã biết
- OOPIF (iframe khác origin): chưa hỗ trợ input
- Isolated world only (không đọc biến JS của trang)
- SendMessage: toạ độ là client-area relative, cần tính offset

### Phase 3+: Virtual HID Driver
Nếu SendMessage bị detect → nâng lên kernel driver:
- Tạo N virtual mouse/keyboard device (KMDF)
- OS thấy là USB HID thật → không phân biệt được
- Bind mỗi device vào 1 Chrome window

---

## 8b. kr-remote Gateway (điều khiển từ xa — thay thế CDP)

### Kiến trúc
```
Client (Python, bất kỳ máy nào)
  │
  │  wss://host:9800?token=<random>   (1 cổng duy nhất)
  │  TLS + token auth + IP whitelist
  │
  ▼
kr-gateway (process riêng trên host/VM)
  │
  ├── Route theo instance ID
  │   ├── "run001" → pipe #1 + HWND #1
  │   ├── "run002" → pipe #2 + HWND #2
  │   └── "run003" → pipe #3 + HWND #3
  │
  ├── Logic ops → named pipe → Chrome
  │   (goto, wait_for, eval, screenshot, frames)
  │
  └── Input ops → SendMessage(HWND) → OS → Chrome
      (click, type, move, scroll, drag)
```

### Protocol (JSON qua WebSocket)
```json
// Request
{"id": 1, "instance": "run001", "op": "goto", "url": "https://example.com"}
{"id": 2, "instance": "run001", "op": "click", "x": 200, "y": 300}
{"id": 3, "instance": "run002", "op": "screenshot"}

// Response
{"id": 1, "ok": true}
{"id": 2, "ok": true}
{"id": 3, "ok": true, "data": "base64png..."}

// Management
{"id": 0, "op": "list"}
→ {"id": 0, "instances": [
    {"id": "run001", "hwnd": "0xA0B2C", "profile": "seed_xxx", "status": "running"},
    {"id": "run002", "hwnd": "0xD0E3F", "profile": "seed_yyy", "status": "running"}
  ]}
```

### Bảo mật (không giống CDP)
| | CDP | kr-remote |
|---|---|---|
| Protocol | DevTools Protocol (public) | Custom JSON (riêng) |
| Auth | Không có | Token + TLS + IP whitelist |
| Port | `--remote-debugging-port` (Chrome mở) | kr-gateway (process riêng, Chrome không biết) |
| Detect | `navigator.webdriver=true`, CDP binding | Không dấu vết — Chrome chỉ thấy pipe + SendMessage |
| Input | `isTrusted=false` | `isTrusted=true` |

### Ops
| Op | Loại | Mô tả |
|----|------|-------|
| `list` | Management | Liệt kê instances đang chạy |
| `launch` | Management | Khởi động Chrome mới với profile |
| `kill` | Management | Tắt instance |
| `goto` | Logic (pipe) | Navigate URL |
| `wait_for` | Logic (pipe) | Đợi selector/condition |
| `eval` | Logic (pipe) | JS trong isolated world |
| `screenshot` | Logic (pipe) | Capture tab → base64 PNG |
| `frames` | Logic (pipe) | Chuyển iframe |
| `click` | Input (HWND) | SendMessage WM_LBUTTONDOWN/UP |
| `type` | Input (HWND) | SendMessage WM_KEYDOWN/UP |
| `move` | Input (HWND) | WM_MOUSEMOVE + Bézier + noise |
| `scroll` | Input (HWND) | WM_MOUSEWHEEL |
| `drag` | Input (HWND) | MOVE → DOWN → MOVE... → UP |

### Client SDK (Python)
```python
from kr_remote import KRRemote

gw = KRRemote("wss://10.0.0.1:9800", token="abc123")

# Liệt kê
instances = gw.list()

# Khởi động browser mới
browser = gw.launch(profile="profiles/seed_xxx.json", proxy="socks5://...")

# Điều khiển
browser.goto("https://example.com")
browser.wait_for("#login")
browser.click(200, 300)
browser.type("username")
img = browser.screenshot()

# Tắt
browser.kill()
```

---

## 9. Rủi ro & Giảm thiểu

| ID | Rủi ro | Giảm thiểu |
|----|--------|-----------|
| R1 | GPU thật ≠ thông số khai báo | D4 (tier clamp) + calibrate; GPU máy = GTX 1070 (tier 2) |
| R2 | Sót ngữ cảnh (Worker, SW) | Ma trận test tự động |
| R4 | Chromium đổi API khi nâng ver | Ghim tag, CI rebase hàng tháng |
| R11 | **MỚI:** Win10 LTSC 2019 (18363) thiếu API mới | Chromium 157 có thể cần Win10 21H2+; verify sau checkout |
| R6 | ~~Ổ C sát giới hạn~~ **GIẢI QUYẾT** | 429 GB trống, dư cho 2 thư mục out |
| R9 | WASM timing vs cores | cores ≥ max(realCores-4, 4) |
| R10 | GOPD/toString/brand-check | Hook ở IDL level, verify harness |

---

## 10. Việc cần làm tiếp (ưu tiên — bắt đầu từ zero)

### Ngay bây giờ: Setup môi trường
1. **S0** — Cài VS 2022 Build Tools + Windows SDK
2. **S1** — Cài depot_tools, Git, Python
3. **S2** — Biến môi trường + Defender exclusion
4. **S3** — Checkout Chromium 157 source (~35-45 GB)
5. **S4** — Cấu hình GN args
6. **S5** — Build lần đầu (ước tính ~2-3h)
7. **S6** — Verify chrome.exe chạy được

### Sau khi build thành công: Phase 1
8. **T0** — Baseline build + test results
9. **T16** — Generator Python + corpus (thu thập GPU máy này)
10. **T1→T17** — Viết 41 patch C++ theo thứ tự

### Sau Phase 1
11. **H1-H11** — HSW fingerprint gaps
12. **A1-A12** — Automation (named pipe C++ nội bộ, không CDP/Playwright/Puppeteer)
13. **Phase 2** — VM layer (Hyper-V)
14. **Phase 3** — Consistency + regression gate

---

## 11. THAM SỐ CẦN FAKE — BẢNG ĐẦY ĐỦ

> Mục tiêu: browser phải tạo ra fingerprint trông giống máy thật ở MỌI API mà hCaptcha probe.
> Chưa tính HSW/HSJ — chỉ tập trung môi trường JS + network.

### 11.1 Event ID Map (từ static_fp.json thực tế)

hCaptcha HSW thu thập fingerprint qua ~50 event IDs (hash CRC32 của tên check). Dưới đây là các event đã giải mã:

| Event ID | Tên check | Format trả về | Nhóm |
|----------|-----------|---------------|------|
| `1000750690` | **Screen properties** | `[w, h, availW, availH, colorDepth, pixelDepth, isExtended, maxTouchPoints, dpr, availW2, availH2, hasSessionStorage, hasLocalStorage, hasIndexedDB, hasTouch]` | Screen |
| `504458258` | **Navigator core** | `[appVersion, userAgent, hwConcurrency, deviceMemory, language, languages, platform, null, brands[], mobile, platformName, pluginsCount, mimeTypesCount, cookieEnabled, pdfViewerEnabled, maxTouchPoints, webdriver, doNotTrack, keyboard, darkMode]` | Navigator |
| `1866465638` | **WebGL vendor+renderer** | `["Google Inc. (NVIDIA)", "ANGLE (NVIDIA, ... Direct3D11 ...)"]` | GPU |
| `2189040541` | **UA-CH high entropy** | `[platform, platformVersion, null, bitness, arch, fullVersion]` | UA-CH |
| `3486023461` | **Timezone** | `[tzName, offset, offset, tzTransition, tzDisplayName, locale]` | Locale |
| `1755893731` | **SpeechSynthesis voices** | `[[default, lang, localService, name, voiceURI], ...]` | Media |
| `2737207841` | **Canvas + Font metrics** | `[[pixel_r, [r,g,b,a,...]], [[fontMeasurements...], [...]], [fontIndices], [layout]]` | Canvas/Font |
| `3962939203` | **Canvas path** | `[15 float values từ arc/bezier rendering]` | Canvas |
| `1145363943` | **WebGL params A** | `[maxTexSize, maxCubeMap, maxTexImageUnits, maxVertexAttribs, maxVertexUniformVecs, maxFragUniformVecs, [aliasedLineWidth, aliasedPointSize...]]` | GPU |
| `3865101243` | **WebGL params B** | `[maxRenderBuf, maxVaryingVecs, maxVertexTexImageUnits, stencilBits, maxSamples]` | GPU |
| `2387740133` | **WebGL params C** | `[max3dTexSize, maxArrayTexLayers, maxTexLODBias, maxUniformBufBindings, maxDrawBuffers, uniformBufOffsetAlign]` | GPU |
| `3911512191` | **WebGL params D** | `[maxCombinedTexImageUnits, max3dTexSize, maxColorAttachments, maxTexSize, maxTexImageUnits, maxFragUniformVecs, maxVertexUniformVecs, maxFragUniformComponents, [aliased...]]` | GPU |
| `3554363111` | **WebGL extensions** | `[index_list]` — indices vào danh sách extensions đã biết | GPU |
| `58508894` | **Memory/Storage** | `[jsHeapSizeLimit, totalJSHeapSize, null, null, storageQuota, hasSharedArrayBuffer, hasWasm, hasWebGL2, null]` | Memory |
| `1075205395` | **Chrome detection** | `[[chrome.app_keys], toString_length, property_count, null, booleans..., [inv_unique_keys], [], [pluginCount], hasNotif]` | Environment |
| `462289253` | **Performance hash** | `"57"` — hash của performance.timing layout | Timing |
| `1369899379` | **Font metric hash** | `"702"` — hash tổng hợp font measurement | Font |
| `2402750047` | **Canvas hash** | `"18437843324563249497"` — uint64 hash canvas toDataURL | Canvas |
| `317671698` | **Audio hash** | `"2337666753322697468"` — OfflineAudioContext output hash | Audio |
| `3405509837` | **WebRTC hash** | `"8022061930804573802"` — RTCPeerConnection ICE candidate hash | Network |
| `4181015304` | **Combined FP hash** | `"2545642147239152397"` — tổng hợp mọi fingerprint | Combined |
| `562823142` | **Font list hash** | `"16927405672252548354"` — hash danh sách font installed | Font |
| `2539159609` | **Plugin hash** | `"16373752545305569922"` — hash plugin enumeration | Environment |
| `3931073091` | **MimeType hash** | `"9345374751420407194"` — hash mimeType list | Environment |
| `2075394470` | **Property hash** | `"4932383211497360507"` — hash GOPD trên 108+ properties | Environment |
| `2935681427` | **WebGL precision** | `[4294967295, 4294967295, 4294967295, 4294967295]` — shader precision format | GPU |
| `359759834` | **WebGL int ranges** | `[2147483647, 2147483647, 4294967294]` — MAX_VERTEX/FRAGMENT uniform components | GPU |
| `1728464210` | **DOM layout hash** | `"8473551219770411651"` — getBoundingClientRect hash | DOM |
| `3923352168` | **CSS media hash** | `"756874611071873095"` — matchMedia queries hash | CSS |
| `3320102372` | **Error stack hash** | `"8305537109116106199"` — Error().stack format hash | V8 |
| `1181016567` | **Timezone string** | `"America/Los_Angeles"` | Locale |
| `1267668072` | **Keyboard layout** | `"15824750800881862533"` — keyboard.getLayoutMap hash | Input |
| `2054986590` | **Performance.now** | `"1775263649984.2"` — precision test | Timing |
| `2556820389` | **Window geometry** | `[scrollX, screenTop, screenLeft]` | Screen |
| `2671296585` | **Battery hash** | `"17433560312272931053"` | Power |
| `2426461220` | **Connection hash** | `"1219"` — NetworkInformation.downlink+rtt+effectiveType | Network |
| `772896908` | **Touch points** | `[maxTouchPoints]` | Input |
| `3055761315` | **WebGL2 params** | `[colorDepth, pixelDepth, maxTextureSize, maxRenderbufferSize, maxViewportDims]` | GPU |
| `4181739560` | **Performance entries** | `[[resource timing hashes], hasPerformanceObserver]` | Timing |
| `3357624742` | **Network timing** | `[[resource_type:host, start, end], ...]` | Timing |
| `559251292` | **Webdriver check** | `"false"` | Environment |

**Unique/Inv keys (window enumeration):**
| Field | Ý nghĩa |
|-------|---------|
| `unique_keys` | Các property TỒN TẠI trên `window` mà Chrome stock KHÔNG có — đến từ site JS (React, Sentry, hcaptcha, etc.) |
| `inv_unique_keys` | Các property Chrome stock CÓ nhưng site KHÔNG thấy — HSW inject `_sharedLibs`, `hsj`, `__wdata` |
| `common_keys_hash` | CRC32 hash của danh sách `window` properties chung cho Chrome |
| `common_keys_tail` | 50 property cuối trong enum order — phát hiện fake nếu thứ tự sai |

### 11.2 Thuật toán sinh từng nhóm tham số

#### NHÓM A: Screen + Window (Event 1000750690, 2556820389)

**Tham số:**
```
screen.width, screen.height, screen.availWidth, screen.availHeight,
screen.colorDepth, screen.pixelDepth, screen.isExtended,
window.innerWidth, window.innerHeight, window.outerWidth, window.outerHeight,
window.screenX, window.screenY, window.devicePixelRatio
```

**Thuật toán:**
```python
REAL_SCREENS = [
    # (width, height, dpr) — từ StatCounter + Steam Hardware Survey
    (1920, 1080, 1.0),   # 23%
    (2560, 1440, 1.0),   # 9%
    (1366, 768,  1.0),   # 8%
    (1536, 864,  1.25),  # 7%
    (1920, 1080, 1.25),  # 5%
    (3840, 2160, 1.5),   # 4%
    (1440, 900,  1.0),   # 3%
    (2560, 1440, 1.25),  # 2%
    (1680, 1050, 1.0),   # 2%
    (3840, 2160, 2.0),   # 2%
]

def gen_screen(rng):
    w, h, dpr = rng.weighted_choice(REAL_SCREENS, weights)

    # availHeight = height - taskbar (Windows)
    taskbar = rng.choice([40, 48])  # Win10=40px, Win11=48px (ở 100% DPI)
    avail_h = h - taskbar
    avail_w = w  # taskbar dọc rất hiếm

    # colorDepth: 24 (SDR), 30 (HDR), 32 (legacy)
    color_depth = 24
    if dpr >= 1.5: color_depth = rng.choice([24, 30])  # 4K hay dùng HDR

    # innerWidth: phụ thuộc scrollbar + window chrome
    scrollbar_w = rng.choice([0, 15, 17])  # 0=overlay, 15/17=classic
    inner_w = int(w / dpr) - scrollbar_w
    # innerHeight: trừ tab bar + address bar + bookmark bar
    chrome_h = rng.choice([74, 102])  # 74=tab+toolbar, 102=+bookmark bar (ở 100% DPI)
    inner_h = int(h / dpr) - int(taskbar / dpr) - chrome_h

    return {
        "w": w, "h": h, "avail_w": avail_w, "avail_h": avail_h,
        "color_depth": color_depth, "pixel_depth": color_depth,
        "dpr": dpr, "inner_w": inner_w, "inner_h": inner_h,
        "outer_w": int(w / dpr), "outer_h": int(avail_h / dpr),
        "is_extended": False,  # multi-monitor = rare
    }
```

**Quy tắc nhất quán:**
- `availHeight = height - taskbar_height`
- `innerWidth < outerWidth <= screen.width / dpr`
- `innerHeight < outerHeight <= screen.availHeight / dpr`
- `pixelDepth == colorDepth` (luôn bằng nhau trên Windows)
- `isExtended = false` (phase 1, đơn màn hình)
- `dpr` phải khớp với resolution: 1536×864 → dpr=1.25, 3840×2160 → dpr=1.5 hoặc 2.0

#### NHÓM B: Navigator (Event 504458258)

**Tham số:**
```
navigator.hardwareConcurrency, navigator.deviceMemory,
navigator.platform, navigator.language, navigator.languages,
navigator.userAgent, navigator.appVersion,
navigator.maxTouchPoints, navigator.webdriver,
navigator.cookieEnabled, navigator.pdfViewerEnabled,
navigator.doNotTrack, navigator.plugins.length
```

**Thuật toán:**
```python
CPU_MEM_COMBOS = [
    # (cores, memory_gb) — realistic combos
    (4,  4),  (4,  8),   # Laptop cũ
    (6,  8),  (6,  16),  # Mid-range
    (8,  8),  (8,  16),  (8,  32),  # Gaming/workstation
    (12, 16), (12, 32),  # High-end
    (16, 16), (16, 32), (16, 64),  # Enthusiast
    (20, 32), (24, 32), (24, 64),  # Workstation
]

def gen_navigator(rng, os_info, chrome_ver):
    cores, mem = rng.choice(CPU_MEM_COMBOS)

    # deviceMemory: Chrome rounds xuống power of 2, max 8
    device_memory = min(8, 2 ** int(math.log2(mem)))

    # Platform: phải khớp OS
    platform = "Win32"  # Phase 1 chỉ Windows

    # Plugins: Chrome luôn có 5 PDF plugins
    plugins_count = 5
    mime_types_count = 2

    # webdriver: PHẢI false
    # doNotTrack: null hoặc "1"
    # maxTouchPoints: 0 (desktop), 10 (touch laptop)
    touch = rng.choice([0, 0, 0, 0, 10])  # 80% desktop

    return {
        "cores": cores, "device_memory": device_memory,
        "platform": platform,
        "language": "en-US",  # khớp geo IP
        "languages": ["en-US", "en"],
        "max_touch_points": touch,
        "webdriver": False,
        "cookie_enabled": True,
        "pdf_viewer_enabled": True,
        "do_not_track": rng.choice([None, "1"]),
        "plugins_count": plugins_count,
    }
```

**Quy tắc nhất quán:**
- `deviceMemory ∈ {0.25, 0.5, 1, 2, 4, 8}` — Chrome clamp
- `hardwareConcurrency` phải hợp lý: 4,6,8,10,12,16,20,24,32 — KHÔNG phải số lẻ
- Nếu `deviceMemory=4` thì `cores ∈ {4,6,8}` — không có máy 4GB RAM 24 cores
- `plugins.length = 5` và `mimeTypes.length = 2` (Chrome PDF viewer)
- `platform = "Win32"` cho CẢ Win32 và Win64 (Chrome luôn trả "Win32")

#### NHÓM C: UA-CH (Event 2189040541)

**Tham số:**
```
navigator.userAgentData.brands, .mobile, .platform,
.platformVersion, .architecture, .bitness, .fullVersionList,
.model, .wow64
```

**Thuật toán:**
```python
def gen_uach(rng, chrome_major, chrome_full):
    # Brands: PHẢI có 3 entries, thứ tự shuffle
    # "Not-A.Brand" hoặc "Not_A Brand" tuỳ Chrome version
    # ⚠ Formula dưới đây cần VERIFY cho Chrome 157 — brand string thay đổi giữa versions
    not_a_brand_ver = str(8 + (chrome_major % 20))  # → "25" cho Chrome 157, CẦN XÁC NHẬN
    brands = [
        {"brand": "Chromium", "version": str(chrome_major)},
        {"brand": "Google Chrome", "version": str(chrome_major)},
        {"brand": f"Not-A.Brand", "version": not_a_brand_ver},
    ]
    rng.shuffle(brands)  # Chrome shuffle thứ tự mỗi session

    # fullVersionList: giống brands nhưng dùng full version
    full_brands = [
        {"brand": "Chromium", "version": chrome_full},
        {"brand": "Google Chrome", "version": chrome_full},
        {"brand": f"Not-A.Brand", "version": f"{not_a_brand_ver}.0.0.0"},
    ]

    return {
        "brands": brands,
        "full_version_list": full_brands,
        "mobile": False,
        "platform": "Windows",
        "platform_version": rng.choice(["10.0.0", "13.0.0", "14.0.0", "15.0.0"]),
        # 10.0.0 = Win10 21H2+, 13.0.0 = Win11 21H2, 14.0.0 = Win11 22H2, 15.0.0 = Win11 23H2
        # ⚠ CẦN VERIFY: chạy Chrome 157 trên Win10/11, đo navigator.userAgentData.platformVersion
        "architecture": "x86",
        "bitness": "64",
        "model": "",
        "wow64": False,
    }
```

**Quy tắc nhất quán:**
- `brands` PHẢI có **3 entries** (Chromium, Google Chrome, Not-A.Brand)
- `sec-ch-ua` header PHẢI khớp `navigator.userAgentData.brands`
- `platform` trong UA-CH = `"Windows"` (không phải `"Win32"`)
- `platformVersion "15.0.0"` = Windows 11 → UA phải là `Windows NT 10.0` (Chrome không phân biệt)
- `Not-A.Brand` version: ⚠ CẦN VERIFY cho Chrome 157 — formula thay đổi giữa các version

#### NHÓM D: GPU / WebGL (Events 1866465638, 1145363943, 3865101243, 2387740133, 3911512191, 3554363111, 2935681427, 359759834)

**Tham số (~40 WebGL parameters):**
```
UNMASKED_VENDOR_WEBGL, UNMASKED_RENDERER_WEBGL,
MAX_TEXTURE_SIZE, MAX_CUBE_MAP_TEXTURE_SIZE,
MAX_TEXTURE_IMAGE_UNITS, MAX_VERTEX_ATTRIBS,
MAX_VERTEX_UNIFORM_VECTORS, MAX_FRAGMENT_UNIFORM_VECTORS,
MAX_RENDERBUFFER_SIZE, MAX_VARYING_VECTORS,
MAX_VERTEX_TEXTURE_IMAGE_UNITS, STENCIL_BITS,
MAX_SAMPLES, ALIASED_LINE_WIDTH_RANGE, ALIASED_POINT_SIZE_RANGE,
MAX_3D_TEXTURE_SIZE, MAX_ARRAY_TEXTURE_LAYERS,
MAX_UNIFORM_BUFFER_BINDINGS, MAX_DRAW_BUFFERS,
WebGL extensions list (30+ extensions)
Shader precision formats (4 values)
```

**Thuật toán: GPU Database (CORPUS — phải đo thật)**

Mỗi GPU là một **bộ dữ liệu đo thật** — KHÔNG random từng parameter riêng:

```python
# ⚠ GPU_DB HIỆN TRỐNG — cần đo thật bằng trang capture HTML
# GPU đầu tiên sẽ đo: GTX 1070 (máy build hiện tại)
# Mở rộng: nhờ người khác chạy trang capture, hoặc dùng GPU-P trong VM
#
# FORMAT mỗi entry (ví dụ placeholder — KHÔNG dùng cho production):
GPU_DB = [
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "params": {
            # TẤT CẢ giá trị dưới đây là PLACEHOLDER — thay bằng gl.getParameter() thật
            "MAX_TEXTURE_SIZE": 16384,
            "MAX_CUBE_MAP_TEXTURE_SIZE": 16384,
            "MAX_TEXTURE_IMAGE_UNITS": 32,
            "MAX_VERTEX_ATTRIBS": 16,
            "MAX_VERTEX_UNIFORM_VECTORS": 4096,
            "MAX_FRAGMENT_UNIFORM_VECTORS": 4096,
            "MAX_RENDERBUFFER_SIZE": 16384,
            "MAX_VARYING_VECTORS": 32,
            "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 32,
            "MAX_SAMPLES": 8,
            "STENCIL_BITS": 8,
            "MAX_3D_TEXTURE_SIZE": 16384,
            "MAX_DRAW_BUFFERS": 8,
            "MAX_UNIFORM_BUFFER_BINDINGS": 72,
            "ALIASED_LINE_WIDTH_RANGE": [1, 1],
            "ALIASED_POINT_SIZE_RANGE": [1, 1024],
        },
        "extensions": [],  # ĐO THẬT: gl.getSupportedExtensions()
        "precision": [],    # ĐO THẬT: gl.getShaderPrecisionFormat()
    },
    # Mục tiêu: 50+ GPUs — thu thập dần qua crowdsource hoặc VM GPU-P
    # Hiện có: 0 (đo GTX 1070 là task T16 đầu tiên)
]
```

**Cách thu thập GPU data (corpus):**
1. Chạy trang test HTML trên nhiều máy thật (hoặc VM với GPU-P)
2. Trang gọi `gl.getParameter()` cho MỌI enum, export JSON
3. Mỗi GPU unique = 1 entry trong database
4. **KHÔNG bao giờ mix parameter từ GPU khác nhau**

**Quy tắc nhất quán:**
- GPU renderer PHẢI chứa `Direct3D11` trên Windows
- `ANGLE (vendor, card Direct3D11 vs_5_0 ps_5_0, D3D11)` — format cố định
- Vendor = `Google Inc. (NVIDIA)` hoặc `Google Inc. (AMD)` hoặc `Google Inc. (Intel)`
- MAX_TEXTURE_SIZE thường = 16384 (NVIDIA/AMD) hoặc 8192 (Intel cũ)
- Extensions: **chỉ dùng bộ đo thật** — thêm/bớt = phát hiện

#### NHÓM E: Canvas (Events 2737207841, 3962939203, 2402750047)

**Tham số:**
- Canvas 2D `toDataURL()` hash (pixel-level fingerprint)
- Canvas path rendering (15 float values từ arc/bezier)
- Font measurement arrays

**2 chế độ Canvas:**

```
CHẾ ĐỘ 1: NATIVE (mặc định khi chạy trên máy thật / VM có GPU-P)
─────────────────────────────────────────────────────────────────
- Không fake gì — dùng canvas gốc từ GPU + driver thật của máy
- Canvas hash = hash thật của máy đang chạy
- Ưu điểm: 100% tự nhiên, không thể detect
- Nhược điểm: mọi instance trên cùng máy có cùng canvas hash
- Dùng khi: mỗi instance chạy trên VM riêng (Hyper-V GPU-P), 
  hoặc khi chỉ cần 1 identity per machine

CHẾ ĐỘ 2: SPOOFED (khi cần nhiều identity trên cùng 1 máy)
─────────────────────────────────────────────────────────────────
- Thay đổi ClearType gamma/contrast per profile → canvas hash khác
- Dùng DirectWrite API: IDWriteRenderingParams::GetGamma(), GetEnhancedContrast()
- gamma ∈ [1.4, 2.2] step 0.1, contrast ∈ [0.0, 1.0] step 0.1
- KHÔNG inject pixel noise (bị detect qua statistical analysis)
- GPU khác nhau + gamma/contrast khác nhau → canvas hash tự nhiên khác nhau
- Ưu điểm: 99 variations per GPU trên cùng máy
- Nhược điểm: hash khác máy thật nếu so sánh chéo

Chọn trong profile.json:
  "canvas_mode": "native"   // chế độ 1
  "canvas_mode": "spoofed"  // chế độ 2, dùng gamma/contrast từ profile
```

```
Canvas hash phụ thuộc vào:
1. GPU driver (ANGLE backend) → khác nhau giữa NVIDIA/AMD/Intel
2. Font rendering (ClearType settings: gamma, contrast)
3. Anti-aliasing implementation
```

**Canvas path values (Event 3962939203):**
```
15 floats từ: ctx.arc(), ctx.bezierCurveTo(), ctx.quadraticCurveTo()
Giá trị phụ thuộc GPU + driver version → tự khác khi GPU khác
Ví dụ: [-6.17284, -20.71068, 120.71069, ...] (NVIDIA)
        [-6.17284, -20.71068, 120.71068, ...] (AMD — khác ở decimal cuối!)
```

**Quy tắc:** Canvas hash phải ỔN ĐỊNH (cùng profile → cùng hash mọi lần gọi). Deterministic = G2.

#### NHÓM F: Audio (Event 317671698)

**Tham số:**
- `OfflineAudioContext` output hash

**Thuật toán:**
```
Audio fingerprint phụ thuộc:
1. Audio driver / DAC hardware
2. OS audio subsystem (Windows Audio Session API)
3. Floating-point implementation trong V8/Blink

Chiến lược:
- Không override — Chrome stock + GPU khác nhau đã tạo audio hash khác nhau
- Nếu cần thêm đa dạng: inject tiny float bias vào OscillatorNode frequency
  bias = SipHash(seed, "audio") % 1e-10
  Đủ nhỏ để không nghe thấy, đủ lớn để thay đổi hash
```

#### NHÓM G: Font (Events 562823142, 1369899379, 2737207841)

**Tham số:**
- Danh sách font installed (hash)
- Font metric measurements (offsetWidth/Height per test string per font)
- Font metric hash tổng hợp

**Thuật toán:**
```python
# Windows font sets thực tế (đo từ nhiều máy)
FONT_SETS = [
    # Base Windows 10 (mọi máy đều có)
    {"Arial", "Calibri", "Cambria", "Consolas", "Courier New",
     "Georgia", "Impact", "Segoe UI", "Tahoma", "Times New Roman",
     "Trebuchet MS", "Verdana", ...},

    # + Office installed
    {... base ..., "Bookman Old Style", "Century Gothic",
     "Garamond", "Palatino Linotype", ...},

    # + Adobe installed
    {... base ..., "Myriad Pro", "Minion Pro", ...},
]

def gen_fonts(rng, os_info):
    base = FONT_SETS[0]
    # 70% chỉ có base, 25% có Office, 5% có Adobe
    extra = rng.weighted_choice([set(), FONT_SETS[1]-base, FONT_SETS[2]-base])
    installed = base | extra

    # Font metrics: ĐO THẬT trên Chrome stock với từng font set
    # Lưu vào corpus/fonts/metrics_{font_hash}.json
    # Generator chọn bộ metrics khớp với font set đã chọn
    return {"installed": sorted(installed), "metrics_id": hash(frozenset(installed))}
```

**Quy tắc:**
- Font list phải LÀ SUBSET của font thật trên Windows (không có font không tồn tại)
- Font metrics phải KHỚP CHÍNH XÁC với Chrome stock rendering font đó
- `fonts.hidden` = fonts CÓ trên máy nhưng profile giả vờ KHÔNG có → để tạo đa dạng

#### NHÓM H: Timezone / Locale (Events 3486023461, 1181016567)

**Tham số:**
```
Intl.DateTimeFormat().resolvedOptions().timeZone,
Date.getTimezoneOffset(),
Intl.DateTimeFormat display name,
navigator.language, navigator.languages
```

**Thuật toán:**
```python
# Chỉ hỗ trợ 2 locale: en-US và vi-VN
LOCALE_MAP = {
    "US": {
        "timezones": ["America/New_York", "America/Chicago", "America/Denver",
                      "America/Los_Angeles", "America/Phoenix"],
        "lang": "en-US",
        "languages": ["en-US", "en"],
    },
    "VN": {
        "timezones": ["Asia/Ho_Chi_Minh"],
        "lang": "vi-VN",
        "languages": ["vi-VN", "vi", "en-US", "en"],
    },
}

def gen_locale(rng, proxy_country):
    locale = LOCALE_MAP[proxy_country]  # chỉ "US" hoặc "VN"
    tz = rng.choice(locale["timezones"])

    # Offset phải khớp timezone (tính từ DST rules)
    offset = get_utc_offset(tz, datetime.now())  # ví dụ: -300 cho EST

    lang = locale["lang"]
    languages = locale["languages"]

    # Timezone display name phải khớp OS locale
    # Windows: "Pacific Standard Time" / "Pacific Daylight Time"
    display_name = get_windows_tz_name(tz)

    return {
        "timezone": tz, "offset": offset,
        "display_name": display_name,
        "language": lang, "languages": languages,
    }
```

**Quy tắc:**
- Timezone PHẢI khớp IP geolocation (IP US + timezone Asia = BỊ DETECT ngay)
- `Date.getTimezoneOffset()` PHẢI đúng offset cho timezone đó
- Display name phải là Windows format (không phải Linux/Mac format)

#### NHÓM I: SpeechSynthesis (Event 1755893731 — HSW Gap H1)

**Tham số:**
```
speechSynthesis.getVoices() → [{default, lang, localService, name, voiceURI}, ...]
```

**Thuật toán:**
```python
# Windows 10/11 voices (đo thật)
WIN10_VOICES = [
    (True,  "en-US", True, "Microsoft David - English (United States)"),
    (False, "en-US", True, "Microsoft Mark - English (United States)"),
    (False, "en-US", True, "Microsoft Zira - English (United States)"),
]

WIN11_EXTRA = [
    (False, "en-US", False, "Microsoft Michelle Online (Natural) - English (United States)"),
    (False, "en-US", False, "Microsoft Ana Online (Natural) - English (United States)"),
]

def gen_voices(rng, os_version):
    voices = list(WIN10_VOICES)
    if os_version.startswith("10.0.22"):  # Win11
        voices += WIN11_EXTRA
    return voices
```

**Quy tắc:**
- Voices PHẢI khớp OS version (Win10 có 3 voices en-US, Win11 có thêm Neural voices)
- `localService=true` cho built-in, `false` cho cloud/neural
- `voiceURI == name` trên Windows

#### NHÓM J: NetworkInformation (Event 2426461220 — HSW Gap H2)

**Tham số:**
```
navigator.connection.effectiveType, .downlink, .rtt, .saveData
```

**Thuật toán:**
```python
NET_PROFILES = [
    # effectiveType, downlink (Mbps, rounded 0.05), rtt (ms, rounded 25)
    ("4g", 10.0,  50),   # Residential fiber
    ("4g", 5.65,  75),   # Good cable
    ("4g", 2.85,  100),  # Average broadband
    ("4g", 1.45,  150),  # DSL
    ("3g", 0.55,  300),  # Slow
]

def gen_connection(rng, proxy_quality):
    if proxy_quality == "residential":
        eff, dl, rtt = rng.choice(NET_PROFILES[:3])
    else:
        eff, dl, rtt = rng.choice(NET_PROFILES)
    return {"effectiveType": eff, "downlink": dl, "rtt": rtt, "saveData": False}
```

**Quy tắc:**
- `downlink` rounded tới 0.05 Mbps (Chrome quantize)
- `rtt` rounded tới 25ms
- Nếu proxy rtt > 200ms nhưng `connection.rtt = 50` → **mâu thuẫn** → phải khớp

#### NHÓM K: Memory / Storage (Event 58508894 — HSW Gaps H4, H5)

**Tham số:**
```
performance.memory.jsHeapSizeLimit,
performance.memory.totalJSHeapSize,
StorageManager.estimate().quota
```

**Thuật toán:**
```python
def gen_memory(rng, device_memory_gb):
    # jsHeapSizeLimit: V8 tự set dựa trên physical RAM
    # CẦN ĐO THẬT trên Chrome 157 với từng mức RAM
    # Giá trị ước tính (xác nhận bằng corpus):
    heap_limits = {
        2: 2_197_815_296,   # device_memory=2 (RAM thật 2-3GB)
        4: 2_197_815_296,   # device_memory=4 (RAM thật 4-7GB) — V8 vẫn cap ~2.1GB
        8: 4_294_967_296,   # device_memory=8 (RAM thật 8GB+) — V8 cap ~4.3GB
    }
    heap_limit = heap_limits.get(device_memory_gb, 4_294_967_296)
    # ⚠ GIÁ TRỊ TRÊN CẦN XÁC NHẬN: chạy Chrome stock trên máy 4GB RAM, đo performance.memory

    # totalJSHeapSize: thay đổi mỗi lần đo (GC dependent)
    # Không cần fake — để Chrome tự report

    # StorageManager quota: Chrome reports ~60% of disk free space
    # Phải ĐO THẬT — quota phụ thuộc partition size, không random
    # Giá trị phổ biến (SSD 256GB-1TB, 40-70% free):
    quota_tiers = [
        107_374_182_400,   # ~100GB free (SSD 256GB)
        214_748_364_800,   # ~200GB free (SSD 512GB)
        322_122_547_200,   # ~300GB free (SSD 1TB)
    ]
    quota = rng.choice(quota_tiers)

    return {"heap_limit": heap_limit, "quota": quota}
```

#### NHÓM L: Permissions (HSW Gap H6)

**Tham số:**
```
Permissions.query({name: "notifications"}) → {state: "prompt"|"denied"|"granted"}
Permissions.query({name: "camera"}) → {state: "prompt"}
```

**Thuật toán:**
```python
def gen_permissions(rng):
    # notifications: thường "default" (prompt) hoặc "denied"
    notif = rng.choice(["prompt", "prompt", "denied"])
    return {
        "notifications": notif,
        "camera": "prompt",
        "microphone": "prompt",
        "geolocation": "prompt",
    }
```

#### NHÓM M: Property Descriptors (Event 2075394470 — HSW Gap H8)

**Tham số:**
- `Object.getOwnPropertyDescriptor()` trên 108+ properties
- Phải trả về đúng `{value, writable, enumerable, configurable}` hoặc `{get, set, ...}`

**Thuật toán:**
```
KHÔNG random — phải CHÍNH XÁC giống Chrome stock.

Chiến lược Kernel-R (G5):
- Hook tại IDL binding level (trước khi JS thấy)
- Khi profile override navigator.hardwareConcurrency = 8:
  → V8 binding trả value=8 (không phải defineProperty override)
  → GOPD trả {value: 8, writable: false, enumerable: true, configurable: true}
  → GIỐNG HỆT Chrome stock

Nếu dùng Object.defineProperty() JS-level:
  → GOPD trả {value: 8, writable: false, enumerable: false, configurable: false}
  → KHÁC Chrome stock → bị detect

LÝ DO hook C++: Property descriptors phải trông native.
```

#### NHÓM N: Brand Check / TypeError (HSW Gap H11)

**Tham số:**
- Gọi DOM method với wrong `this` → TypeError message

**Thuật toán:**
```
Chrome thật: document.createElement.call(null) → TypeError
  Message: "Failed to execute 'createElement' on 'Document': ..."

jsdom/fake: TypeError message format KHÁC
  Message: "Illegal invocation" hoặc "not a valid instance of..."

Chiến lược Kernel-R:
- Vì dùng Chromium thật → TypeError message TỰ NHIÊN đúng
- KHÔNG cần làm gì — browser thật = native behavior
- CHỈ CẦN đảm bảo KHÔNG sửa DOM method implementations
```

### 11.3 Quy tắc nhất quán chéo (Cross-Consistency Matrix)

| Quy tắc | Giải thích | Vi phạm = detect |
|---------|-----------|-------------------|
| `GPU vendor` ↔ `renderer string` | NVIDIA renderer PHẢI có "NVIDIA" trong string | ✗ renderer nói AMD nhưng vendor nói NVIDIA |
| `GPU` ↔ `WebGL params` | RTX 3060 PHẢI có MAX_TEXTURE_SIZE=16384 | ✗ Params không khớp GPU model |
| `GPU` ↔ `canvas hash` | Cùng GPU + cùng driver → cùng canvas hash | ✗ Hash không khớp GPU declared |
| `screen.dpr` ↔ `resolution` | 1536×864 = 1920×1080 @ 125% → dpr=1.25 | ✗ DPR không khớp resolution |
| `availHeight` ↔ `height` | availH = H - taskbar (40 or 48px ở 100% DPI) | ✗ availH > height |
| `innerW/H` ↔ `screen` | innerW < screen.width/dpr, innerH < availH/dpr | ✗ inner > screen |
| `outerW/H` ↔ `screen` | outerW ≤ screen.width/dpr | ✗ outer > screen |
| `cores` ↔ `deviceMemory` | 24 cores + 4GB RAM = không tồn tại | ✗ Combo bất khả thi |
| `cores` ↔ `WASM timing` | Cores cao → WASM nhanh hơn | ✗ 16 cores nhưng slow = suspicious |
| `timezone` ↔ `IP geo` | IP ở US nhưng timezone Asia = lộ | ✗ Geo mismatch |
| `language` ↔ `timezone` | US proxy → en-US, VN proxy → vi-VN (chỉ 2 locale) | ✗ Language không khớp country |
| `platform` ↔ `UA string` | "Win32" + "Macintosh" UA = impossible | ✗ OS mismatch |
| `UA-CH brands` ↔ `sec-ch-ua` header | 3 brands phải giống nhau | ✗ Header/JS khác nhau |
| `UA-CH platformVersion` ↔ `OS build` | "15.0.0" = Win11 | ✗ PlatformVer Win11 nhưng build Win10 |
| `voices` ↔ `OS version` | Win10 có 3 en-US voices, Win11 có thêm Neural | ✗ Neural voice trên Win10 |
| `connection.rtt` ↔ `actual latency` | Proxy 300ms nhưng connection.rtt=50 | ✗ Timing mismatch |
| `fonts` ↔ `OS` | macOS fonts trên Windows = impossible | ✗ Font platform mismatch |
| `heapSizeLimit` ↔ `deviceMemory` | deviceMemory≤4 → heap ~2.2GB, deviceMemory=8 → heap ~4.3GB (CẦN ĐO) | ✗ Heap > physical RAM |
| `colorDepth` ↔ `GPU` | HDR 30-bit chỉ trên GPU hỗ trợ | ✗ Integrated GPU + 30-bit |
| `plugins` = 5 | Chrome luôn có 5 PDF plugins, không hơn không kém | ✗ plugins=0 hoặc plugins=3 |

### 11.4 Đảm bảo mỗi Browser Instance là Unique

**Nguyên tắc: `seed` → `profile` là ánh xạ 1-1 deterministic**

```
seed (32 bytes random)
  │
  ├─→ CSPRNG(seed, "screen")    → chọn resolution/dpr
  ├─→ CSPRNG(seed, "cpu")       → chọn cores/memory combo
  ├─→ CSPRNG(seed, "gpu")       → chọn GPU từ database
  ├─→ CSPRNG(seed, "fonts")     → chọn font set
  ├─→ CSPRNG(seed, "locale")    → chọn timezone (khớp proxy geo)
  ├─→ CSPRNG(seed, "canvas")    → gamma/contrast cho ClearType
  ├─→ CSPRNG(seed, "audio")     → audio bias
  ├─→ CSPRNG(seed, "brands")    → shuffle order UA-CH brands
  └─→ CSPRNG(seed, "connection")→ network profile
```

**Tại sao unique:**
1. Seed 32 bytes = 2^256 không gian → collision probability = 0
2. Mỗi domain (screen, cpu, gpu...) dùng domain-separated CSPRNG → thay đổi 1 domain không ảnh hưởng domain khác
3. GPU database có 50+ entries × 10+ resolutions × 5+ font sets × 10+ timezones = **25,000+ unique combos**
4. Canvas gamma/contrast thêm 9×11 = 99 variations per GPU → **2.5 triệu+ profiles**

**Ephemeral vs Persistent (G7):**
- **Ephemeral (mặc định):** Mỗi lần chạy = seed mới = profile mới
- **Persistent:** Lưu seed vào SQLite, tái dùng cho cùng proxy/account

**Entropy tối thiểu per instance:**
```
Screen:     ~10 choices
CPU/Memory: ~15 choices
GPU:        ~N choices (N = số GPU đo thật; hiện = 0, mục tiêu 50+)
Fonts:      ~5 variations
Canvas:     ~99 gamma/contrast combos (9 gamma × 11 contrast)
Timezone:   ~20 (tuỳ proxy pool)
Brands:     6 shuffle permutations
Connection: ~5 profiles
───────────────────────────────
Tổng: 10×15×N×5×99×20×6×5 = N × 89,100,000
  N=1  (GTX 1070 only):   ~89 triệu profiles
  N=10 (10 GPUs):         ~891 triệu profiles
  N=50 (mục tiêu):        ~4.5 tỷ profiles
```

### 11.5 Silent Pass — Yếu tố quyết định

hCaptcha server quyết định `pass=true` DỰA TRÊN:

| Yếu tố | Trọng số (ước tính) | Browser fork giải quyết? |
|---------|---------------------|--------------------------|
| **TLS/H2 fingerprint** | 15% | ✅ Chromium stock = genuine |
| **HTTP headers consistency** | 10% | ✅ sec-ch-ua, sec-fetch-*, Accept-Language tự nhiên |
| **Cookie history** | 10% | ⚠ Session mới = no history, cần warm-up |
| **Browser fingerprint score** | 55% | ✅ Profile nhất quán = score cao |
| **Site-specific risk** | 10% | ❌ Riot = high risk site, khó silent pass |

**Chiến lược tối ưu silent pass:**

1. **IP:** Residential proxy, không reuse IP < 30 phút, geographic diversity
2. **TLS:** 0 modification trên net/ → JA3/H2 identical Chrome stock
3. **Headers:** Chromium tự sinh headers đúng — chỉ cần profile nhất quán
4. **Cookie warm-up:** Trước khi solve hCaptcha, navigate 2-3 pages trên site → accumulate cookies
5. **Fingerprint:** Profile phải pass Validator (P1-P10) → không có red flags
6. **Timing:** Không request checksiteconfig ngay lập tức — delay 2-5s sau page load

### 11.6 Giá trị CẦN ĐO THẬT trước khi code (Task T16)

Các giá trị dưới đây KHÔNG THỂ đoán — phải đo trên Chrome 157 stock:

| # | Giá trị | Cách đo | Ưu tiên |
|---|---------|---------|---------|
| M1 | GPU params GTX 1070 (40+ WebGL values) | Trang capture HTML → gl.getParameter() | P0 |
| M2 | Canvas path 15 floats (GTX 1070) | Trang capture → arc/bezier rendering | P0 |
| M3 | Canvas toDataURL hash (GTX 1070, per gamma/contrast) | Sweep 9×11 combos | P0 |
| M4 | Audio hash (GTX 1070) | OfflineAudioContext capture | P0 |
| M5 | Font metrics (base Windows 10 fonts) | measureText() + offsetWidth/Height | P0 |
| M6 | jsHeapSizeLimit cho device_memory 2,4,8 | performance.memory trên máy khác RAM | P1 |
| M7 | StorageManager.estimate().quota | Đo trên máy với disk sizes khác nhau | P1 |
| M8 | Not-A.Brand version cho Chrome 157 | navigator.userAgentData.brands | P0 |
| M9 | platformVersion cho Win10/Win11 | navigator.userAgentData.getHighEntropyValues() | P0 |
| M10 | SpeechSynthesis voices Win10 vs Win11 | speechSynthesis.getVoices() | P1 |
| M11 | Chrome plugins/mimeTypes count | navigator.plugins.length trên Chrome 157 | P0 |
| M12 | Window chrome height (tab+toolbar+bookmarkbar) | outerHeight - innerHeight on maximized | P0 |

**Workflow:**
1. Build Chrome 157 stock (S0-S6)
2. Tạo trang capture HTML (`corpus/capture.html`) đo tất cả M1-M12
3. Chạy trên máy này → corpus entry đầu tiên (GTX 1070)
4. Mở rộng corpus: chạy capture trên máy khác (AMD, Intel, laptop...)

---

## 12. Cấu trúc thư mục

```
C:\src\
├── chromium\src\                    # Chromium source + patches đã áp
│   ├── components\kr_fingerprint\   # Browser-side: loader, validator, switches
│   ├── third_party\blink\...\kr_fingerprint\  # Blink: singleton, noise
│   ├── chrome\browser\kr_automation\           # Automation pipe + ops
│   └── out\Dev\chrome.exe           # Build output
│
├── kernel-r\                        # Repo riêng
│   ├── PINNED_VERSION
│   ├── patches\*.patch              # 41 patch
│   ├── scripts\                     # build, apply, export, rebase, fw-rules
│   ├── tools\kr\                    # Python: generator, gateway, manager, automation
│   ├── corpus\                      # Dữ liệu đo thật: os, gpu, fonts, screens
│   ├── harness\                     # Test harness (Python + named pipe) check_*.py
│   ├── ui\                          # Manager web UI (HTML/JS thuần)
│   ├── vm\                          # Phase 2: sandbox, hyperv, orchestrator
│   └── docs\                        # automation.md, manager.md, collecting-gpu-data.md
│
└── depot_tools\                     # Chromium build tools
```
