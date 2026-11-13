"""Mobile-first video logo overlay app for a small Render Docker web service."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
TEMP_ROOT = Path(tempfile.gettempdir()) / 'mobile-video-logo'
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = max(1, int(os.getenv('MAX_UPLOAD_MB', '150')))
MAX_LOGO_MB = 6
APP_PIN = os.getenv('APP_PIN', '').strip()
COOKIE_NAME = 'video_logo_session'
JOB_TTL_SECONDS = 90 * 60
MAX_QUEUED_JOBS = 3

app = FastAPI(title='Video Logo — Mobile', docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
executor = ThreadPoolExecutor(max_workers=1)
jobs: dict[str, dict] = {}
jobs_lock = threading.RLock()


class PinRequest(BaseModel):
    pin: str


def token_value() -> str:
    return hmac.new(APP_PIN.encode(), b'mobile-video-logo-session-v1', hashlib.sha256).hexdigest()


def authenticated(request: Request) -> bool:
    if not APP_PIN:
        return True
    current = request.cookies.get(COOKIE_NAME, '')
    return hmac.compare_digest(current, token_value())


def require_auth(request: Request) -> None:
    if not authenticated(request):
        raise HTTPException(status_code=401, detail='Vui lòng nhập mã PIN để sử dụng.')


def job_for(job_id: str) -> dict:
    with jobs_lock:
        j = jobs.get(job_id)
        if j is None:
            raise HTTPException(status_code=404, detail='Video không tồn tại hoặc đã hết hạn.')
        return j


def update_job(job_id: str, **fields) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is not None:
            job.update(fields)


def probe(path: Path) -> tuple[int, int, float, str | None]:
    proc = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
        capture_output=True, text=True, timeout=35, check=False,
    )
    if proc.returncode != 0:
        raise ValueError('Không đọc được video. Hãy chọn tệp MP4 hoặc MOV hợp lệ.')
    info = json.loads(proc.stdout)
    videos = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
    if not videos:
        raise ValueError('Tệp tải lên không có hình ảnh video.')
    stream = videos[0]
    width = int(stream.get('width', 0))
    height = int(stream.get('height', 0))
    if width <= 0 or height <= 0:
        raise ValueError('Không xác định được kích thước video.')
    rotation = 0.0
    for sd in stream.get('side_data_list', []):
        if 'rotation' in sd:
            rotation = float(sd['rotation'])
            break
    if rotation == 0:
        rotation = float(stream.get('tags', {}).get('rotate', 0) or 0)
    if abs(int(round(rotation))) % 180 == 90:
        width, height = height, width
    duration = float(info.get('format', {}).get('duration') or stream.get('duration') or 0)
    if duration <= 0:
        raise ValueError('Không xác định được thời lượng video.')
    audio = next((s.get('codec_name') for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)
    return width, height, duration, audio


def make_overlay(source: Path, destination: Path, video_width: int,
                 percentage: int, cover: bool) -> None:
    Image.MAX_IMAGE_PIXELS = 20_000_000
    try:
        with Image.open(source) as original:
            original.verify()
        with Image.open(source) as original:
            img = ImageOps.exif_transpose(original).convert('RGBA')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError('Logo cần là ảnh PNG, JPG hoặc WEBP hợp lệ.') from exc
    bbox = img.getchannel('A').getbbox()
    if bbox is None:
        raise ValueError('Ảnh logo bị trong suốt hoàn toàn.')
    img = img.crop(bbox)

    max_logo_width = max(40, round(video_width * percentage / 100))
    # Restrict logo height for very tall artwork, preserving aspect ratio.
    max_logo_height = max(36, round(video_width * .22))
    img.thumbnail((max_logo_width, max_logo_height), Image.Resampling.LANCZOS)

    if cover:
        pad = max(7, round(video_width * .011))
        panel_w = max(img.width + pad * 2, round(video_width * .19))
        panel_h = max(img.height + pad * 2, round(video_width * .095))
        panel = Image.new('RGBA', (panel_w, panel_h), '#111827')
        x = (panel_w - img.width) // 2
        y = (panel_h - img.height) // 2
        panel.alpha_composite(img, (x, y))
    else:
        panel = img
    panel.save(destination, 'PNG')


def process_job(job_id: str) -> None:
    with jobs_lock:
        j = jobs.get(job_id)
        if j is None:
            return
        video = Path(j['video_path'])
        logo = Path(j['logo_path'])
        folder = Path(j['folder'])
        corner = j['corner']
        percentage = j['percentage']
        cover = j['cover']
    output = folder / 'video-da-chen-logo.mp4'
    overlay = folder / 'overlay.png'
    log_file = folder / 'ffmpeg.log'
    update_job(job_id, status='processing', progress=1, message='Đang kiểm tra video...')
    try:
        width, height, duration, audio = probe(video)
        make_overlay(logo, overlay, width, percentage, cover)
        # An opaque panel reaches the video edge to cover a corner watermark fully.
        # Transparent logos are inset 1.5% from the edge for a cleaner look.
        margin = 0 if cover else max(6, round(width * .015))
        x = f'main_w-overlay_w-{margin}'
        y = str(margin) if corner == 'top-right' else f'main_h-overlay_h-{margin}'
        filt = (
            f'[0:v:0][1:v:0]overlay=x={x}:y={y}:shortest=1:format=auto,'
            'format=yuv420p[v]'
        )
        cmd = [
            'ffmpeg', '-y', '-hide_banner', '-nostdin', '-loglevel', 'error',
            '-stats_period', '0.6', '-progress', 'pipe:1',
            '-i', str(video), '-loop', '1', '-i', str(overlay),
            '-filter_complex', filt, '-map', '[v]', '-map', '0:a:0?',
            '-map_metadata', '0', '-c:v', 'libx264', '-preset', 'veryfast',
            '-crf', '18', '-pix_fmt', 'yuv420p', '-threads', '1',
        ]
        if audio == 'aac':
            cmd += ['-c:a', 'copy']
        else:
            cmd += ['-c:a', 'aac', '-b:a', '192k']
        cmd += ['-movflags', '+faststart', '-max_muxing_queue_size', '1024', str(output)]
        update_job(job_id, progress=2, message='Đang chèn logo và xuất MP4...')
        with open(log_file, 'wb') as stderr_file:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr_file,
                                  text=True, bufsize=1) as proc:
                assert proc.stdout is not None
                for line in proc.stdout:
                    if line.startswith('out_time_us=') or line.startswith('out_time_ms='):
                        try:
                            current = int(line.strip().split('=', 1)[1]) / 1_000_000
                            p = min(98, max(2, round(current / duration * 100)))
                            update_job(job_id, progress=p)
                        except ValueError:
                            pass
                return_code = proc.wait()
        if return_code != 0 or not output.exists() or output.stat().st_size == 0:
            error_tail = log_file.read_text(errors='replace')[-1200:]
            raise RuntimeError(error_tail or 'FFmpeg không xuất được video.')
        update_job(
            job_id, status='done', progress=100, message='Video đã sẵn sàng!',
            size=output.stat().st_size, completed=time.time(),
        )
    except Exception as exc:
        msg = re.sub(r'/tmp/\S+', '[tệp tạm]', str(exc))
        update_job(job_id, status='error', message=f'Xử lý thất bại: {msg[:350]}',
                   progress=0, completed=time.time())
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
    finally:
        for f in (video, logo, overlay, log_file):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass


def cleanup_worker():
    while True:
        time.sleep(5 * 60)
        now = time.time()
        remove = []
        with jobs_lock:
            for id_, j in list(jobs.items()):
                age = now - j.get('completed', j['created'])
                if j['status'] in ('done', 'error') and age > JOB_TTL_SECONDS:
                    remove.append((id_, j['folder']))
                    del jobs[id_]
        for _id, folder in remove:
            shutil.rmtree(folder, ignore_errors=True)


@app.on_event('startup')
def startup():
    threading.Thread(target=cleanup_worker, daemon=True).start()


@app.get('/')
def home():
    return FileResponse(BASE / 'static' / 'index.html')


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/api/config')
def config(request: Request):
    return {
        'requiresPin': bool(APP_PIN),
        'authenticated': authenticated(request),
        'maxUploadMB': MAX_UPLOAD_MB,
        'maxLogoMB': MAX_LOGO_MB,
        'retentionMinutes': round(JOB_TTL_SECONDS / 60),
    }


@app.post('/api/login')
def login(body: PinRequest, response: Response):
    if APP_PIN and not hmac.compare_digest(body.pin, APP_PIN):
        raise HTTPException(status_code=401, detail='Mã PIN không đúng.')
    if APP_PIN:
        response.set_cookie(COOKIE_NAME, token_value(), max_age=30 * 86400,
                            httponly=True, secure=os.getenv('COOKIE_SECURE', '1') != '0',
                            samesite='lax', path='/')
    return {'ok': True}


@app.post('/api/jobs')
async def create_job(
    request: Request,
    video: UploadFile = File(...),
    logo: UploadFile = File(...),
    corner: str = Form('bottom-right'),
    percentage: int = Form(18),
    cover: bool = Form(True),
):
    require_auth(request)
    if corner not in ('top-right', 'bottom-right') or not 8 <= percentage <= 35:
        raise HTTPException(422, detail='Vị trí hoặc kích thước logo không hợp lệ.')
    allowed_video = {'.mp4', '.mov', '.m4v', '.webm', '.mkv'}
    video_ext = Path(video.filename or '').suffix.lower()
    if video_ext not in allowed_video:
        raise HTTPException(422, detail='Hỗ trợ video MP4, MOV, M4V, WEBM, MKV.')
    allowed_logo = {'.png', '.jpg', '.jpeg', '.webp'}
    logo_ext = Path(logo.filename or '').suffix.lower()
    if logo_ext not in allowed_logo:
        raise HTTPException(422, detail='Logo phải là PNG, JPG hoặc WEBP.')
    with jobs_lock:
        active = sum(j['status'] in ('queued', 'processing') for j in jobs.values())
        if active >= MAX_QUEUED_JOBS:
            raise HTTPException(429, detail='Máy chủ đang bận, vui lòng thử lại sau.')
    job_id = uuid.uuid4().hex
    folder = TEMP_ROOT / job_id
    folder.mkdir(parents=True, exist_ok=True)
    video_path = folder / ('input' + video_ext)
    logo_path = folder / ('logo' + logo_ext)
    try:
        for upload, path, limit_mb in ((video, video_path, MAX_UPLOAD_MB),
                                       (logo, logo_path, MAX_LOGO_MB)):
            length = 0
            with open(path, 'wb') as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    length += len(chunk)
                    if length > limit_mb * 1024 * 1024:
                        raise HTTPException(413, detail=f'Tệp quá lớn (giới hạn {limit_mb} MB).')
                    out.write(chunk)
            if length == 0:
                raise HTTPException(422, detail='Tệp tải lên trống.')
        with jobs_lock:
            jobs[job_id] = {
                'id': job_id, 'created': time.time(), 'folder': str(folder),
                'video_path': str(video_path), 'logo_path': str(logo_path),
                'corner': corner, 'percentage': percentage, 'cover': cover,
                'status': 'queued', 'progress': 0, 'message': 'Đã nhận video, đang xếp hàng.',
            }
        executor.submit(process_job, job_id)
        return {'id': job_id, 'status': 'queued'}
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        await video.close()
        await logo.close()


@app.get('/api/jobs/{job_id}')
def status(job_id: str, request: Request):
    require_auth(request)
    j = job_for(job_id)
    return {
        'id': j['id'], 'status': j['status'], 'progress': j['progress'],
        'message': j['message'], 'size': j.get('size'),
        'videoUrl': f'/api/jobs/{job_id}/video' if j['status'] == 'done' else None,
        'downloadUrl': f'/api/jobs/{job_id}/download' if j['status'] == 'done' else None,
    }


def output_file(job_id: str, request: Request, download: bool):
    require_auth(request)
    j = job_for(job_id)
    path = Path(j['folder']) / 'video-da-chen-logo.mp4'
    if j['status'] != 'done' or not path.is_file():
        raise HTTPException(404, detail='Video chưa có hoặc đã hết hạn.')
    return FileResponse(path, media_type='video/mp4',
                        filename='video-da-chen-logo.mp4' if download else None,
                        content_disposition_type='attachment' if download else 'inline')


@app.get('/api/jobs/{job_id}/video')
def video_result(job_id: str, request: Request):
    return output_file(job_id, request, False)


@app.get('/api/jobs/{job_id}/download')
def video_download(job_id: str, request: Request):
    return output_file(job_id, request, True)
