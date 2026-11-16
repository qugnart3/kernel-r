# Kernel-R Phase 2: VM / Sandbox Layer

> **For agentic workers:** dùng superpowers:executing-plans hoặc subagent-driven-development. Chỉ bắt đầu khi Phase 1 qua gate "Phase 1 done".

**Goal:** Mỗi lần mở chạy trong một môi trường Windows sạch, riêng biệt, có định danh phần cứng ảo sinh từ cùng seed với profile trình duyệt.

**Architecture:** Orchestrator trên host: nhận seed ⇒ tạo VM từ ổ khác biệt (differencing disk) của image gốc ⇒ đặt cấu hình VM ⇒ đưa `profile.json` và build Chromium vào guest ⇒ chạy ⇒ huỷ VM khi đóng.

**Tech Stack:** Windows Sandbox (V0) → Hyper-V Gen2 + PowerShell/WMI (V1) → QEMU/KVM trên Linux host (V2, tuỳ chọn).

**Spec:** `2026-10-29-design-spec.md`

**Global Constraints:**
- Guest là Windows thật (D3): không giả OS khác họ bằng Chromium.
- Không có task che giấu hypervisor khỏi anti-cheat/integrity check (ngoài phạm vi, xem README).
- Định danh VM chỉ là cấu hình hợp lệ của hypervisor (tên, serial, UUID, MAC); không vá nhân guest.

**Review Focus:**
1. Dữ liệu VM sót lại sau khi đóng (đĩa, thư mục chia sẻ, snapshot) -> `test_teardown_leaves_nothing`.
2. Profile trình duyệt nói "GPU A" nhưng guest dùng GPU ảo/phần mềm -> `test_gpu_path_matches_profile`.
3. Hai VM chạy song song đụng MAC/UUID/tên -> `test_parallel_unique_identity`.
4. Giấy phép Windows trong VM -> mục 1.
5. Đồng hồ/timezone guest lệch profile -> `test_guest_tz_matches_profile`.

---

## 1. Quyết định nền tảng và giấy phép

| Phương án | Ưu | Nhược | Dùng khi |
|---|---|---|---|
| V0 Windows Sandbox | Sạch mỗi lần (tự huỷ), cấu hình bằng `.wsb`, có vGPU tuỳ chọn | Ít kiểm soát định danh, 1 instance/máy | Thử nghiệm nhanh, ephemeral thật |
| V1 Hyper-V Gen2 | Điều khiển bằng PowerShell/WMI, đa VM, differencing disk, GPU-P | Cần Windows Pro, Hyper-V bật | Hướng chính |
| V2 QEMU/KVM (Linux host) | Kiểm soát SMBIOS/thiết bị sâu nhất, passthrough GPU | Cần máy/phân vùng Linux, phức tạp | Khi V1 không đủ |

- Quyết định: **V0 để dựng pipeline, V1 làm bản chính, V2 chỉ khi có nhu cầu thật.**
- Giấy phép: mỗi VM Windows cần giấy phép hợp lệ. Lựa chọn hợp pháp: Windows Enterprise Evaluation (90 ngày, tái tạo image), hoặc giấy phép bạn sở hữu cho số VM đồng thời. Ghi vào `NOTES.md` phương án chọn trước khi tạo hàng loạt.
- Tài nguyên (máy 32 GB, 20 luồng): mỗi guest 4 GB RAM / 2-4 vCPU ⇒ tối đa 3-4 VM đồng thời, chừa 12-16 GB cho host.
- BIOS: bật Intel VT-x (WMI hiện báo `False`, kiểm tra ở T-V0).

## 2. Điều kiện trước

> **Trạng thái (2026-10-31, đo bằng `vm/check-prereqs.ps1`):** Windows 11 Pro, RAM 31.8 GB, C: trống 140 GB: đủ. Hypervisor đã chạy sẵn (VT-x hoạt động, không cần đụng BIOS). Hyper-V đầy đủ và Windows Sandbox **chưa cài**: chạy `vm/enable-virtualization.ps1` bằng Administrator rồi khởi động lại. Đã làm sẵn phần không cần VM: `identity.py`, `tz_map.py`, V0 (`vm/sandbox/`). Xem CHANGELOG.
- [ ] Phase 1 qua gate.
- [ ] BIOS bật VT-x/VT-d; `systeminfo` báo Hyper-V Requirements = Yes.
- [ ] Bật `Microsoft-Hyper-V-All` và `Containers-DisposableClientVM`, khởi động lại.
- [ ] Ổ chứa VM >= 100 GB trống (image gốc ~25 GB + differencing disks).

