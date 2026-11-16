# Git Workflow — Kernel-R Docs

## Repo này là gì
Chứa plans, docs, changelogs cho dự án Kernel-R (Chromium 158 fork).
**KHÔNG** chứa source code C++ — source ở `C:\src\chromium\src`.

## Quy tắc bắt buộc

### 1. Luôn push sau mỗi session làm việc
```powershell
cd C:\Users\h\Desktop\Build_Browser
git add -A
git commit -m "mô tả ngắn gọn"
git push
```
Không có ngoại lệ. Làm xong = push. Không để local-only.

### 2. Commit message format
```
[loại] mô tả ngắn

Ví dụ:
[plan] thêm plan WebRTC T13
[handover] cập nhật trạng thái T13 hoàn thành
[changelog] ghi nhận changes session 2026-11-16
[fix] sửa lỗi typo trong MASTER-PLAN
[docs] thêm GIT-WORKFLOW.md
```

Loại: `plan`, `handover`, `changelog`, `docs`, `fix`, `config`

### 3. Khi nào commit
- **Bắt đầu session**: pull trước khi làm
- **Kết thúc session**: commit + push tất cả thay đổi
- **Hoàn thành 1 task**: commit ngay (vd: xong T13 → update HANDOVER + CHANGELOG → commit → push)
- **Thay đổi quan trọng**: đừng đợi, commit luôn

### 4. Branching
Repo docs này đơn giản — làm trên `main` là đủ. Không cần feature branch cho docs.

## Setup lần đầu

### Tạo repo trên GitHub
1. Vào github.com → New repository
2. Tên: `kernel-r-docs` (hoặc tên bạn chọn)
3. Private repo
4. Không tạo README (đã có files local)

### Kết nối local → remote
```powershell
cd C:\Users\h\Desktop\Build_Browser
git init
git add -A
git commit -m "[docs] initial commit — plans, handover, changelog"
git branch -M main
git remote add origin https://github.com/USERNAME/kernel-r-docs.git
git push -u origin main
```

Thay `USERNAME` bằng GitHub username của bạn.

## Workflow hàng ngày

### Bắt đầu làm việc
```powershell
cd C:\Users\h\Desktop\Build_Browser
git pull
```

### Trong lúc làm
```powershell
# Sau mỗi thay đổi quan trọng
git add -A
git commit -m "[loại] mô tả"
```

### Kết thúc session
```powershell
git add -A
git commit -m "[loại] mô tả"
git push
```

## Cấu trúc thư mục
```
Build_Browser/
├── CLAUDE.md          # Instructions cho Claude
├── HANDOVER.md        # Trạng thái dự án, kiến trúc, task tracking
├── CHANGELOG.md       # Log mọi thay đổi
├── GIT-WORKFLOW.md    # File này
├── .gitignore
└── plans/
    ├── MASTER-PLAN.md
    ├── 2026-10-29-*.md    # Phase 1 plans
    ├── 2026-11-01-*.md    # Network/automation plans
    └── 2026-11-02-*.md    # Consistency/HSW plans
```
