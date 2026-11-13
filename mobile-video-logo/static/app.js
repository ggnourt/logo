'use strict';
const $ = id => document.getElementById(id);
const app = {
  videoFile: null,
  logoFile: null,
  logoData: null,
  logoName: null,
  videoObjectUrl: null,
  timer: null,
  busy: false,
  config: {maxUploadMB: 150, maxLogoMB: 6, retentionMinutes: 90},
};
const LOGO_STORAGE_KEY = 'logodrop-saved-logo-v1';
const JOB_STORAGE_KEY = 'logodrop-last-job-v1';

function showError(message) {
  $('errorBox').textContent = message;
  $('errorBox').hidden = !message;
  if (message) $('errorBox').scrollIntoView({block:'nearest', behavior:'smooth'});
}
function fmtBytes(n) {
  if (!n && n !== 0) return '';
  return n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
function setBusy(busy) {
  app.busy = busy;
  $('submitBtn').disabled = busy;
  $('buttonLabel').textContent = busy ? 'Đang xử lý...' : 'Chèn logo vào video';
}
function setProgress(percent, stage, msg) {
  $('processCard').hidden = false;
  $('processTitle').textContent = stage;
  $('processMessage').textContent = msg || '';
  $('progressPercent').textContent = `${percent}%`;
  $('progressFill').style.width = `${percent}%`;
  $('progressLabel').textContent = percent < 100 ? 'Tiến độ' : 'Hoàn tất';
}
function setLogoPreview(url, name, saved) {
  $('logoThumb').innerHTML = '';
  const img = document.createElement('img');
  img.alt = 'Logo đã chọn';
  img.src = url;
  $('logoThumb').append(img);
  $('logoLabel').textContent = name || 'Logo đã lưu';
  $('logoSub').textContent = saved ? 'Đã lưu trên thiết bị này' : 'Được chọn cho lần xử lý này';
  $('chooseLogoBtn').textContent = 'Thay logo';
}
async function chooseVideo(file) {
  if (!file) return;
  showError('');
  if (!/\.(mp4|mov|m4v|webm|mkv)$/i.test(file.name)) {
    showError('Video cần là MP4, MOV, M4V, WEBM hoặc MKV.');
    return;
  }
  if (file.size > app.config.maxUploadMB * 1024 * 1024) {
    showError(`Video vượt giới hạn ${app.config.maxUploadMB} MB của hosting này.`);
    return;
  }
  app.videoFile = file;
  $('videoLabel').textContent = 'Đã chọn video';
  $('videoSub').textContent = file.name;
  $('originalPreviewWrap').hidden = false;
  if (app.videoObjectUrl) URL.revokeObjectURL(app.videoObjectUrl);
  app.videoObjectUrl = URL.createObjectURL(file);
  $('originalPreview').src = app.videoObjectUrl;
  $('videoMeta').textContent = `${file.name} • ${fmtBytes(file.size)}`;
  $('originalPreview').onloadedmetadata = () => {
    const v = $('originalPreview');
    $('videoMeta').textContent = `${file.name} • ${fmtBytes(file.size)} • ${v.videoWidth} × ${v.videoHeight} • ${v.duration ? v.duration.toFixed(1) + ' giây' : ''}`;
  };
}
function dataUrlToFile(data, filename) {
  const match = data.match(/^data:(image\/(?:png|jpeg|webp));base64,(.+)$/);
  if (!match) throw new Error('Logo lưu trên thiết bị không hợp lệ.');
  const raw = atob(match[2]);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return new File([bytes], filename || 'logo.png', {type: match[1]});
}
async function chooseLogo(file) {
  if (!file) return;
  if (!/\.(png|jpg|jpeg|webp)$/i.test(file.name)) return showError('Logo phải là ảnh PNG, JPG hoặc WEBP.');
  if (file.size > app.config.maxLogoMB * 1024 * 1024) return showError(`Logo không được vượt ${app.config.maxLogoMB} MB.`);
  app.logoFile = file;
  const reader = new FileReader();
  reader.onload = () => {
    app.logoData = reader.result;
    let saved = false;
    if (file.size < 1_000_000) {
      try { localStorage.setItem(LOGO_STORAGE_KEY, JSON.stringify({data: reader.result, name: file.name})); saved = true; }
      catch (_) { /* Browser storage may be full or disabled. */ }
    }
    setLogoPreview(reader.result, file.name, saved);
  };
  reader.readAsDataURL(file);
  showError('');
}
function showResult(job) {
  setBusy(false);
  $('processCard').hidden = true;
  $('resultCard').hidden = false;
  $('resultVideo').src = job.videoUrl;
  $('openVideoBtn').href = job.videoUrl;
  $('downloadBtn').href = job.downloadUrl;
  $('outputMeta').textContent = `MP4 • ${fmtBytes(job.size)} • tỉ lệ khung hình giữ nguyên`;
  $('expiryNote').textContent = `Tệp trên máy chủ sẽ được xóa sau khoảng ${app.config.retentionMinutes} phút.`;
  $('resultCard').scrollIntoView({block:'start',behavior:'smooth'});
}
async function checkJob(jobId) {
  if (!jobId) return;
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Video không còn tồn tại.');
    if (data.status === 'done') {
      clearInterval(app.timer); app.timer = null;
      showResult(data);
      return;
    }
    if (data.status === 'error') {
      clearInterval(app.timer); app.timer = null;
      setBusy(false);
      setProgress(0, 'Xử lý chưa thành công', data.message);
      showError(data.message);
      return;
    }
    setProgress(data.progress || 0, data.status === 'queued' ? 'Đang xếp hàng' : 'Đang chèn logo', data.message);
  } catch (e) {
    clearInterval(app.timer); app.timer = null;
    setBusy(false);
    $('processCard').hidden = true;
    localStorage.removeItem(JOB_STORAGE_KEY);
    showError(e.message);
  }
}
function trackJob(jobId) {
  clearInterval(app.timer);
  localStorage.setItem(JOB_STORAGE_KEY, jobId);
  setBusy(true);
  checkJob(jobId);
  app.timer = setInterval(() => checkJob(jobId), 2200);
}
function sendJob() {
  if (app.busy) return;
  if (!app.videoFile) return showError('Bạn cần chọn video trước.');
  let logo = app.logoFile;
  if (!logo && app.logoData) {
    try { logo = dataUrlToFile(app.logoData, app.logoName || 'logo.png'); }
    catch (e) { return showError(e.message); }
  }
  if (!logo) return showError('Bạn cần tải logo lên ít nhất một lần.');
  showError('');
  $('resultCard').hidden = true;
  setBusy(true);
  setProgress(0, 'Đang tải video lên máy chủ', 'Vui lòng giữ kết nối mạng ổn định...');
  const form = new FormData();
  form.append('video', app.videoFile);
  form.append('logo', logo);
  form.append('corner', $('cornerSelect').value);
  form.append('percentage', $('sizeSlider').value);
  form.append('cover', $('coverCheck').checked ? 'true' : 'false');
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/jobs');
  xhr.upload.onprogress = event => {
    if (event.lengthComputable) {
      const p = Math.max(1,Math.round(event.loaded / event.total * 100));
      setProgress(p, 'Đang tải video lên máy chủ', 'Tải lên: ' + p + '%');
    }
  };
  xhr.onload = () => {
    let body;
    try { body = JSON.parse(xhr.responseText); } catch (_) { body = {}; }
    if (xhr.status >= 200 && xhr.status < 300 && body.id) {
      trackJob(body.id);
    } else {
      setBusy(false);
      $('processCard').hidden = true;
      showError(typeof body.detail === 'string' ? body.detail : 'Không tải lên được. Kiểm tra mạng hoặc thử video nhỏ hơn.');
    }
  };
  xhr.onerror = () => {
    setBusy(false);
    $('processCard').hidden = true;
    showError('Mất kết nối tới server. Hãy thử lại.');
  };
  xhr.send(form);
  $('processCard').scrollIntoView({block:'nearest',behavior:'smooth'});
}
async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    if (!resp.ok) throw new Error('Máy chủ chưa phản hồi.');
    app.config = await resp.json();
    $('limitText').textContent = `Video tối đa ${app.config.maxUploadMB} MB • Video tự xóa sau ${app.config.retentionMinutes} phút`;
    if (app.config.requiresPin && !app.config.authenticated) {
      $('pinBackdrop').hidden = false;
      return;
    }
    restoreLastJob();
  } catch(e) { showError('Không kết nối được máy chủ. Vui lòng tải lại trang.'); }
}
function restoreLastJob() {
  const last = localStorage.getItem(JOB_STORAGE_KEY);
  if (last && /^[a-f0-9]{32}$/.test(last)) trackJob(last);
}
$('videoInput').addEventListener('change', event => chooseVideo(event.target.files[0]));
$('logoInput').addEventListener('change', event => chooseLogo(event.target.files[0]));
$('chooseLogoBtn').addEventListener('click', () => $('logoInput').click());
$('sizeSlider').addEventListener('input', e => $('sizeValue').textContent = e.target.value);
$('submitBtn').addEventListener('click', sendJob);
for(const eventName of ['dragenter','dragover']) {
  $('videoArea').addEventListener(eventName, e => { e.preventDefault(); $('videoArea').classList.add('dragover'); });
}
for(const eventName of ['dragleave','drop']) {
  $('videoArea').addEventListener(eventName, e => { e.preventDefault(); $('videoArea').classList.remove('dragover'); });
}
$('videoArea').addEventListener('drop', e => chooseVideo(e.dataTransfer.files[0]));
$('pinForm').addEventListener('submit', async e => {
  e.preventDefault();
  $('pinError').hidden = true;
  try {
    const res = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pin:$('pinInput').value})});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Mã PIN không đúng.');
    $('pinBackdrop').hidden = true;
    restoreLastJob();
  } catch (err) {
    $('pinError').textContent = err.message;
    $('pinError').hidden = false;
  }
});
try {
  const saved = JSON.parse(localStorage.getItem(LOGO_STORAGE_KEY) || 'null');
  if (saved && saved.data && saved.name) {
    app.logoData = saved.data;
    app.logoName = saved.name;
    setLogoPreview(saved.data, saved.name, true);
  }
} catch (_) {}
loadConfig();