---

### Task V0: Pipeline thử bằng Windows Sandbox

**Files:** Create: `kernel-r/vm/sandbox/kr.wsb.tmpl`, `kernel-r/vm/sandbox/run.ps1`, `kernel-r/vm/tests/test_sandbox.py`

**Interfaces:** Produces `run.ps1 -Seed <hex> -Profile <path>`; ánh xạ thư mục chỉ-đọc chứa build Chromium + profile; thư mục ghi riêng cho log.

**Steps:**
- [ ] Test `test_sandbox_boots_and_runs_chrome`: khởi chạy, chrome mở trang `kr/collect.html` và ghi JSON ra thư mục ghi. Kỳ vọng ban đầu: FAIL.
- [ ] Viết `.wsb` (vGPU bật, mạng bật, ánh xạ thư mục, `LogonCommand` chạy chrome với `--kr-*`).
- [ ] Test `test_teardown_leaves_nothing` (Review Focus 1): sau khi đóng sandbox, thư mục ghi chỉ có log đã định.
- [ ] Commit: `kr: vm: windows sandbox pipeline`.

---

### Task V1.1: Image gốc (golden image)

**Files:** Create: `kernel-r/vm/hyperv/{build-golden.ps1,unattend.xml.tmpl,README.md}`

**Interfaces:** Produces `golden.vhdx` (Windows sạch, đã cài driver Hyper-V integration, VC++ redist, Chromium kr build, dịch vụ khởi động `kr-agent`).

**Steps:**
- [ ] Tạo VM Gen2 từ ISO hợp lệ, cài Windows, cập nhật, tắt các tác vụ nền gây nhiễu (Windows Update tự động, OneDrive).
- [ ] Cài `kr-agent` (script PowerShell chạy lúc đăng nhập): đọc `profile.json` từ ổ cấp phát, đặt timezone/locale/độ phân giải theo profile, chạy Chromium.
- [ ] Sysprep (generalize) rồi lưu `golden.vhdx`; đặt chỉ-đọc.
- [ ] Test `test_golden_boots_via_diff_disk`.
- [ ] Commit: `kr: vm: golden image build scripts`.

---

### Task V1.2: Orchestrator Hyper-V

**Files:**
- Create: `kernel-r/vm/orchestrator/{vmctl.ps1,identity.py,orchestrator.py}`
- Test: `kernel-r/vm/tests/test_{identity,orchestrator,parallel,teardown}.py`

**Interfaces:**
- Produces `identity.derive(seed) -> VmIdentity { name, bios_serial, baseboard_serial, chassis_serial, asset_tag, mac, uuid, cpu_count, memory_mb, disk_gb }` (xác định theo seed; giá trị đúng định dạng nhà sản xuất hợp lệ).
- Produces `orchestrator.start(seed) -> VmHandle`, `.stop()`, `.logs()`.
- Consumes `profile.json` (T16) để khớp `cpu.cores`, RAM, độ phân giải.

**Steps:**
- [ ] Test `test_identity_deterministic`, `test_identity_unique_over_10000_seeds`, `test_identity_formats_valid` (UUID v4 hợp lệ, MAC có bit locally-administered/unicast đúng).
- [ ] Viết `identity.py` ⇒ PASS.
- [ ] `vmctl.ps1`: `New-VHD -Differencing -ParentPath golden.vhdx`, `New-VM -Generation 2`, `Set-VMProcessor -Count`, `Set-VMMemory`, `Set-VMNetworkAdapter -StaticMacAddress`, đặt `BIOSSerialNumber`, `BaseBoardSerialNumber`, `ChassisSerialNumber`, `ChassisAssetTag` qua `Msvm_VirtualSystemSettingData` (WMI), gắn ISO cấu hình chứa `profile.json`.
- [ ] Test `test_parallel_unique_identity` (Review Focus 3): 3 VM chạy cùng lúc, không trùng định danh.
- [ ] Test `test_guest_tz_matches_profile` (Review Focus 5): trong guest `Get-TimeZone` khớp profile.
- [ ] Test `test_teardown_leaves_nothing`: sau `stop()` đã xoá VM, VHDX khác biệt, ISO cấu hình, bản ghi WMI.
- [ ] Commit: `kr: vm: hyper-v orchestrator and identity`.

