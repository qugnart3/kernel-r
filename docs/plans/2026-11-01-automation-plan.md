# Kernel-R: Kịch bản thao tác trong trình duyệt (C++, không CDP)

Spec: `2026-10-29-design-spec.md` (quyết định D31). Trạng thái: **ĐÃ HOÀN THÀNH S1, A1-A6 (2026-11-01)**; xem từng task bên dưới và `docs/automation.md`.

**Goal:** Người dùng gửi một kịch bản JSON cho một profile đang chạy; tiến trình browser của Chromium thực thi bằng API nội bộ. Không `--remote-debugging-port`, không DevTools agent, không Playwright/CDP.

**Vì sao:** `NOTES.md` đã ghi hai điều: cổng CDP `=0` làm `navigator.webdriver=true`, và Playwright qua CDP để lại dấu. Đường này bỏ cả hai.

**Global Constraints:** Patch nhỏ, tách module (G6). Không thêm phụ thuộc Python. Không hook JS vào trang (G5). Không mô phỏng dáng chuột người, không nhiễu ngẫu nhiên (xem mục 5). Phạm vi QA / quản lý tài khoản hợp lệ (`README.md`).

---

## 1. Đối chiếu danh sách hàm được đề xuất

Đã kiểm trên cây Chromium 157 (`C:\src\chromium\src`). Kết luận từng nhóm:

| Nhóm đề xuất | Kết luận | Lý do / thay bằng |
|---|---|---|
| 1. Tab/frame: `AttachTab`, `ForEachFrame`, `OnFrameCreated/Deleted` | **Giữ một phần** | `ForEachRenderFrameHost` có trong `content/public` (web_contents.h:616). Không cần theo dõi tạo/xoá frame liên tục: liệt kê khi cần. Chỉ giữ một `WebContentsObserver` cho tab đang điều khiển (đợi tải xong, tab đóng). |
| 2. Input: `ForwardMouse/Keyboard/WheelEvent` | **Giữ, sửa cách định tuyến** | Hàm có trong `render_widget_host.h:183-192`, nhưng gọi trên widget của main frame **không tự định tuyến vào iframe khác origin**. Bản đề xuất nói "gọi thẳng RenderFrameHost của frame" là chưa đủ: định tuyến OOPIF do `RenderWidgetHostInputEventRouter` làm, và `content/public` không lộ nó (grep không thấy). Xem spike S1. |
| 2. `Drag` bằng `SyntheticSmoothDragGesture` | **Bỏ khỏi bản đầu** | Nằm trong `content/browser/`, `chrome/` không được include (DEPS). Drag làm bằng chuỗi Down, nhiều Move, Up. |
| 2. `TransformToRoot` | **Giữ** | `RenderWidgetHostView::TransformPointToRootCoordSpaceF` (public). |
| 3. Query/GetRect/ElementFromPoint/Viewport/ObserveMutations trong **Blink** qua Mojo | **THAY** | Cần interface Mojo mới giữa browser và renderer, mã trong `third_party/blink/`, patch lớn, khó rebase. Thay bằng `RenderFrameHost::ExecuteJavaScriptInIsolatedWorld` (render_frame_host.h:624, public): một đoạn JS trong world riêng chạy `querySelector`, `getBoundingClientRect`, `elementFromPoint`, `visualViewport` rồi trả JSON. Trang không thấy world này. Cùng kết quả cho nhu cầu kịch bản, 0 dòng Blink. |
| 3. `Eval(script)` | **Giữ, mặc định isolated** | Chạy ở main world (`ExecuteJavaScript`) thì trang có thể quan sát tác dụng phụ; chỉ cho khi script ghi rõ `"world":"main"`. |
| 3. `ObserveMutations` | **Bỏ** | Thay bằng op `wait_for` (poll selector trong isolated world). Không cần callback liên tục. |
| 4. Mạng: `URLLoaderThrottle`, `GetResponseBody` | **Hoãn (Phase B)** | Cần hook ở `ChromeContentBrowserClient::CreateURLLoaderThrottles` và giữ thân phản hồi: patch lớn. `WebContentsObserver::ResourceLoadComplete` **không còn trong 157** (grep rỗng). Bản đầu chỉ có `wait_for_load`. Nếu thật sự cần chờ một request cụ thể, làm `NavigationThrottle`/`DidFinishNavigation` cho điều hướng và thử phương án khác cho XHR sau. |
| 5. Ảnh: `CopyFromSurface` | **Giữ** | `render_widget_host_view.h` (public). Encode PNG bằng `gfx::PNGCodec`. |
| 5. `ReadCanvas(element)` | **Bỏ** | Đọc canvas qua isolated-world `toDataURL` là đủ và đi qua đường nhiễu canvas đã có (D27, D28). Cần biết: kết quả chịu nhiễu canvas của profile. |
| Lời tuyên bố không thêm nhiễu/dáng chuột người | **Giữ nguyên** | Đồng ý; xem mục 5. |

