# LogoDrop — Web chèn logo vào video (tối ưu cho iPhone)

Web tự động ghép logo PNG/JPG/WEBP vào **góc phải dưới** (hoặc **góc phải trên**) của video, giữ nguyên tỉ lệ, kích thước khung hình, thời lượng, và xuất **MP4 H.264** dễ mở trên iPhone. Chạy trên máy chủ cloud, **không cần bật PC** khi dùng.

## Video nào phù hợp?

- Nên dùng các clip ngắn được tạo bằng AI, khoảng 720p / 1080p, đầu vào MP4 hoặc MOV.
- Mặc định tối đa **150 MB/tệp** (có thể thay đổi trong Render bằng biến `MAX_UPLOAD_MB`, nhưng gói miễn phí có giới hạn tốc độ xử lý / bộ nhớ).
- Video gốc dọc 9:16, ngang 16:9, vuông 1:1 đều được giữ nguyên **tỉ lệ và độ phân giải hiển thị**. FPS nguồn được FFmpeg mặc định giữ theo timestamp; có thể dao động nhỏ do chuyển mã.
- Phần video được mã hóa bằng H.264, `CRF 18` (chất lượng cao); AAC đầu vào được giữ bằng **copy**, các codec audio khác đổi sang AAC 192 kb/s.
- **Không thể giữ y hệt từng bit hình ảnh sau khi chèn logo**, vì phải mã hóa lại video. Video HDR, 10-bit hoặc độ phân giải rất cao có thể thay đổi hiển thị / quá tải hosting miễn phí.

## Cách đưa web lên internet hoàn toàn miễn phí với GitHub + Render

Bạn chỉ cần thiết lập **một lần**. Sau đó mở link trên Safari của iPhone để dùng; không cần bật PC.

### A. Tạo repository trên GitHub

1. Mở https://github.com/ , đăng nhập, nhấn **New repository**.
2. Đặt tên, ví dụ `mobile-video-logo`; chọn **Private** để mã nguồn không công khai (Render cần quyền đọc repository khi liên kết).
3. Nhấn **Create repository**.
4. Giải nén file ZIP này. Ở GitHub, chọn **Add file → Upload files**, tải **các file trong thư mục `mobile-video-logo`** lên repository (bao gồm thư mục `static`). **Không upload một file ZIP duy nhất**.
5. Nhấn **Commit changes**.

> GitHub giao diện di động có thể khó upload cả thư mục. Nếu không có máy tính khi thiết lập lần đầu, có thể dùng Safari ở chế độ "Yêu cầu trang web cho máy tính"; tải file từng phần / dùng công cụ GitHub hỗ trợ quản lý repo. Khi đã deploy, chỉ cần dùng điện thoại.

### B. Deploy lên Render

1. Mở https://dashboard.render.com/ và đăng nhập (có thể dùng GitHub).
2. Chọn **New → Web Service**; kết nối repo `mobile-video-logo`.
3. Render sẽ phát hiện `Dockerfile`. Chọn **Language/Runtime: Docker**, **Instance Type: Free**.
4. Trong **Environment**, thêm biến `APP_PIN` = một mã bảo vệ do bạn tự đặt, ví dụ **một mã ngẫu nhiên riêng**. Không lưu mã này vào repository.
5. Có thể thêm `MAX_UPLOAD_MB=150` (nếu không thêm, app mặc định 150 MB).
6. Nhấn **Create Web Service / Deploy**. Khi build hoàn thành, Render cấp link dạng `https://mobile-video-logo-xxxx.onrender.com`.
7. Mở link này bằng Safari iPhone, nhập PIN rồi tải video lên.

**Cách khác:** Có thể chọn **New → Blueprint**, kết nối repo có `render.yaml` và cung cấp `APP_PIN` khi được hỏi. Blueprint tự khai báo Docker + Free + health check.

### C. Sử dụng trên iPhone

