# Environment Setup

Spec: `2026-10-29-design-spec.md`. Mọi bước bên dưới chạy trên máy hiện tại (Win 11 Pro, i5-14600KF, 32 GB).

## 1. Quy tắc vị trí (quan trọng)

- **Không** đặt cây Chromium trong OneDrive (`Desktop\New folder`): OneDrive đồng bộ hàng trăm nghìn file sẽ làm build hỏng/chậm.
  Docs ở đây giữ nguyên. Mã Chromium đặt ở `C:\src\chromium` (đường dẫn ngắn).
- Thư mục công cụ riêng: `C:\src\kernel-r\` (git repo của chúng ta: `patches/`, `tools/`, `corpus/`, `harness/`).
- Loại trừ Windows Defender cho `C:\src` và `C:\depot_tools` (giảm thời gian build mạnh):
  `Add-MpPreference -ExclusionPath 'C:\src','C:\depot_tools'` (PowerShell admin).

## 2. Dung lượng (ổ C trống 182 GB)

| Hạng mục | Ước tính |
|----------|----------|
| Checkout `--no-history` | ~35-45 GB |
| `out\Dev` (component build, symbol_level=0) | ~40-60 GB |
| `out\Rel` (khi cần bản phát hành) | ~30-40 GB |
| Cache ccache/sccache (tuỳ chọn) | 10-20 GB |
| Tổng | ~120-165 GB |

182 GB là **đủ sát nút**. Bắt buộc: dùng `--no-history`, chỉ giữ một thư mục out ở một thời điểm, xoá `out\*` cũ.
Khuyến nghị: gắn thêm SSD hoặc dùng ổ khác >= 300 GB cho `C:\src` (đổi sang `D:\src`, cập nhật mọi đường dẫn).
Kiểm tra: `Get-PSDrive C` phải còn >= 60 GB sau khi checkout xong.

## 3. Cài công cụ

Chạy PowerShell **Admin**:

1. **Visual Studio 2022 Community** (hoặc Build Tools), workload:
   - "Desktop development with C++"
   - Thành phần: MSVC v143 x64/x86 build tools, **Windows 11 SDK (10.0.22621.x trở lên)**, **C++ ATL for latest build tools**, C++ MFC (nếu Chromium yêu cầu), "Debugging Tools for Windows" (nằm trong SDK).
   - Ngôn ngữ: English (Chromium build kỳ vọng).
   Lệnh gợi ý: `winget install Microsoft.VisualStudio.2022.Community` rồi thêm workload trong Visual Studio Installer.
2. **Windows SDK debugger**: Settings > Apps > Windows SDK > Modify > bật "Debugging Tools for Windows".
3. **depot_tools**: tải zip về `C:\depot_tools`, thêm vào **đầu** `PATH` (trước cả Python/Git).
4. Biến môi trường (hệ thống):
   - `DEPOT_TOOLS_WIN_TOOLCHAIN=0`
   - `vs2022_install=C:\Program Files\Microsoft Visual Studio\2022\Community`
   - `GYP_MSVS_VERSION=2022` (không bắt buộc với GN, nhưng vô hại)
5. Chạy `gclient` một lần để depot_tools tự cài Python/Git riêng; kiểm `python3 --version` trong shell mới.
6. Python 3.12 hiện có của hệ thống dùng cho `tools/kr`; Chromium dùng Python riêng của depot_tools. Không trộn venv.
7. Git cấu hình:
   ```
   git config --global core.autocrlf false
   git config --global core.filemode false
   git config --global branch.autosetuprebase always
   git config --global core.longpaths true
   ```
8. Virtualization (cho Phase 2): WMI báo `VirtualizationFirmwareEnabled=False`. Có thể do Hyper-V/VBS đang chiếm; xác minh bằng
   `systeminfo` (mục "Hyper-V Requirements"). Nếu thật sự tắt: bật Intel VT-x trong BIOS. Bật tính năng Windows:
   `Microsoft-Hyper-V-All`, `Containers-DisposableClientVM` (Windows Sandbox). Cần khởi động lại.

## 4. Lấy mã và ghim phiên bản

```
mkdir C:\src\chromium; cd C:\src\chromium
fetch --nohooks --no-history chromium
cd src
git fetch --tags --depth=1 origin tag <STABLE_TAG>
git checkout -b kr/base <STABLE_TAG>
gclient sync -D --with_branch_heads --nohooks
gclient runhooks
```
- Ghi `<STABLE_TAG>` vào `kernel-r/PINNED_VERSION` (một dòng). Mọi tài liệu và patch tham chiếu tag này.
- Nếu `--no-history` gây khó tag: lấy tag stable từ trang phát hành Chrome, rồi `git fetch origin refs/tags/<tag>:refs/tags/<tag> --depth=1`.

## 5. Cấu hình build (`gn args`)

`out\Dev` (phát triển, nhanh):
```
is_debug = false
is_component_build = true
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
enable_nacl = false
use_jumbo_build = false
dcheck_always_on = true
is_clang = true
```
`out\Rel` (đóng gói, sau này):
```
is_debug = false
is_official_build = true   # cần nhiều RAM/thời gian
is_component_build = false
symbol_level = 0
chrome_pgo_phase = 0
```
Lệnh: `gn gen out\Dev` rồi `autoninja -C out\Dev chrome`.
Thời gian dự kiến lần đầu: 3-6 giờ với 20 luồng; build tăng dần: 1-15 phút.
Kiểm tra RAM khi link: nếu nghẽn, giảm song song: `autoninja -C out\Dev -j 14 chrome`.

## 6. Quy trình patch (series)

```
kernel-r/
  PINNED_VERSION
  patches/
    0001-add-kr-switches.patch
    0002-kr-profile-loader.patch
    ...
  scripts/
    apply.ps1      # git am --3way patches\*.patch trên cây sạch
    export.ps1     # git format-patch kr/base..HEAD -o patches\
    rebase.ps1     # đổi tag, apply lại, báo patch lỗi