## 2. Kiến trúc

```
Manager (Python) ──named pipe, JSON từng dòng──► chrome.exe (browser process)
  profile_id → {run_id, pipe}                        chrome/browser/kr_automation/
                                                       PipeServer (thread IO) ──PostTask──► UI thread
                                                       ScriptRunner: chạy từng bước tuần tự
                                                       Ops: goto, click, type, key, scroll, wait_for, eval, screenshot
```

- **Vị trí mã: `chrome/browser/kr_automation/`**, KHÔNG phải `components/`. `components/kr_fingerprint` có `DEPS` cấm `-content -chrome`; còn automation phải dùng `WebContents`/`BrowserList`. (Sửa so với lời đề xuất trước đó trong chat là đặt ở `components/`.)
- **Tab đích:** `BrowserList` → `tab_strip_model()->GetActiveWebContents()`; lệnh có thể kèm `tab` (chỉ số) ở bản sau.
- **Kênh:** named pipe `\\.\pipe\kr-ctl-<run_id>-<128-bit token>`, tạo bởi browser, `PIPE_REJECT_REMOTE_CLIENTS`, DACL chỉ user hiện tại. Không mở cổng TCP.
- **Cờ:** `--kr-control-pipe=<tên>`; thêm vào `CommandLineStringForDisplay` để ẩn khỏi `chrome://version` (D22). Chỉ có mặt khi Manager chạy với `script=true`; không có cờ thì không tạo pipe và không có mã nào chạy.
- **Giao thức:** mỗi dòng một JSON `{"id":N,"op":"click","frame":"main","selector":"#login"}` (`frame` mặc định `"main"`) → trả `{"id":N,"ok":true,...}` hoặc `{"id":N,"ok":false,"error":"..."}`. Kịch bản = mảng các op; Manager gửi từng op (để dừng/gỡ lỗi từng bước), có `timeout_ms` mỗi op.
- **Manager:** `POST /api/runs/{run_id}/script` (kịch bản) và dùng lại bảng `sessions` có sẵn trong `manager.py` (thêm khoá `pipe`). Cùng cơ chế guard/token hiện có. Lệnh CLI `kr run` chỉ gọi API này (một nơi giữ ánh xạ).

## 3. Các op bản đầu

| Op | Làm gì | API |
|---|---|---|
| `goto` | điều hướng, đợi tải | `NavigationController::LoadURLWithParams` + `DidStopLoading` |
| `wait_for` | đợi selector xuất hiện / hiển thị | poll isolated world mỗi 100 ms tới `timeout_ms` |
| `click` | cuộn phần tử vào view, lấy rect (cộng offset iframe cùng origin, nhân DPR), gửi Move/Down/Up ở giữa rect | isolated JS + `ForwardMouseEvent`; `isTrusted=true` |
| `type` | gõ text vào phần tử đang focus (có thể kèm selector để click trước) | `ForwardKeyboardEvent` (RawKeyDown/Char/KeyUp) |
| `key` | phím đơn: Enter, Tab, Escape, mũi tên | như trên |
| `scroll` | cuộn theo delta | `ForwardWheelEvent` |
| `eval` | chạy THÂN HÀM JS (dùng `return`), trả giá trị JSON | chỉ isolated (main world không có trong API public, xem A2) |
| `frames` | liệt kê frame: id, url, origin, cross_process | `ForEachRenderFrameHost` |
| `screenshot` | PNG base64 | `CopyFromSurface` + `PNGCodec` |
| `sleep` | chờ cố định (người viết kịch bản tự chọn) | timer |

