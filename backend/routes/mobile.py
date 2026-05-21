"""Mobile connectivity — QR code, mobile upload page, LAN discovery."""
from __future__ import annotations
import io
import logging
import socket
from flask import Blueprint, request, render_template_string

from .. import config
from ..utils import envelope_ok

log = logging.getLogger(__name__)
bp = Blueprint("mobile", __name__, url_prefix="/mobile")


def _get_local_ip() -> str:
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ===================================================================
# GET /mobile/qr — Show QR code to connect phone
# ===================================================================
@bp.get("/qr")
def show_qr():
    """Generate a QR code page that phone can scan to connect."""
    ip = _get_local_ip()
    port = config.PORT
    base_url = f"http://{ip}:{port}"
    mobile_url = f"{base_url}/mobile/scan"

    # Simple HTML page with QR code (using a JS QR library from CDN)
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Mobile Connect — RAID System</title>
<style>
body {{ font-family: Arial; text-align: center; padding: 40px;
       background: #1a1a2e; color: #fff; }}
.box {{ background: #fff; color: #333; padding: 30px; border-radius: 15px;
        display: inline-block; margin-top: 20px; }}
h1 {{ color: #00d4ff; }}
.url {{ font-size: 18px; background: #f0f0f0; padding: 10px;
        border-radius: 5px; margin: 15px 0; word-break: break-all; color: #333; }}
#qrcode {{ margin: 20px auto; }}
.info {{ color: #aaa; margin-top: 20px; font-size: 14px; }}
</style>
</head><body>
<h1>Mobile Scanner Connect</h1>
<p>Phone se ye QR code scan karein ya URL browser mein dalein</p>
<div class="box">
  <div id="qrcode"></div>
  <div class="url"><strong>{mobile_url}</strong></div>
  <p>Server IP: <strong>{ip}:{port}</strong></p>
</div>
<div class="info">
  <p>Ensure phone and computer are on same WiFi network</p>
  <p>दोनों devices एक ही WiFi पर होने चाहिए</p>
</div>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<script>
new QRCode(document.getElementById("qrcode"), {{
    text: "{mobile_url}",
    width: 256, height: 256,
    colorDark: "#000", colorLight: "#fff"
}});
</script>
</body></html>"""
    return html


# ===================================================================
# GET /mobile/scan — Mobile-friendly upload page
# ===================================================================
@bp.get("/scan")
@bp.get("/scan/<case_id>")
def mobile_scan_page(case_id: str = ""):
    """Mobile-optimized HTML page for scanning and uploading documents."""
    ip = _get_local_ip()
    port = config.PORT
    base_url = f"http://{ip}:{port}"

    html = """<!DOCTYPE html>
<html lang="hi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Document Scanner — RAID System</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
       background: #f5f5f5; min-height: 100vh; padding: 10px; }
.header { background: linear-gradient(135deg, #667eea, #764ba2);
           color: #fff; padding: 15px; border-radius: 12px; margin-bottom: 15px;
           text-align: center; }
.header h1 { font-size: 20px; margin-bottom: 5px; }
.header p { font-size: 13px; opacity: 0.9; }
.card { background: #fff; border-radius: 12px; padding: 20px;
         margin-bottom: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.card h3 { color: #333; margin-bottom: 12px; font-size: 16px; }
label { display: block; font-size: 14px; color: #555; margin-bottom: 6px;
         font-weight: 600; }
input, select { width: 100%; padding: 12px; border: 2px solid #e0e0e0;
                border-radius: 8px; font-size: 16px; margin-bottom: 12px;
                -webkit-appearance: none; }
input:focus, select:focus { border-color: #667eea; outline: none; }
.btn { display: block; width: 100%; padding: 15px; border: none;
        border-radius: 10px; font-size: 17px; font-weight: 700;
        cursor: pointer; text-align: center; margin-bottom: 10px; }
.btn-camera { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; }
.btn-gallery { background: linear-gradient(135deg, #f093fb, #f5576c); color: #fff; }
.btn-upload { background: linear-gradient(135deg, #4facfe, #00f2fe); color: #fff; }
.btn:disabled { opacity: 0.5; }
.preview-area { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
.preview-item { position: relative; width: 80px; height: 80px;
                 border-radius: 8px; overflow: hidden; border: 2px solid #e0e0e0; }
.preview-item img { width: 100%; height: 100%; object-fit: cover; }
.preview-item .remove { position: absolute; top: -5px; right: -5px;
                         background: #f5576c; color: #fff; border-radius: 50%;
                         width: 22px; height: 22px; font-size: 12px;
                         border: none; cursor: pointer; line-height: 22px;
                         text-align: center; }
.status { padding: 12px; border-radius: 8px; margin: 10px 0;
           font-size: 14px; text-align: center; display: none; }
.status.success { display: block; background: #d4edda; color: #155724; }
.status.error { display: block; background: #f8d7da; color: #721c24; }
.status.uploading { display: block; background: #fff3cd; color: #856404; }
.file-count { background: #667eea; color: #fff; padding: 4px 10px;
               border-radius: 12px; font-size: 12px; display: inline-block; }
.recent-uploads { max-height: 200px; overflow-y: auto; }
.recent-item { display: flex; align-items: center; padding: 8px 0;
                border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.recent-item .icon { width: 35px; height: 35px; background: #f0f0f0;
                      border-radius: 8px; display: flex; align-items: center;
                      justify-content: center; margin-right: 10px; font-size: 18px; }
</style>
</head><body>

<div class="header">
  <h1>Document Scanner</h1>
  <p>विद्युत चोरी रेड — दस्तावेज स्कैन एवं अपलोड</p>
</div>

<div class="card">
  <h3>Case ID दर्ज करें</h3>
  <input type="text" id="caseId" placeholder="Case ID (e.g. RC-20250118-A3F2BC)"
         value=\"""" + case_id + """\" autocomplete="off">
</div>

<div class="card">
  <h3>दस्तावेज श्रेणी चुनें</h3>
  <select id="category">
    <option value="checking_report">जाँच रिपोर्ट / Checking Report</option>
    <option value="inspection_photo">निरीक्षण फोटो / Inspection Photo</option>
    <option value="application">आवेदन पत्र / Application</option>
    <option value="notice_served">तामील सूचना / Notice Served</option>
    <option value="payment_receipt">भुगतान रसीद / Payment Receipt</option>
    <option value="meter_photo">मीटर फोटो / Meter Photo</option>
    <option value="site_photo">स्थल फोटो / Site Photo</option>
    <option value="fir_copy">FIR प्रति / FIR Copy</option>
    <option value="appeal_document">अपील दस्तावेज / Appeal Document</option>
    <option value="id_proof">पहचान पत्र / ID Proof</option>
    <option value="correspondence">पत्राचार / Correspondence</option>
    <option value="other">अन्य / Other</option>
  </select>
</div>

<div class="card">
  <h3>फोटो / दस्तावेज चुनें</h3>

  <button class="btn btn-camera" onclick="openCamera()">
    📷 Camera से Scan करें
  </button>

  <button class="btn btn-gallery" onclick="openGallery()">
    🖼️ Gallery / Files से चुनें
  </button>

  <!-- Hidden file inputs -->
  <input type="file" id="cameraInput" accept="image/*" capture="environment"
         multiple style="display:none" onchange="handleFiles(this)">
  <input type="file" id="galleryInput"
         accept="image/*,.pdf,.doc,.docx" multiple
         style="display:none" onchange="handleFiles(this)">

  <div class="preview-area" id="previewArea"></div>
  <div id="fileCount"></div>
</div>

<div class="card">
  <label>विवरण / Description (optional)</label>
  <input type="text" id="description" placeholder="जैसे: मीटर का फोटो, साइट फोटो...">

  <button class="btn btn-upload" id="uploadBtn" onclick="uploadFiles()" disabled>
    ⬆️ Upload करें
  </button>

  <div class="status" id="status"></div>
</div>

<div class="card">
  <h3>हाल की अपलोड / Recent Uploads</h3>
  <div class="recent-uploads" id="recentUploads">
    <p style="color:#999; font-size:13px; text-align:center;">
      अभी कोई upload नहीं हुई
    </p>
  </div>
</div>

<script>
const BASE = \"""" + base_url + """\";
let selectedFiles = [];

function openCamera() {
    document.getElementById('cameraInput').click();
}

function openGallery() {
    document.getElementById('galleryInput').click();
}

function handleFiles(input) {
    const files = Array.from(input.files);
    files.forEach(f => {
        if (selectedFiles.length < 10) selectedFiles.push(f);
    });
    renderPreviews();
    input.value = '';
}

function renderPreviews() {
    const area = document.getElementById('previewArea');
    area.innerHTML = '';
    selectedFiles.forEach((f, i) => {
        const div = document.createElement('div');
        div.className = 'preview-item';
        if (f.type.startsWith('image/')) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(f);
            div.appendChild(img);
        } else {
            div.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:24px;">📄</div>';
        }
        const btn = document.createElement('button');
        btn.className = 'remove';
        btn.textContent = '×';
        btn.onclick = () => { selectedFiles.splice(i, 1); renderPreviews(); };
        div.appendChild(btn);
        area.appendChild(div);
    });
    document.getElementById('fileCount').innerHTML =
        selectedFiles.length > 0
        ? `<span class="file-count">${selectedFiles.length} file(s) selected</span>`
        : '';
    document.getElementById('uploadBtn').disabled = selectedFiles.length === 0;
}

async function uploadFiles() {
    const caseId = document.getElementById('caseId').value.trim();
    if (!caseId) {
        showStatus('error', 'Case ID दर्ज करें!');
        return;
    }

    const category = document.getElementById('category').value;
    const description = document.getElementById('description').value;
    const btn = document.getElementById('uploadBtn');
    btn.disabled = true;
    showStatus('uploading', 'Uploading... कृपया प्रतीक्षा करें...');

    try {
        const formData = new FormData();
        selectedFiles.forEach(f => formData.append('files', f));
        formData.append('category', category);
        formData.append('description', description);
        formData.append('uploaded_by', 'mobile');

        const resp = await fetch(`${BASE}/api/cases/${caseId}/upload-multiple`, {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();

        if (data.ok) {
            const r = data.data;
            showStatus('success',
                `✅ ${r.uploaded} file(s) uploaded successfully!` +
                (r.failed > 0 ? ` (${r.failed} failed)` : ''));
            selectedFiles = [];
            renderPreviews();
            loadRecent(caseId);
        } else {
            showStatus('error', '❌ ' + (data.error || 'Upload failed'));
        }
    } catch (e) {
        showStatus('error', '❌ Network error: ' + e.message);
    }
    btn.disabled = false;
}

function showStatus(type, msg) {
    const el = document.getElementById('status');
    el.className = 'status ' + type;
    el.textContent = msg;
    if (type === 'success') setTimeout(() => el.style.display = 'none', 5000);
}

async function loadRecent(caseId) {
    if (!caseId) return;
    try {
        const resp = await fetch(`${BASE}/api/cases/${caseId}/documents`);
        const data = await resp.json();
        if (data.ok && data.data.documents.length > 0) {
            const el = document.getElementById('recentUploads');
            el.innerHTML = data.data.documents.slice(0, 10).map(d => `
                <div class="recent-item">
                    <div class="icon">${d.is_image ? '🖼️' : '📄'}</div>
                    <div>
                        <div style="font-weight:600">${d.document_name}</div>
                        <div style="color:#888;font-size:11px">${d.document_type} • ${(d.file_size/1024).toFixed(1)} KB</div>
                    </div>
                </div>
            `).join('');
        }
    } catch(e) {}
}

// Auto-load recent if case_id is pre-filled
const initCase = document.getElementById('caseId').value;
if (initCase) loadRecent(initCase);
document.getElementById('caseId').addEventListener('blur', function() {
    loadRecent(this.value.trim());
});
</script>
</body></html>"""
    return html


# ===================================================================
# GET /mobile/info — Server info for mobile app discovery
# ===================================================================
@bp.get("/info")
def mobile_info():
    """Return server connection info for mobile apps."""
    ip = _get_local_ip()
    return envelope_ok({
        "server_ip": ip,
        "port": config.PORT,
        "base_url": f"http://{ip}:{config.PORT}",
        "mobile_url": f"http://{ip}:{config.PORT}/mobile/scan",
        "upload_endpoint": f"http://{ip}:{config.PORT}/api/cases/<case_id>/upload",
        "max_upload_mb": config.MAX_UPLOAD_SIZE_MB,
        "categories": config.UPLOAD_CATEGORIES,
    })
