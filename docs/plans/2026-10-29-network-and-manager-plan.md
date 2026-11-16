# Kernel-R: Proxy, Network Consistency và Manager UI

Spec: `2026-10-29-design-spec.md`. Bổ sung cho Phase 1 (T13, T14) và Phase 2 (V1.4).

> **For agentic workers:** dùng superpowers:executing-plans. Tick `- [ ]` khi xong.

**Goal:** Mỗi profile gắn đúng một đường ra mạng (proxy) và không có kênh nào đi vòng; profile sinh ra *sau khi* biết IP đầu ra để locale/timezone khớp. Có giao diện quản lý nội bộ để tạo, chạy, dừng, xem trạng thái.

**Architecture:** `kr-gateway` (tiến trình cục bộ) giữ thông tin xác thực upstream; trình duyệt chỉ nói chuyện với gateway; tường lửa chặn mọi đường ra khác của `chrome.exe`; preflight đo IP đầu ra thật rồi mới sinh profile.

**Tech Stack:** Python 3.12 (asyncio, `python-socks` hoặc tự viết SOCKS5/HTTP CONNECT), Windows Firewall (`New-NetFirewallRule`), FastAPI + SQLite + HTML tĩnh cho UI, pytest.

**Spec:** `2026-10-29-design-spec.md`

**Global Constraints:** Không lưu thông tin xác thực proxy trong profile.json hay dòng lệnh Chromium. Ephemeral mặc định: xoá mọi thứ khi đóng. Giao diện chỉ lắng nghe `127.0.0.1`.

**Review Focus:**
1. Kênh đi vòng proxy (QUIC/UDP, DNS, WebRTC, IPv6, dịch vụ nền của Chrome) -> `test_no_direct_egress`.
2. Proxy chết giữa phiên làm trình duyệt lộ IP thật -> `test_kill_switch`.
3. Timezone/ngôn ngữ không khớp địa lý IP đầu ra -> `test_locale_matches_egress_geo`.
4. Hai profile dùng chung một IP -> `test_one_ip_one_profile`.
5. Lộ mật khẩu proxy qua dòng lệnh, `chrome://version`, log -> `test_no_secret_leak`.

---

## 1. Các kênh lộ qua mạng (danh sách phải đóng hết)

| # | Kênh | Vì sao lộ | Cách đóng |
|---|------|-----------|-----------|
| N1 | IP đầu ra | Trang thấy IP thật nếu có đường đi vòng | Gateway + tường lửa (mục 2) |
| N2 | DNS | Phân giải DNS bằng resolver của máy | `socks5://` (DNS phía proxy) hoặc HTTP CONNECT; cấm phân giải cục bộ |
| N3 | WebRTC (STUN/ICE) | UDP không đi qua proxy HTTP, lộ IP LAN/thật | T13 + chính sách `disable_non_proxied_udp`. **Đính chính 2026-10-30:** cờ `--force-webrtc-ip-handling-policy` mặc định KHÔNG có tác dụng trong chrome.exe (chỉ content_shell); đã vá (patch 0014) và kiểm chứng: 0 candidate với `disable_non_proxied_udp`. |
| N4 | QUIC/HTTP3 | UDP đi thẳng, bỏ qua HTTP proxy | Tắt QUIC (`--disable-quic`) hoặc chỉ dùng SOCKS5 có UDP-associate; mặc định tắt |
| N5 | IPv6 | Trình duyệt dùng IPv6 trực tiếp | Chặn IPv6 đi ra của `chrome.exe` bằng tường lửa; gateway chỉ IPv4 (hoặc IPv6 của proxy) |
| N6 | Dịch vụ nền của Chrome | Safe Browsing, kiểm tra cập nhật, captive-portal, Google API, prefetch, DNS prefetch | Tắt bằng flag/policy; tường lửa chặn mọi đích không qua gateway |
| N7 | Địa lý không khớp | Timezone/ngôn ngữ/`Accept-Language` khác vùng của IP | Preflight (mục 3): sinh locale **từ** geo của IP |
| N8 | Loại IP / ASN | IP trung tâm dữ liệu, hoặc ASN không hợp với "người dùng nhà" | Chọn loại proxy phù hợp mục đích; ghi `ip_class` vào metadata |
| N9 | Độ trễ / MTU / TCP | Độ trễ không hợp lý với vùng khai báo; dấu vân tay ngăn xếp TCP khác OS khai báo | Chỉ khai Windows (D3) nên TCP stack của host khớp; đo RTT trong preflight, cảnh báo nếu bất thường |
| N10 | Danh tiếng IP | IP nằm trong danh sách xấu | Kiểm tra trước khi dùng, ngưỡng loại bỏ cấu hình được |
| N11 | Tái sử dụng IP | Hai profile cùng IP | Ràng buộc 1 IP ↔ 1 profile trong DB |
| N12 | Chia sẻ chung đường mạng | LAN thật bị nhìn thấy từ VM/trình duyệt | Phase 2: vSwitch nội bộ + NAT qua gateway |