---

### Task V1.3: Đường GPU

**Files:** Create: `kernel-r/vm/hyperv/gpu.ps1`, `kernel-r/vm/tests/test_gpu.py`

**Interfaces:** Consumes `profile.gpu`; Produces VM có GPU-P (partition) từ GPU máy chủ (RTX 5060 Ti) nếu driver/OS hỗ trợ.

**Steps:**
- [ ] Kiểm tra hỗ trợ GPU-P: `Get-VMHostPartitionableGpu`. Nếu không hỗ trợ ⇒ ghi quyết định: dùng GPU ảo + giới hạn profile chỉ chọn GPU tier thấp *khớp đường render thực tế*, hoặc chuyển V2.
- [ ] Test `test_gpu_path_matches_profile` (Review Focus 2): trong guest, WebGL `UNMASKED_RENDERER` của Chromium kr **không** mâu thuẫn với GPU mà guest thấy (ví dụ guest render bằng GPU NVIDIA thì profile phải thuộc nhóm tier/vendor tương thích; render phần mềm ⇒ profile phải khai GPU cấp thấp phù hợp hoặc bị validator loại).
- [ ] Mở rộng Validator: thêm quy tắc `render_path` (`gpu-p|software|passthrough`) ràng buộc `gpu.tier`.
- [ ] Commit: `kr: vm: gpu path and validator rule`.

---

### Task V1.4: Mạng và proxy

**Files:** Create: `kernel-r/vm/hyperv/net.ps1`

**Steps:**
- [ ] Mỗi VM một vSwitch nội bộ + NAT hoặc proxy riêng; truyền `--kr-egress-ip`/`--proxy-server` vào Chromium.
- [ ] Test `test_egress_ip_matches_profile_locale`: timezone/ngôn ngữ do generator chọn theo vùng của egress IP (khi có proxy).
- [ ] Test `test_no_host_network_leak`: guest không thấy mạng LAN của host.
- [ ] Commit: `kr: vm: per-vm networking`.

---

### Task V1.5: Vòng đời, dọn dẹp, giám sát

**Files:** Create: `kernel-r/vm/orchestrator/{lifecycle.py,reaper.py}`

**Steps:**
- [ ] `reaper.py`: quét VM/VHDX mồ côi mỗi lần khởi động và theo lịch, xoá có xác nhận.
- [ ] Test `test_crash_cleanup`: kill tiến trình orchestrator giữa chừng ⇒ lần sau reaper dọn sạch.
- [ ] Giới hạn đồng thời theo RAM còn trống (`test_refuses_when_low_memory`).
- [ ] Commit: `kr: vm: lifecycle and reaper`.

---

### Task V2 (tuỳ chọn): QEMU/KVM backend

**Files:** Create: `kernel-r/vm/qemu/{launch.py,smbios.py}`

**Steps:**
- [ ] Chỉ làm khi V1.3 xác nhận GPU-P không đủ hoặc cần kiểm soát SMBIOS sâu hơn Hyper-V cho phép.
- [ ] Dùng tuỳ chọn cấu hình chính thức của QEMU (`-smbios`, `-uuid`, `-netdev`/`-device` MAC) và qcow2 backing files; cùng giao diện `orchestrator.start(seed)`.
- [ ] Cùng bộ test V1.2/V1.5 chạy trên backend này.

---

## Tiêu chí hoàn thành Phase 2
- [ ] `kr run --vm` mở một VM mới trong <= 60 giây, định danh khác nhau mỗi lần, đóng là mất sạch.
- [ ] Bộ harness Phase 1 chạy trong guest cho cùng kết quả P1-P10.
- [ ] 3 VM song song ổn định 24 giờ.
- [ ] Mọi test mục trên xanh; tài liệu giấy phép Windows đã chốt.

## Self-review
- Spec D3 (guest Windows thật) ↔ mục 1; G7 ephemeral ↔ V0/V1.5; R7 giấy phép ↔ mục 1; R1 hiệu năng ↔ V1.3 `render_path`.
- Ngoài phạm vi được nhắc lại (không che hypervisor khỏi anti-cheat).