1. Mở địa chỉ web đã deploy bằng Safari.
2. Bấm **Chọn video từ iPhone** để chọn MP4/MOV từ Ảnh hoặc Tệp.
3. Bấm **Tải logo lên** và chọn logo PNG. Logo nhỏ hơn 1 MB được web lưu **trong Safari của chính điện thoại đó** để lần sau tự dùng lại (trình duyệt có thể xóa bộ nhớ này).
4. Chọn góc phải dưới hoặc trên, kích thước logo, chế độ nền che kín logo cũ (mặc định bật).
5. Nhấn **Chèn logo vào video**; giữ trang mở khi upload và xử lý.
6. Khi hoàn tất, nhấn **Mở video để lưu vào Ảnh**. Trên Safari dùng **Chia sẻ → Lưu video** nếu có. Nếu không có, dùng **Tải file MP4**, vào ứng dụng **Tệp**, mở file rồi dùng **Chia sẻ → Lưu video**.
7. Muốn mở như app: Safari → **Chia sẻ → Thêm vào Màn hình chính**.

## Hạn chế của hosting Free

- Render Free có **0.1 CPU, 512 MB RAM**, nên xử lý video 1080p có thể rất chậm. Không phù hợp video dài/4K hay xử lý hàng loạt. Gói miễn phí **không cam kết luôn chạy**.
- Render Free ngủ sau khoảng **15 phút không có request**, tự khởi động khi có lượt truy cập mới (có thể mất khoảng một phút); thời gian upload/xử lý phụ thuộc mạng và CPU.
- Tệp đầu vào được xóa sau khi xử lý, file kết quả chỉ lưu **tạm 90 phút**, không phải kho lưu trữ. Render có thể khởi động lại dẫn đến mất job/file ngay cả trước thời điểm này.
- Mỗi lần chỉ mã hóa **một video**; thêm tối đa ba tác vụ đang chờ hoặc chạy.
- Nếu chưa cấu hình `APP_PIN`, ai có link cũng có thể tải video lên và dùng CPU của bạn: **nên đặt PIN**.
- Chức năng nền che kín mặc định tạo **một ô tối phủ góc phải** trước khi đặt logo của bạn; nó che được watermark ở khu vực đó nhưng có thể hơi khác màu video nền.

## Cấu trúc mã nguồn

```text
mobile-video-logo/
├── app.py                 # Backend FastAPI + FFmpeg + các job
├── requirements.txt       # Thư viện Python
├── Dockerfile             # Chứa FFmpeg, deploy lên Render
├── render.yaml            # Blueprint gói miễn phí (tùy chọn)
└── static/
    ├── index.html         # Giao diện tiếng Việt
    ├── style.css          # Thiết kế mobile
    ├── app.js             # Upload, trạng thái, lưu logo trong máy
    ├── manifest.webmanifest
    └── icon.png
```

## Thử trên máy tính (tùy chọn)

Phải có `ffmpeg` và `ffprobe` trong PATH.

```bash
pip install -r requirements.txt
# macOS/Linux: APP_PIN=123456 COOKIE_SECURE=0 uvicorn app:app --reload
# Windows PowerShell:
$env:APP_PIN="123456"; $env:COOKIE_SECURE="0"; uvicorn app:app --reload
```

Truy cập `http://127.0.0.1:8000`. Để triển khai online sử dụng hướng dẫn Render ở trên.

## Bảo mật và riêng tư

- Dùng `APP_PIN` khi công khai website. Không chia sẻ PIN hoặc link video đầu ra với người không mong muốn.
- Các file tạm chỉ nằm trong máy chủ khi xử lý. Không upload video nhạy cảm lên hosting miễn phí nếu chưa đánh giá chính sách và độ riêng tư phù hợp.
- Web không liên hệ dịch vụ AI/Gemini; chỉ xử lý **video bạn cung cấp** bằng FFmpeg.
- Chỉ sử dụng video và logo mà bạn có quyền chỉnh sửa.