## 2. Thiết kế `kr-gateway`

```
chrome.exe  ──socks5://127.0.0.1:PORT (không auth)──►  kr-gateway  ──(auth)──►  upstream proxy ──► Internet
   ▲                                                       │
   └──── tường lửa: chrome.exe chỉ được nối 127.0.0.1:PORT; mọi thứ khác bị chặn
```

- Mỗi profile một gateway instance, cổng cục bộ riêng (cổng ngẫu nhiên, chỉ bind `127.0.0.1`).
- Chromium chỉ nhận `--proxy-server=socks5://127.0.0.1:PORT` + `--proxy-bypass-list=<-loopback>` (không có bypass nào ngoài loopback).
- Mật khẩu upstream chỉ nằm trong bộ nhớ gateway, nạp từ kho mã hoá của máy (Windows DPAPI qua `keyring`/`win32crypt`), không ghi vào profile hay dòng lệnh.
- **Kill-switch:** nếu upstream chết, gateway đóng cổng cục bộ ngay ⇒ Chromium mất mạng thay vì rơi sang đường thẳng. Tường lửa là lớp thứ hai nếu gateway bị crash.
- Giao thức upstream hỗ trợ: HTTP CONNECT, SOCKS5 (có user/pass). Tuỳ chọn: chuỗi 2 proxy.
- Ghi log chỉ metadata (thời gian, byte), không ghi URL.

### Quy tắc tường lửa (mỗi lần chạy, sinh động)
Trong Windows Firewall, quy tắc Block luôn thắng Allow, nên không dùng cặp Allow+Block. Chỉ dùng **một** quy tắc Block áp lên mọi địa chỉ *trừ* loopback:
```
New-NetFirewallRule -DisplayName "kr-<id>-block" -Program <chrome.exe> -Direction Outbound -Action Block `
  -RemoteAddress 0.0.0.0-126.255.255.255,128.0.0.0-255.255.255.255,::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff
```
(Loopback IPv4 `127.0.0.0/8` và IPv6 `::1` nằm ngoài các dải này nên vẫn thông.) Test `test_no_direct_egress` xác minh hành vi thực tế rồi chỉnh. Cần admin ⇒ cài một dịch vụ nhỏ một lần để tạo/xoá quy tắc. Xoá quy tắc khi thoát.

> **Trạng thái 2026-10-30:** N1/N2 (gateway + kill-switch + preflight theo IP) đã làm và kiểm chứng với proxy HTTP thật (`tools/kr/gateway.py`, `proxy_probe.py`, `main.py --proxy`, `harness/check_proxy_leaks.py`). Tường lửa (mục 2) đã làm và kiểm chứng 2026-10-30 (`scripts/fw-rules.ps1`, `harness/check_firewall.py`). **N4 (pool, 1 IP ↔ 1 profile), M1 (API), M2 (UI) đã làm và kiểm chứng 2026-10-30** (xem `docs/manager.md`, CHANGELOG). Khác kế hoạch: `http.server` thay FastAPI, client WebSocket tối giản thay Playwright, DPAPI bằng `ctypes`. Chưa làm: M3 (chạy trong VM, thuộc Phase 2), kiểm IPv6 (mạng không có IPv6). A/B nhân quả của tường lửa đã chạy 2026-10-30 (gỡ quy tắc: lộ IP thật; bật quy tắc: bị chặn). Đính chính: không dùng `--proxy-bypass-list=<-loopback>` (làm trang cục bộ không tải được); xem CHANGELOG.

## 3. Preflight và sinh profile theo IP (đảo thứ tự)

Trình tự mới của launcher (T17):
1. Chọn proxy cho profile (DB: 1 IP ↔ 1 profile).
2. Mở gateway, **đo IP đầu ra** qua endpoint echo do chính bạn dựng (tránh gửi IP cho bên thứ ba); lấy: IP, ASN, quốc gia, thành phố, timezone, RTT.
3. Tra geo bằng cơ sở dữ liệu cục bộ (ví dụ bản MaxMind GeoLite2 tải sẵn, giấy phép cho phép dùng nội bộ) để không phát sinh truy vấn ra ngoài.
4. Gọi `generate(seed, egress=EgressInfo)`: timezone, `languages`, định dạng ngày/số, bàn phím, thậm chí bộ font theo vùng đều bắt nguồn từ geo.
5. Validator thêm quy tắc N7: `locale.timezone ∈ tz_of(egress.country)`, `languages[0]` thuộc ngôn ngữ phổ biến của vùng.
6. Chạy Chromium; nếu bước nào lỗi ⇒ không mở.

## 4. Task

### Task N1: Mô hình `EgressInfo` và quy tắc địa lý
**Files:** Create: `tools/kr/egress.py`, `corpus/locales/geo_to_locale.json`, `tools/kr/tests/test_egress.py`
**Interfaces:** Produces `EgressInfo(ip, asn, country, region, city, tz, rtt_ms, ip_class)`; `locales_for(country) -> list[Locale]`.
- [ ] Test `test_locale_matches_egress_geo` (Review Focus 3): 50 quốc gia ⇒ generator chỉ sinh timezone/ngôn ngữ nằm trong tập hợp lệ.
- [ ] Viết ⇒ PASS. Commit `kr: net: egress model`.

### Task N2: `kr-gateway`
**Files:** Create: `tools/kr/gateway.py`, `tools/kr/secrets.py`, `tools/kr/tests/test_gateway.py`
**Interfaces:** Produces `Gateway(upstream: Upstream).start() -> int(port)`, `.stop()`, `.health() -> bool`; `Upstream(kind, host, port, user_ref)`.
- [ ] Test với upstream giả (server SOCKS5/HTTP cục bộ): `test_forwards_tcp`, `test_remote_dns` (tên miền không bị phân giải cục bộ), `test_auth_to_upstream`.
- [ ] Test `test_kill_switch` (Review Focus 2): tắt upstream ⇒ cổng cục bộ đóng trong <= 1 giây, kết nối mới bị từ chối.
- [ ] Test `test_no_secret_leak` (Review Focus 5): mật khẩu không xuất hiện trong dòng lệnh tiến trình, log, biến môi trường con.
- [ ] Commit `kr: net: gateway with kill switch`.

### Task N3: Tường lửa và cờ Chromium
**Files:** Create: `scripts/fw-rules.ps1`, `tools/kr/chrome_flags.py`, `tools/kr/tests/test_no_direct_egress.py`
**Interfaces:** Produces `chrome_flags(port) -> list[str]` gồm proxy, `--disable-quic`, tắt Safe Browsing/prefetch/captive-portal/component update/translate-ui, `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`, `--disable-features=...` (danh sách chốt theo phiên bản ghim, kiểm lại bằng `chrome://flags` và mã nguồn).
- [ ] Test `test_no_direct_egress` (Review Focus 1): bật bắt gói (Windows `pktmon`) khi chạy trang thử WebRTC/QUIC/DNS/IPv6/ảnh từ nhiều domain ⇒ **không** có gói nào từ `chrome.exe` tới địa chỉ khác `127.0.0.1:PORT`.
- [ ] Test `test_ipv6_blocked`.
- [ ] Commit `kr: net: firewall rules and chrome flags`.

### Task N4: Pool proxy và ràng buộc 1 IP ↔ 1 profile
**Files:** Create: `tools/kr/proxy_pool.py`, `tools/kr/db.py` (SQLite), test.
**Interfaces:** Produces `ProxyPool.add(...)`, `.check(proxy) -> HealthReport(latency, ip, class, reputation_flag)`, `.lease(profile_id) -> Proxy`, `.release(profile_id)`.
- [ ] Test `test_one_ip_one_profile` (Review Focus 4): lease cùng IP hai lần cho hai profile khác nhau ⇒ lỗi.
- [ ] Test `test_dead_proxy_not_leased`, `test_lease_released_on_exit`.
- [ ] Commit `kr: net: proxy pool`.

### Task N5 (tích hợp T13/T14): kiểm tra phía engine
- [ ] Hoàn tất T13 (WebRTC) và T14 (TLS/H2 ngang bằng stock); thêm test harness `test_leaks.py` gọi N3.

**Giá trị TLS/H2 chuẩn Chrome 157 (verified từ HSW reverse engineering, `hcaptcha.js:273-288`):**
- **JA3 extensions:** SNI (0) luôn đầu, padding (21) luôn cuối, 14 extension giữa shuffle ngẫu nhiên mỗi session (Chrome 110+ behavior): `[23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 43, 27, 17513]`
- **JA3 ciphers:** `4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53`
- **JA3 curves:** `29-23-24`
- **H2 SETTINGS:** `1:65536;2:0;3:1000;4:6291456;6:262144` (HEADER_TABLE_SIZE:65536, ENABLE_PUSH:0, MAX_CONCURRENT_STREAMS:1000, INITIAL_WINDOW_SIZE:6291456, MAX_HEADER_LIST_SIZE:262144)
- **H2 WINDOW_UPDATE:** `15663105`
- **H2 PRIORITY:** `m,s,a,p` (method, scheme, authority, path)
- **Tổng h2fp:** `1:65536;2:0;3:1000;4:6291456;6:262144|15663105|0|m,s,a,p`
- T14 test harness PHẢI verify các giá trị trên bằng TLS/H2 server cục bộ.