Chưa làm ở bản đầu: drag, touch, upload file, hộp thoại JS, nhiều tab, iframe khác origin (phụ thuộc S1), chặn/đọc mạng.

## 4. Task

Trạng thái: `[ ]` chưa, `[x]` xong. Mọi task theo `CLAUDE.md` mục 1 (test → chrome.exe thật → CHANGELOG → commit).

- [x] **S1 (spike): định tuyến input vào iframe khác origin. KẾT QUẢ (2026-11-01, chỉ đọc mã, CHƯA chạy thử): KHÔNG định tuyến được bằng API public.** `RenderWidgetHostImpl::ForwardMouseEvent` (render_widget_host_impl.cc:1697) đưa sự kiện thẳng tới widget được gọi, không qua router. DevTools định tuyến bằng `widget_host->GetInputEventRouter()` (input_handler.cc:1404, 1451, 1706), thuộc `components/input`/`content/browser`, không có trong `content/public`. Chọn phương án (a): bản đầu chỉ main frame + iframe cùng origin, OOPIF trả `unsupported_cross_origin_frame`. Phương án (b) (cầu nối nhỏ trong `content/browser/`) để sau nếu cần. Kết luận sẽ được xác nhận bằng thực nghiệm ở A3 (ca iframe khác origin phải trả đúng lỗi).
- [x] **A1: khung `kr_automation` + cờ + pipe (xong 2026-11-01).** `chrome/browser/kr_automation/` (protocol, pipe_server, kr_automation), cờ `--kr-control-pipe` (gỡ khỏi dòng lệnh trong bộ nhớ, ẩn khỏi chuỗi hiển thị), pipe một-khách DACL chủ sở hữu, `ping`/`unknown_op`. Đã kiểm: `kr_automation_unittests` 10/10, `harness/check_automation_pipe.py` 14/14 trên chrome.exe thật (đang bật siết quyền D24). **Chưa kiểm:** DACL với người dùng khác. Commit Chromium f93e89308b, patch 0030.
- [x] **A2: `goto`, `wait_for`, `eval`, `screenshot`, `sleep`, `frames` (xong 2026-11-01).** `harness/check_automation_ops.py` 29/29 trên chrome.exe thật (headless; bản ghi đầu "30/30" là đếm nhầm). Khác kế hoạch: `eval` chỉ có world isolated (`ExecuteJavaScript` main world của content/public chỉ dùng được trên chrome:// và devtools://), có thêm op `frames` để lấy FrameId. Commit Chromium f51a692e06, patch 0031. Chưa kiểm: chế độ có cửa sổ; nội dung ảnh chụp (mới kiểm PNG hợp lệ + kích thước).
- [x] **A3: input `click`, `type`, `key`, `scroll` (xong 2026-11-01).** `harness/check_automation_input.py` 28/28 trên chrome.exe thật (headless, DPR giả 1.5): isTrusted, toạ độ trúng giữa nút (sai số <= 1 px) kể cả trong iframe cùng origin có viền, tiếng Việt có dấu, Ctrl+A/Tab/Backspace/Enter/ArrowLeft, cuộn hai chiều, che phủ -> `element_obscured`, OOPIF -> `unsupported_cross_origin_frame` (xác nhận kết luận S1 bằng thực nghiệm). Giới hạn: ký tự ngoài ASCII chỉ sinh keypress (không keydown/keyup); emoji bị từ chối `unsupported_char`; chưa có chuột phải/kéo-thả/cảm ứng; giả định zoom 100%. Commit Chromium 3e6fecbb6e, patch 0032.
- [x] **A4: Manager + chạy song song (xong 2026-11-01).** `Manager.run(script=True)`, `Manager.script`, `Manager.script_batch`, API `POST /api/runs/{id}/script` và `POST /api/script/batch`, client Python `tools/kr/automation.py`. 13 test pytest mới (client giả), tổng 148 đạt. **Khác kế hoạch:** KHÔNG làm lệnh `kr run` (nạp file) theo quyết định mục 6 (để sau); thêm `automation.RUN_FLAGS` (xem A4b).
- [x] **A4b: kiểm song song trên chrome.exe thật (xong 2026-11-01).** `harness/check_automation_parallel.py` qua Manager thật, CÓ CỬA SỔ: 3 và 8 trình duyệt cùng lúc đạt; `sleep 1.5 s` trên n trình duyệt xong trong 1.50 s (tuần tự sẽ n x 1.5 s); mỗi trình duyệt chỉ nhận chữ của chính nó, mọi event isTrusted; dừng #0 thì #0 báo lỗi rõ và các trình duyệt khác vẫn chạy. **Phát hiện:** không có cờ, cửa sổ bị che nhận lệnh `ok` nhưng trang KHÔNG nhận input (3 trình duyệt: 2 hỏng; 8 trình duyệt: 7 hỏng); thêm `--disable-features=CalculateNativeWinOcclusion --disable-backgrounding-occluded-windows --disable-renderer-backgrounding` cho lượt chạy script thì hết (chưa tách xem cờ nào là then chốt). Giới hạn đã thử: 8 cửa sổ; chưa thử nhiều hơn.
- [x] **A5: kiểm "không để lại dấu" (xong 2026-11-01).** `harness/check_automation_leaks.py`, có cửa sổ, cùng seed, so TẮT với BẬT (pipe + RUN_FLAGS + chạy goto/click/type/scroll/eval): `navigator.webdriver` false; không `--remote-debugging` trên dòng lệnh; không có cổng TCP nghe nào trong cây tiến trình (cả hai); ảnh chụp 25+ chỉ số trang đọc được (biến global của window/document, prototype navigator, chuỗi toString của hàm native, kích thước màn hình/cửa sổ, hash canvas, visibilityState, hasFocus, Worker...) GIỐNG HỆT giữa TẮT và BẬT (trừ kết quả của chính kịch bản); mọi sự kiện chuột/phím đều isTrusted, pointerType=mouse. **KHÔNG kiểm được / không khẳng định:** hành vi thời gian và hình dạng chuỗi sự kiện so với chuột thật (op click gửi move->down->up tức thời, toạ độ luôn đúng tâm phần tử; pointerdown có detail=0, mousedown detail=1 là mặc định của Chrome); chưa so trực tiếp với chuột thật bằng SendInput. Sự cố chưa giải thích: 1 lần trong ~15 lần chạy harness (bản cũ, chờ cố định 3 s), ảnh chụp chỉ có sự kiện move, ô nhập rỗng, scrollY=0 (op báo ok); 14 lần sau đó đạt; harness giờ in kết quả op + đọc DOM + visibility/hasFocus để bắt lại.
- [x] **A6: tài liệu (xong 2026-11-01).** `docs/automation.md` (cú pháp op, mã lỗi, ví dụ, giới hạn, bảng lệnh kiểm thử), `docs/manager.md` mục kịch bản, spec D31 cập nhật trạng thái thực tế, CHANGELOG, NOTES.

Mỗi task Chromium: commit ở `C:\src\chromium\src` rồi `scripts/export.ps1`; không sửa tay `.patch`. Build theo `scripts/build.ps1` (đóng mọi chrome.exe trước, chạy `fix-sandbox-acl.ps1` nếu ra thư mục mới, `sync_direct` sau build).

- [x] **A7: so với chuột/bàn phím THẬT + tìm ra và sửa nguyên nhân input bị bỏ (xong 2026-11-01).** `harness/check_automation_realinput.py` (SendInput thật, có chốt an toàn). So sánh: cùng trang, op click+type của bộ điều khiển và input thật cho CÙNG chuỗi sự kiện, CÙNG giá trị mọi trường (isTrusted, pointerType, pointerId, button(s), detail, pressure, width/height, key/code/keyCode/charCode, inputType...) và CÙNG toạ độ client/screen ở cả cửa sổ phóng to lẫn thường; khác duy nhất `movementX/Y` của lần di chuột đầu (scripted tính từ con trỏ OS còn sót, thật là 0) và chuột thật đôi khi có thêm một mousemove nhỏ giữa down và up. **KHÔNG so được:** thời gian giữa sự kiện và đường đi chuột (scripted: một bước nhảy; thật: nhiều bước). **Nguyên nhân gốc input bị bỏ (đã chứng minh):** `Focus()` gửi SetFocus qua kênh mojo KHÁC kênh input; `document.hasFocus()` là false ngay sau khi mở cửa sổ (40/40 lần), nên sự kiện focus có thể xen giữa mousemove và mousedown và Blink bỏ mousedown (mouseup vẫn tới; browser thấy ack MouseDown kNotConsumed trước ack MouseMove). Cùng điều kiện (sự kiện dồn một lượt, không chốt chặn): chờ focus 0/40, không chờ 14/40. **Sửa:** trước mỗi op input gọi Focus() rồi đợi renderer báo `hasFocus()` (poll 10 ms, tối đa ~2 s; nếu không bao giờ có focus thì nhớ và thôi chờ). Sau sửa: 1/200 lần hỏng (1 lần chưa giải thích, không bắt được). Đã bỏ chốt chặn 400 ms (heuristic); giữ nhịp click move->40 ms->down->30 ms->up. Commit Chromium 7e9145d5db, patch 0034 (8d2014d572 / patch 0033 là bước giảm nhẹ trung gian).

- [x] **A8: nút script trong UI Manager (xong 2026-11-01).** `ui/index.html`: nút "Chạy + kịch bản", khung nhập kịch bản (JSON), thẻ kết quả theo trình duyệt (từng bước, `eval`, ảnh chụp), chọn phiên dùng chung với khung CDP. Kiểm: `check_manager_ui.py` 43 check (client script giả: JSON hỏng, thiếu `op`, dừng khi lỗi bật/tắt, HTML trong kết quả không thực thi, lựa chọn giữ qua làm mới); `check_script_ui_e2e.py` 8 check ĐẦU-CUỐI THẬT (UI do Chrome headless điều khiển, 2 trình duyệt kr có cửa sổ, kiểm lại độc lập trên 2 trang), chạy 3/3 lần đạt. Chỉ phía Python/UI, không đổi Chromium.

- [x] **A9: zoom khác 100% + UI nâng cấp (xong 2026-11-01).** Tái hiện trước khi sửa: `harness/check_automation_zoom.py` cho thấy ở zoom 120%/144%/83% click trượt (chỉ 1/3 hoặc 0/3 nút trúng, sai tới 72-99 px) vì toạ độ CSS px bị gửi thẳng làm toạ độ widget (DIP). Sửa: toạ độ widget = CSS px x hệ số zoom (`HostZoomMap::GetZoomLevel` + `ZoomLevelToZoomFactor`), gốc màn hình tính từ kích thước cửa sổ quy về DIP. Sau sửa: 4 mức zoom (100/120/144/83%) click trúng 3/3, sai số <= 1 px; so với chuột thật ở 120% và 83%: cùng `client`, cùng `screen`. Commit Chromium a0b2f2f3f4; patch 0035. UI Manager: kết quả hiện từng bước ngay khi có (mỗi bước một lời gọi API), nút huỷ, kịch bản dạng đối tượng {số lượt: bước} (bước riêng cho từng trình duyệt), lưu/tải/xoá kịch bản (localStorage), bấm ảnh để phóng to. Manager: không in traceback khi trình duyệt đóng kết nối giữa chừng.

- [x] **A10: xử lý các mục "chưa kiểm chứng" còn lại (xong 2026-11-01).** DACL của pipe (`check_automation_acl.py`): `D:P(A;;FA;;;OW)`, một ACE, không Everyone/Anonymous/Users/AU; tiến trình cùng người dùng ở mức toàn vẹn Thấp bị từ chối (Permission denied) còn tiến trình thường nối được. Nhiều cửa sổ: 16, 24, 32 trình duyệt đạt (RAM trống tụt còn 87 MB ở 32: giới hạn thực là bộ nhớ). Tách cờ `RUN_FLAGS`: bỏ `--disable-renderer-backgrounding` (vô dụng, 0/2); hai cờ còn lại mỗi cờ một mình đủ (2/2), bản 2 cờ đạt 8/8 ở n=8. Tác động lên trang: cửa sổ bị che vẫn visible và ~180 khung/giây (không cờ: hidden, 0 khung). Sửa lỗi cũ `direct_is_stale()` (debug.log ở cả Dev và Dev-direct bị coi là bản cũ, Manager từ chối mở phiên thứ 10). Săn lần hỏng input còn lại: 0/300 với mã hiện tại (tổng 1/500). **Không làm:** mô phỏng nhịp/đường đi chuột như người (ngoài phạm vi: chỉ phục vụ qua mặt phát hiện).

- [x] **A11: op `move` (di chuyển con trỏ xác định) (xong 2026-11-01).** Theo lựa chọn của người dùng: bản XÁC ĐỊNH, không ngẫu nhiên. Nội suy tuyến tính hoặc ease-in-out qua `steps` bước trong `duration_ms`, từ vị trí con trỏ hiện tại tới phần tử hoặc (x,y); `trace` trả đường đi đã tính. Lần đầu (chưa biết điểm xuất phát) chỉ gửi MỘT sự kiện. `harness/check_automation_move.py` 56 check x 3 lần đạt (zoom 100% và 120%): số sự kiện, đều bước (tuyến tính), chậm-nhanh-chậm đối xứng (ease), thời lượng, xác định (so từng số), hover menu `:hover` thật, `mouseout`, toạ độ x,y, 9 lỗi tham số. Phát hiện: Blink gộp `mousemove` trong một khung hình nên bước cách nhau < ~25 ms bị gộp (40 bước/100 ms: trang nhận 21-22). Không làm: mô phỏng chuyển động người (ngẫu nhiên/rung/Bézier tự nhiên): ngoài phạm vi (chỉ phục vụ qua mặt phát hiện). Chưa làm: `drag`.

- [x] **A12: op `drag` (xong 2026-11-02).** Nhấn tại nguồn, di chuyển nội suy xác định khi giữ nút, thả tại đích; hai đầu không tự cuộn; lỗi luôn xảy ra trước khi nhấn. `harness/check_automation_drag.py` 50 check (zoom 100% và 120%) + 2 check so với kéo bằng chuột THẬT (SendInput): thanh trượt, thả vào vùng đích, canvas, trace xác định, 10 lỗi tham số, `draggable=true` không làm treo; chạy 3/3 lần đạt. Phát hiện: cửa sổ tự sinh `mousemove` theo con trỏ OS thật làm thanh trượt nhảy tới cuối giữa lúc kéo; sửa bằng `AddMouseEventCallback` nuốt sự kiện chuột không phải của mình trong lúc kéo. Không hỗ trợ kéo-thả HTML5 gốc (`drop` không tới). Commit Chromium 115a7e9c0c; patch 0038.

## 5. Rủi ro và giới hạn (nói thẳng)

1. **Dấu hiệu hành vi vẫn có thể bị nhận ra.** Bỏ CDP không làm nhịp click, thời gian giữa các thao tác, toạ độ luôn đúng giữa phần tử trở nên giống người. Không hứa "không bị phát hiện". Không có mô phỏng dáng chuột người trong kế hoạch này; muốn trễ thì người viết kịch bản dùng `sleep`.
2. **Isolated world không đọc được biến JS của trang**, và KHÔNG có đường vào main world qua API public (đã đo ở A2: `main_world_unsupported`). Cần đọc biến của trang thì phải vá C++ (ngoài phạm vi hiện tại).
3. **S1 chưa chắc thành công**: nếu `content/public` không đủ cho OOPIF, phải thêm cầu nối nhỏ vào `content/browser/` hoặc bỏ iframe khác origin khỏi phạm vi.
4. **Pipe không chống được tiến trình cùng user có quyền cao** đọc dòng lệnh browser để lấy tên pipe (D23/D24 cũng chỉ chống một phần). Giảm: ẩn cờ khỏi giao diện, token 128-bit, DACL; tiến trình con dùng lại DACL siết của D24.
5. **DACL tiến trình đã siết (D24)** có thể ảnh hưởng tới đọc/ghi pipe từ Manager hoặc `CopyFromSurface`; sẽ lộ ra ở A1/A2.
6. **Rebase**: dùng toàn API `content/public` nên phần lớn ổn định, nhưng chữ ký `ExecuteJavaScriptInIsolatedWorld`, `ForwardMouseEvent` có thể đổi giữa các bản; cần chạy lại A3 sau mỗi lần nâng bản (thêm vào `rebase.ps1` checklist).
7. **Nhiễu canvas** (D27/D28) vẫn áp vào dữ liệu canvas mà kịch bản đọc.
8. **motionData fingerprint (verified từ HSW reverse engineering).** hCaptcha thu thập motionData
   chi tiết gồm: `mm` (mouse move: `[[x,y,ts],...]`), `md` (mouse down), `mu` (mouse up),
   `kd` (key down), `ku` (key up), mỗi nhóm có `*-mp` (meanPeriod giữa các event), và
   `topLevel.nv.webdriver` (phải = false). Cấu trúc verified từ `hcaptcha.js:127-235`.
   **Ý nghĩa cho automation:** op `click` gửi move→down→up tức thời (khoảng cách thời gian
   ~70ms), toạ độ luôn đúng giữa phần tử → pattern dễ nhận biết qua motionData. op `move` có
   nội suy nhưng vẫn xác định. Đây là giới hạn CỐ Ý (mục 5.1) — kịch bản viết bằng tay dùng
   `sleep` và `move` để tạo nhịp tự nhiên hơn nếu cần. kernel-r KHÔNG tự thêm noise/jitter
   vào timing (policy G5).
9. **`topLevel.nv.webdriver` trong motionData (verified).** hCaptcha đọc
   `navigator.webdriver` và gửi trong `topLevel.nv.webdriver`. kernel-r đặt `webdriver=false`
   (verified A5) nên field này = false. Nếu bất kỳ cờ Chrome nào (vd: bản debug cũ có
   `--enable-automation`) set `webdriver=true`, motionData sẽ leak.

## 6. Quyết định của người duyệt (2026-11-01)

1. **Phạm vi frame:** nếu S1 thất bại, bản đầu chỉ main frame + iframe cùng origin. Điều kiện kèm theo:
   - Gặp OOPIF thì trả lỗi rõ `kUnsupportedCrossOriginFrame` (JSON: `"error":"unsupported_cross_origin_frame"`), không im lặng thất bại.
   - Mọi op nhận tham số `frame` (FrameId) ngay từ đầu; mặc định là main frame. Thêm OOPIF sau không đổi API.
2. **Nạp kịch bản:** bản đầu chỉ gửi từng op qua API Manager. Chế độ nạp file khởi động rồi tự chạy để sau (chỉ là vòng lặp gọi từng op; chưa thiết kế định dạng file, xử lý lỗi giữa chừng, retry). Mỗi op phải có kết quả trả về để sau này lặp qua danh sách được.
   - Lưu ý trung thực: `goto`, `wait_for`, `eval` (đọc), `screenshot` gọi lại an toàn. `click`, `type`, `key` **không** idempotent theo nghĩa gọi lại cho cùng hiệu ứng (gọi hai lần là hai lần nhấn); kết quả trả về của chúng ghi rõ đã làm gì (toạ độ, phần tử trúng) để lớp trên tự quyết định có chạy lại không.
3. **Chạy song song nhiều profile: CẦN, có ngay ở bản đầu.** Mỗi lượt chạy một pipe nên không lẫn nhau; việc phải làm nằm ở Manager (task A4 bên dưới).
