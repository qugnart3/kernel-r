# Kế hoạch: UDP đi qua proxy ở tầng hệ điều hành (hướng 3)

Trạng thái: CHỈ LÀ KẾ HOẠCH, chưa làm gì. Ngày 2026-11-01.

## Mục đích và phạm vi
Tránh rò rỉ IP thật qua UDP (WebRTC/STUN, QUIC) khi dùng proxy có hỗ trợ UDP. Không nhằm làm proxy khó bị phát hiện bởi trang kiểm tra:
việc đó ngoài phạm vi Kernel-R.

## Hiện trạng đã đo (commit 8f8ae3e)
- Proxy hiện tại là HTTP, không có UDP. Luật tường lửa `Kernel-R: block direct egress of chrome.exe` chặn mọi giao thức ra ngoài loopback;
  `harness/check_udp_leak.py`: Dev không có ứng viên srflx, Dev-direct có.
- Hướng 3 chỉ có ý nghĩa khi UDP phải ĐI QUA proxy (không chỉ bị chặn).

## Điều kiện cần (chưa có)
1. Proxy SOCKS5 có UDP ASSOCIATE. Kiểm bằng cách gửi `05 03 00 01 00 00 00 00 00 00` sau khi xác thực: trả `05 00` là hỗ trợ.
   Bước 0 (không cần admin): mở rộng `proxy_probe` để báo `udp: true/false`.
2. Quyền admin và chấp nhận một thành phần nhân của bên thứ ba đã ký (Wintun của WireGuard, hoặc WinDivert). Mình không viết hay ký driver.

## Phương án (chọn một sau khi có điều kiện 1)
- A. Máy ảo (khuyến nghị): thư mục `vm/` đã có. Trình duyệt chạy trong VM, VM có TUN riêng (wintun + tun2socks trỏ vào SOCKS5-UDP), máy chủ
  không đổi route. Cô lập theo từng "PC", không ảnh hưởng ứng dụng khác.
- B. Máy thật, theo tiến trình bằng WinDivert: chuyển hướng gói của cây tiến trình chrome (nhận PID ở lớp FLOW) vào tun2socks cục bộ. Phức tạp, dễ
  hỏng khi Chrome tạo tiến trình mới; cần admin lúc chạy.
- C. TUN toàn máy (wintun + tun2socks + route mặc định): LOẠI, vì đẩy cả máy (gateway, Manager, ứng dụng khác) qua proxy.

## Các bước (phương án A)
0. `proxy_probe` báo `udp`; test đơn vị bằng máy chủ SOCKS5 giả.
1. Dựng VM mẫu: wintun + tun2socks, route mặc định qua TUN, luật chặn mọi đường khác trong VM (chống rò khi TUN rớt).
2. Kill-switch: tắt tun2socks => không có gói nào ra (đo).
3. Tích hợp vào `vm/` và `session` (cờ chọn "UDP qua proxy" chỉ bật khi `proxy_probe` báo udp).
4. Ghi CHANGELOG, đặc tả §8, NOTES; commit theo CLAUDE.md.

## Tiêu chí đạt
- `check_udp_leak.py` (phiên bản trong VM): có srflx và IP srflx == IP thoát của proxy, KHÔNG phải IP thật.
- `check_proxy_leaks.py`: 0 kết nối trực tiếp (TCP+UDP); kill-switch OK; IPv6 không thoát.
- Không đo được thì ghi "chưa kiểm chứng", không suy ra.

## Rủi ro
Thành phần nhân bên thứ ba; UDP qua proxy làm tăng độ trễ; nhiều proxy dân cư không hỗ trợ UDP ASSOCIATE.