**Lưu ý TLS mismatch trap (verified):** Nếu kernel-r dùng libcurl/native HTTP từ C++ cho bất kỳ request nào (vd: proxy probe, preflight), JA3 sẽ KHÁC Chrome → server so sánh TLS fingerprint giữa các request cùng session sẽ phát hiện. Giải pháp: MỌI request ra ngoài phải đi qua Chrome network stack hoặc có JA3 matching.

---

## 5. Manager UI (nội bộ)

**Kiến trúc:** tiến trình `kr-manager` (FastAPI) lắng nghe `127.0.0.1:7777`; SQLite lưu profile, proxy, lịch sử; giao diện là trang tĩnh HTML + một ít JS (không framework nặng). Token cục bộ trong header để trang web khác không gọi được API (chống CSRF/DNS rebinding: kiểm `Host` và `Origin`).

**Chức năng (tối thiểu có ích):**
| Màn hình | Nội dung |
|---|---|
| Profiles | Danh sách; nút Tạo, Chạy, Dừng, Nhân bản, Xoá; nhãn `ephemeral/persistent`; cột IP/quốc gia/timezone/GPU/UA rút gọn |
| Chi tiết profile | Toàn bộ `profile.json` (chỉ đọc) + biểu đồ nhất quán (kết quả Validator) + ghi chú |
| Proxies | Thêm/nhập hàng loạt, kiểm tra sức khoẻ, gán/giải phóng, cảnh báo IP trùng |
| Chạy | Mở N phiên cùng lúc, trạng thái từng phiên (cổng gateway, byte, cảnh báo rò rỉ) |
| Kiểm tra | Nút "Self-check": chạy harness P1-P10 trên profile đó và hiện kết quả |
| Cài đặt | Đường dẫn Chromium, chế độ VM, mặc định noise/proxy |

**Dữ liệu (SQLite):** `profiles(id, name, mode, seed, profile_json, created, last_run)`, `proxies(id, kind, host, port, secret_ref, ip, country, asn, ip_class, status)`, `leases(proxy_id, profile_id, since)`, `runs(id, profile_id, start, end, egress_ip, flags_json, result_json)`.

### Task M1: API lõi
**Files:** Create: `tools/kr/manager/{app,models,services}.py`, `tests/test_api.py`
- [ ] Test: `POST /profiles` (sinh + validate), `POST /profiles/{id}/run` (preflight → gateway → chrome), `POST /runs/{id}/stop`, `GET /proxies/health`.
- [ ] Test bảo mật: yêu cầu thiếu token ⇒ 401; `Host` lạ ⇒ 403; chỉ bind loopback.
- [ ] Commit `kr: ui: manager api`.

### Task M2: Giao diện
**Files:** Create: `ui/{index.html,app.js,style.css}`
- [ ] Viết các màn hình bảng trên bằng HTML/JS thuần, gọi API; trạng thái làm mới mỗi 2 giây (polling, không websocket).
- [ ] Test Playwright `ui/tests/test_ui.py`: tạo profile → chạy → thấy trạng thái "running" → dừng.
- [ ] Commit `kr: ui: web ui`.

### Task M3: Tích hợp VM (sau Phase 2)
- [ ] Thêm tuỳ chọn "Chạy trong VM": gọi `orchestrator.start(seed)`; gateway chạy trên host, VM chỉ thấy gateway qua vSwitch nội bộ.

## 6. Tiêu chí hoàn thành
- [ ] `test_no_direct_egress`, `test_kill_switch`, `test_one_ip_one_profile`, `test_locale_matches_egress_geo`, `test_no_secret_leak` đều xanh.
- [ ] Mở 3 phiên song song, 3 IP khác nhau, 3 profile khác nhau, mỗi phiên timezone/ngôn ngữ khớp IP.
- [ ] UI tạo/chạy/dừng/xoá được; đóng phiên là mất sạch dữ liệu (ephemeral).

## 7. Giới hạn cần biết
Proxy chỉ che IP và đường truyền. Nó không đổi được: loại IP (trung tâm dữ liệu hay nhà dân), danh tiếng IP, hay hành vi người dùng. Hai yếu tố đầu phụ thuộc nguồn proxy bạn mua. Dùng proxy hợp lệ, đúng điều khoản của nhà cung cấp và nền tảng đích.