```
- Mỗi task trong Phase 1 = tối thiểu một commit = một patch. Commit message: `kr: <vùng>: <việc>`.
- Chạy `scripts/export.ps1` sau mỗi task; không bao giờ sửa trực tiếp file patch.
- Nâng phiên bản: `rebase.ps1 <NEW_TAG>`; patch lỗi sửa trên cây rồi `export.ps1`.

## 6b. Quyền AppContainer cho sandbox dịch vụ mạng (bắt buộc, phát hiện 2026-10-30)

Sau mỗi lần build ra thư mục mới: `powershell -ExecutionPolicy Bypass -File C:\src\kernel-r\scripts\fix-sandbox-acl.ps1 [-Dir <thư mục chứa chrome.exe>]`.
Thiếu bước này, dịch vụ mạng sập lúc khởi động (log `Sandbox cannot access executable`, `Network service crashed`) và trang không tải được.
Kiểm: `python harness/check_network_sandbox.py`.

## 7. Kiểm tra môi trường sẵn sàng (Definition of Ready)

- [ ] `cl.exe` tìm thấy trong "Developer PowerShell for VS 2022".
- [ ] `gn --version` và `autoninja --version` chạy được.
- [ ] `out\Dev\chrome.exe` build thành công, mở trang `about:blank` và `https://example.com`.
- [ ] `git -C C:\src\chromium\src log -1` thấy tag đã ghim.
- [ ] Ổ C còn >= 60 GB.
- [ ] Thư mục `kernel-r/` có `PINNED_VERSION` và 3 script trên.
- [ ] Defender exclusions đã thêm.

## 8. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `gclient sync` treo | mạng/proxy | `set HTTPS_PROXY`, thử lại `-v -v` |
| Thiếu `atlbase.h` | Chưa cài ATL | Cài "C++ ATL for latest build tools" |
| Lỗi `Windows SDK ... debugger` | Thiếu Debugging Tools | Mục 3.2 |
| Hết RAM khi link | Quá nhiều job | `-j 10`, đóng app khác |
| Build lại từ đầu mỗi lần | Đổi `gn args` | Đừng đổi args giữa chừng |
