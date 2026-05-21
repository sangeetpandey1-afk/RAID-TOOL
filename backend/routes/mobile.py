"""Mobile App — Full RAID system on phone (Search + Entry + Upload + Dashboard)."""
from __future__ import annotations
import logging
import socket
from flask import Blueprint, request

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


@bp.get("/info")
def mobile_info():
    """Return server connection info for mobile apps."""
    ip = _get_local_ip()
    return envelope_ok({
        "server_ip": ip,
        "port": config.PORT,
        "base_url": f"http://{ip}:{config.PORT}",
        "mobile_url": f"http://{ip}:{config.PORT}/mobile",
        "max_upload_mb": config.MAX_UPLOAD_SIZE_MB,
        "categories": config.UPLOAD_CATEGORIES,
    })



@bp.get("/qr")
def show_qr():
    """QR code page — PC pe open karo, phone se scan karo."""
    ip = _get_local_ip()
    port = config.PORT
    mobile_url = f"http://{ip}:{port}/mobile"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Mobile Connect — RAID System</title>
<style>
body {{ font-family: Arial; text-align: center; padding: 40px; background: #1a1a2e; color: #fff; }}
.box {{ background: #fff; color: #333; padding: 30px; border-radius: 15px; display: inline-block; margin-top: 20px; }}
h1 {{ color: #00d4ff; }}
.url {{ font-size: 18px; background: #f0f0f0; padding: 10px; border-radius: 5px; margin: 15px 0; word-break: break-all; color: #333; }}
#qrcode {{ margin: 20px auto; }}
.info {{ color: #aaa; margin-top: 20px; font-size: 14px; }}
</style></head><body>
<h1>Mobile App Connect</h1>
<p>Phone se QR scan karein — poora app phone pe chalega</p>
<div class="box">
  <div id="qrcode"></div>
  <div class="url"><strong>{mobile_url}</strong></div>
  <p>Server: <strong>{ip}:{port}</strong></p>
</div>
<div class="info">
  <p>Phone aur PC ek hi WiFi par hone chahiye</p>
</div>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<script>new QRCode(document.getElementById("qrcode"), {{text:"{mobile_url}",width:256,height:256}});</script>
</body></html>"""
    return html



@bp.get("/")
@bp.get("/scan")
@bp.get("/scan/<case_id>")
def mobile_app(case_id: str = ""):
    """Full mobile app — Search, Entry, Upload, Dashboard all in one page."""
    ip = _get_local_ip()
    base_url = f"http://{ip}:{config.PORT}"
    return _mobile_html(base_url, case_id)


def _mobile_html(base_url: str, case_id: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="hi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>RAID System — Mobile</title>
<link rel="manifest" crossorigin="use-credentials">
<meta name="theme-color" content="#667eea">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f0f2f5; min-height: 100vh; padding-bottom: 70px; }}
.header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: #fff;
           padding: 15px; text-align: center; position: sticky; top: 0; z-index: 100; }}
.header h1 {{ font-size: 18px; }}
.header small {{ opacity: 0.8; font-size: 11px; }}

/* Bottom Navigation */
.bottom-nav {{ position: fixed; bottom: 0; left: 0; right: 0; background: #fff;
               display: flex; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); z-index: 100; }}
.nav-item {{ flex: 1; text-align: center; padding: 6px 0; cursor: pointer;
             font-size: 10px; color: #888; transition: 0.2s; }}
.nav-item.active {{ color: #667eea; font-weight: 700; }}
.nav-item .icon {{ font-size: 20px; display: block; }}

/* Pages */
.page {{ display: none; padding: 15px; }}
.page.active {{ display: block; }}

/* Cards */
.card {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 12px;
         box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.card h3 {{ font-size: 15px; color: #333; margin-bottom: 10px; }}

/* Form Elements */
input, select, textarea {{ width: 100%; padding: 11px; border: 2px solid #e8e8e8;
    border-radius: 8px; font-size: 15px; margin-bottom: 10px; -webkit-appearance: none; }}
input:focus, select:focus {{ border-color: #667eea; outline: none; }}
label {{ display: block; font-size: 13px; color: #555; margin-bottom: 4px; font-weight: 600; }}

/* Buttons */
.btn {{ display: block; width: 100%; padding: 13px; border: none; border-radius: 10px;
        font-size: 16px; font-weight: 700; cursor: pointer; text-align: center; margin-bottom: 8px; }}
.btn-primary {{ background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; }}
.btn-success {{ background: linear-gradient(135deg, #11998e, #38ef7d); color: #fff; }}
.btn-danger {{ background: linear-gradient(135deg, #f093fb, #f5576c); color: #fff; }}
.btn-info {{ background: linear-gradient(135deg, #4facfe, #00f2fe); color: #fff; }}
.btn:disabled {{ opacity: 0.5; }}
.btn-sm {{ padding: 8px 12px; font-size: 13px; width: auto; display: inline-block; }}

/* Search Results */
.result-item {{ padding: 12px; border-bottom: 1px solid #f0f0f0; }}
.result-item:last-child {{ border: none; }}
.result-item .name {{ font-weight: 700; font-size: 15px; color: #333; }}
.result-item .detail {{ font-size: 12px; color: #888; margin-top: 3px; }}
.result-item .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                        font-size: 11px; font-weight: 600; }}
.badge-open {{ background: #fff3cd; color: #856404; }}
.badge-paid {{ background: #d4edda; color: #155724; }}
.badge-noticed {{ background: #cce5ff; color: #004085; }}

/* Status messages */
.msg {{ padding: 10px; border-radius: 8px; margin: 8px 0; font-size: 13px; text-align: center; }}
.msg-ok {{ background: #d4edda; color: #155724; }}
.msg-err {{ background: #f8d7da; color: #721c24; }}
.msg-info {{ background: #fff3cd; color: #856404; }}

/* Preview */
.preview-area {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }}
.preview-item {{ width: 70px; height: 70px; border-radius: 8px; overflow: hidden;
                  border: 2px solid #e0e0e0; position: relative; }}
.preview-item img {{ width: 100%; height: 100%; object-fit: cover; }}

/* Stats row */
.stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }}
.stat-box {{ background: #fff; border-radius: 10px; padding: 12px; text-align: center;
              box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
.stat-box .num {{ font-size: 24px; font-weight: 800; color: #667eea; }}
.stat-box .lbl {{ font-size: 11px; color: #888; }}
</style></head><body>

<div class="header">
  <h1>RAID Management System</h1>
  <small>विद्युत चोरी रेड प्रबंधन — Mobile</small>
</div>

<!-- ========== PAGE: DASHBOARD ========== -->
<div class="page active" id="pageDashboard">
  <div class="stats">
    <div class="stat-box"><div class="num" id="statOpen">-</div><div class="lbl">Open Cases</div></div>
    <div class="stat-box"><div class="num" id="statTotal">-</div><div class="lbl">Total Cases</div></div>
  </div>
  <div class="card">
    <h3>Quick Actions</h3>
    <button class="btn btn-primary" onclick="switchPage('pageSearch')">🔍 Search Consumer / Case</button>
    <button class="btn btn-success" onclick="switchPage('pageEntry')">➕ New Case Entry</button>
    <button class="btn btn-info" onclick="switchPage('pageUpload')">📷 Scan & Upload</button>
    <button class="btn btn-danger" onclick="switchPage('pageAppeal')">⚖️ Appeal & Revision</button>
  </div>
  <div class="card">
    <h3>Recent Cases</h3>
    <div id="recentCases"><p style="color:#999;text-align:center;font-size:13px;">Loading...</p></div>
  </div>
</div>

<!-- ========== PAGE: SEARCH ========== -->
<div class="page" id="pageSearch">
  <div class="card">
    <h3>🔍 Search / खोजें</h3>
    <input type="text" id="searchQ" placeholder="Name / Account / Case ID / FIR..." autocomplete="off">
    <div style="display:flex;gap:8px;">
      <select id="searchStatus" style="flex:1"><option value="">All Status</option>
        <option value="open">Open</option><option value="noticed">Noticed</option>
        <option value="paid">Paid</option><option value="closed">Closed</option></select>
      <select id="searchSection" style="flex:1"><option value="">All Section</option>
        <option value="135">135</option><option value="138">138</option>
        <option value="126">126</option></select>
    </div>
    <button class="btn btn-primary" onclick="doSearch()">Search करें</button>
  </div>
  <div class="card" id="searchResults" style="display:none">
    <h3>Results</h3>
    <div id="searchList"></div>
  </div>
</div>

<!-- ========== PAGE: CASE ENTRY ========== -->
<div class="page" id="pageEntry">
  <div class="card">
    <h3>➕ New Raid Case Entry</h3>
    <label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
      <input type="checkbox" id="entryNoConnection" onchange="toggleNoConnection()" style="width:auto;">
      <span style="font-size:14px;">⚠️ कोई connection नहीं है (केवल user detail)</span>
    </label>
  </div>

  <!-- Consumer details card (hidden when no-connection) -->
  <div class="card" id="consumerCard">
    <h3>📋 Consumer (पंजीकृत उपभोक्ता)</h3>
    <label>Account Number / खाता संख्या</label>
    <input type="text" id="entryAccount" placeholder="Account No.">
    <button class="btn-sm btn-info" onclick="fetchConsumer()">Consumer खोजें</button>
    <div id="consumerInfo" style="margin:8px 0;font-size:13px;color:#555;"></div>

    <label>Consumer Name / उपभोक्ता नाम</label>
    <input type="text" id="entryName">
    <label>Consumer Father Name / पिता नाम</label>
    <input type="text" id="entryFather">
  </div>

  <!-- User details card -->
  <div class="card">
    <h3>👤 User (परिसर पर मिला व्यक्ति)</h3>
    <label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;" id="sameAsConsumerWrap">
      <input type="checkbox" id="entrySameAsConsumer" onchange="syncUserFromConsumer()" style="width:auto;">
      <span style="font-size:14px;">✓ User और Consumer एक ही हैं (same)</span>
    </label>

    <label>User Name / उपयोगकर्ता का नाम</label>
    <input type="text" id="entryUserName">
    <label>User Father Name / पिता नाम</label>
    <input type="text" id="entryUserFather">
    <label>Mobile</label>
    <input type="tel" id="entryMobile">
  </div>

  <!-- Address card -->
  <div class="card">
    <h3>📍 पता / Address</h3>
    <label>Village / ग्राम</label>
    <input type="text" id="entryVillage">
    <label>Landmark / निकटवर्ती स्थान</label>
    <input type="text" id="entryLandmark" placeholder="जैसे: मंदिर के पास, स्कूल के सामने">
    <label>Post Office / डाकघर</label>
    <input type="text" id="entryPost">
    <label>PIN Code</label>
    <input type="text" id="entryPin" maxlength="6">
  </div>
  <div class="card">
    <label>Section / धारा</label>
    <select id="entrySection">
      <option value="135">135 (Theft)</option>
      <option value="138">138 (TD)</option>
      <option value="126">126 (UUE)</option>
      <option value="Other">Other</option>
    </select>
    <label>Inspection Date / निरीक्षण दिनांक</label>
    <input type="date" id="entryDate">
    <label>Checking Type</label>
    <select id="entryCheckType">
      <option value="Regular">Regular</option>
      <option value="Vigilance">Vigilance</option>
      <option value="Other">Other</option>
    </select>
    <label>J.E. Name</label>
    <input type="text" id="entryJE">
    <label>Connected Load (KW)</label>
    <input type="number" id="entryLoad" step="0.01">
  </div>
  <div class="card">
    <h3>Devices / उपकरण</h3>
    <div id="deviceList"></div>
    <button class="btn-sm btn-info" onclick="addDevice()">+ Device Add करें</button>
  </div>
  <div class="card">
    <button class="btn btn-success" onclick="saveCase()">💾 Case Save करें</button>
    <div id="entryMsg"></div>
  </div>
</div>

<!-- ========== PAGE: UPLOAD ========== -->
<div class="page" id="pageUpload">
  <div class="card">
    <h3>📷 Document Scan & Upload</h3>
    <label>Case ID</label>
    <input type="text" id="uploadCaseId" placeholder="RC-XXXXXXXX-XXXXXX" value="{case_id}">
    <label>Category / श्रेणी</label>
    <select id="uploadCategory">
      <option value="checking_report">जाँच रिपोर्ट</option>
      <option value="inspection_photo">निरीक्षण फोटो</option>
      <option value="application">आवेदन पत्र</option>
      <option value="notice_served">तामील सूचना</option>
      <option value="payment_receipt">भुगतान रसीद</option>
      <option value="meter_photo">मीटर फोटो</option>
      <option value="site_photo">स्थल फोटो</option>
      <option value="fir_copy">FIR प्रति</option>
      <option value="other">अन्य</option>
    </select>
  </div>
  <div class="card">
    <button class="btn btn-primary" onclick="document.getElementById('camInput').click()">📷 Camera</button>
    <button class="btn btn-danger" onclick="document.getElementById('galInput').click()">🖼️ Gallery</button>
    <input type="file" id="camInput" accept="image/*" capture="environment" multiple style="display:none" onchange="handleUploadFiles(this)">
    <input type="file" id="galInput" accept="image/*,.pdf,.doc,.docx" multiple style="display:none" onchange="handleUploadFiles(this)">
    <div class="preview-area" id="uploadPreview"></div>
    <button class="btn btn-success" id="btnUpload" onclick="doUpload()" disabled>⬆️ Upload</button>
    <div id="uploadMsg"></div>
  </div>
</div>

<!-- ========== PAGE: APPEAL & REVISION ========== -->
<div class="page" id="pageAppeal">
  <div class="card">
    <h3>⚖️ Appeal & Revision</h3>
    <label>Case ID</label>
    <input type="text" id="appealCaseId" placeholder="RC-XXXXXXXX-XXXXXX" autocomplete="off">
    <button class="btn-sm btn-info" onclick="loadAppeals()">Load Case</button>
    <div id="appealCaseInfo" style="margin:8px 0;font-size:13px;color:#555;"></div>
  </div>

  <!-- Tab buttons within Appeal page -->
  <div class="card" style="display:flex;gap:6px;padding:10px;">
    <button class="btn-sm btn-primary" style="flex:1;" onclick="showAppealTab('file')">📝 File New</button>
    <button class="btn-sm btn-success" style="flex:1;" onclick="showAppealTab('proc')">📋 Proceedings</button>
    <button class="btn-sm btn-info" style="flex:1;" onclick="showAppealTab('rev')">🔄 Revise</button>
  </div>

  <!-- File Appeal -->
  <div class="card appeal-tab" id="appealTabFile">
    <h3>📝 File Appeal / अपील दर्ज करें</h3>
    <label>Appellant Name / नाम</label>
    <input type="text" id="appAppellantName" placeholder="अपीलकर्ता का नाम">
    <label>Relationship</label>
    <select id="appRelation">
      <option value="self">Self / स्वयं</option>
      <option value="relative">Relative / सम्बन्धी</option>
      <option value="advocate">Advocate / अधिवक्ता</option>
      <option value="other">Other / अन्य</option>
    </select>
    <label>Appeal Reason / कारण</label>
    <textarea id="appReason" rows="3" placeholder="अपील का कारण लिखें..."></textarea>
    <label>Attach Document (PDF/Photo) — optional</label>
    <input type="file" id="appAttach" accept="image/*,.pdf">
    <button class="btn btn-success" onclick="fileAppeal()">⚖️ Appeal File करें</button>
    <div id="appFileMsg"></div>
  </div>

  <!-- Existing Appeals + Proceedings -->
  <div class="card appeal-tab" id="appealTabProc" style="display:none">
    <h3>📋 Existing Appeals & Proceedings</h3>
    <div id="appealList"><p style="color:#999;text-align:center;font-size:13px;">Load case to see appeals</p></div>
    <hr style="margin:12px 0">
    <h3>➕ Add Proceeding / कार्यवाही दर्ज करें</h3>
    <label>Select Appeal</label>
    <select id="procAppealId"><option value="">--Select--</option></select>
    <label>Officer Name / अधिकारी</label>
    <input type="text" id="procOfficer">
    <label>Proceeding Date</label>
    <input type="date" id="procDate">
    <label>Summary / विवरण</label>
    <textarea id="procSummary" rows="2"></textarea>
    <label>Order Passed / आदेश</label>
    <textarea id="procOrder" rows="2"></textarea>
    <label>Next Hearing Date</label>
    <input type="date" id="procNextDate">
    <label>Outcome / परिणाम</label>
    <select id="procOutcome">
      <option value="pending">Pending</option>
      <option value="adjourned">Adjourned / स्थगित</option>
      <option value="partial_relief">Partial Relief</option>
      <option value="full_relief">Full Relief</option>
      <option value="dismissed">Dismissed / खारिज</option>
    </select>
    <label>Attach PDF (order copy) — optional</label>
    <input type="file" id="procAttach" accept="image/*,.pdf">
    <button class="btn btn-primary" onclick="addProceeding()">📋 Proceeding Save करें</button>
    <div id="procMsg"></div>
  </div>

  <!-- Revision -->
  <div class="card appeal-tab" id="appealTabRev" style="display:none">
    <h3>🔄 Revise Assessment / पुनर्निर्धारण</h3>
    <p style="font-size:12px;color:#666;margin-bottom:8px;">Appeal ke baad assessment recalculate hoga, final notice ke kaam aayega</p>

    <label>Select Appeal</label>
    <select id="revAppealId"><option value="">--Select--</option></select>

    <label>New Multiplier (e.g. 6→2)</label>
    <input type="number" id="revMultiplier" step="0.1" placeholder="e.g. 2">

    <label>Less Unit (yearly consumed units to subtract)</label>
    <input type="number" id="revLessUnit" placeholder="e.g. 100">

    <label>New Connected Load (KW) — optional</label>
    <input type="number" id="revLoad" step="0.01">

    <label>New Section — optional</label>
    <select id="revSection">
      <option value="">No change</option>
      <option value="135">135</option>
      <option value="138">138</option>
      <option value="126">126</option>
    </select>

    <label>Revised By / अधिकारी</label>
    <input type="text" id="revBy" placeholder="SDO / EE">

    <button class="btn btn-info" onclick="reviseCase()">🔄 Revise & Recalculate</button>
    <div id="revMsg"></div>
  </div>
</div>

<!-- Bottom Navigation -->
<div class="bottom-nav">
  <div class="nav-item active" onclick="switchPage('pageDashboard')"><span class="icon">🏠</span>Home</div>
  <div class="nav-item" onclick="switchPage('pageSearch')"><span class="icon">🔍</span>Search</div>
  <div class="nav-item" onclick="switchPage('pageEntry')"><span class="icon">➕</span>Entry</div>
  <div class="nav-item" onclick="switchPage('pageUpload')"><span class="icon">📷</span>Upload</div>
  <div class="nav-item" onclick="switchPage('pageAppeal')"><span class="icon">⚖️</span>Appeal</div>
</div>

<script>
const BASE = "{base_url}";

// ---- Navigation ----
function switchPage(id) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelectorAll('.nav-item').forEach((n,i) => {{
    n.classList.toggle('active', n.getAttribute('onclick')?.includes(id));
  }});
  if (id === 'pageDashboard') loadDashboard();
}}

// ---- Dashboard ----
async function loadDashboard() {{
  try {{
    const r = await fetch(BASE+'/api/cases?page_size=5');
    const d = await r.json();
    if (d.ok) {{
      document.getElementById('statTotal').textContent = d.meta?.total || 0;
      const cases = d.data || [];
      const open = cases.filter(c => c.case_status === 'open').length;
      document.getElementById('statOpen').textContent = d.meta?.total ? '...' : '0';
      document.getElementById('recentCases').innerHTML = cases.length
        ? cases.map(c => `<div class="result-item" onclick="viewCase('${{c.case_id}}')">
            <div class="name">${{c.user_name||c.account_number||c.case_id}}</div>
            <div class="detail">${{c.section||''}} | ${{c.inspection_date||''}} | ₹${{(c.total_assessment||0).toLocaleString()}}</div>
            <span class="badge badge-${{c.case_status}}">${{c.case_status}}</span>
          </div>`).join('')
        : '<p style="color:#999;text-align:center">No cases yet</p>';
    }}
  }} catch(e) {{ console.error(e); }}
}}

// ---- Search ----
async function doSearch() {{
  const q = document.getElementById('searchQ').value.trim();
  const status = document.getElementById('searchStatus').value;
  const section = document.getElementById('searchSection').value;
  if (!q && !status && !section) return;

  let url = BASE+'/api/cases/search?page_size=20';
  if (q) url += '&q='+encodeURIComponent(q);
  if (status) url += '&status='+status;
  if (section) url += '&section='+section;

  const r = await fetch(url);
  const d = await r.json();
  const box = document.getElementById('searchResults');
  const list = document.getElementById('searchList');
  box.style.display = 'block';

  if (d.ok && d.data.length > 0) {{
    list.innerHTML = d.data.map(c => `<div class="result-item" onclick="viewCase('${{c.case_id}}')">
      <div class="name">${{c.user_name||c.account_number||c.case_id}}</div>
      <div class="detail">A/c: ${{c.account_number||'-'}} | ${{c.section}} | ${{c.inspection_date||''}}</div>
      <div class="detail">Village: ${{c.user_address||'-'}} | ₹${{(c.total_assessment||0).toLocaleString()}}</div>
      <span class="badge badge-${{c.case_status}}">${{c.case_status}}</span>
    </div>`).join('');
  }} else {{
    list.innerHTML = '<p style="color:#999;text-align:center">कोई result नहीं मिला</p>';
  }}
}}

function viewCase(caseId) {{
  // Jump to Appeal page with case ID pre-filled
  document.getElementById('appealCaseId').value = caseId;
  document.getElementById('uploadCaseId').value = caseId;
  switchPage('pageAppeal');
  loadAppeals();
}}

// ---- Toggle: No Connection mode ----
function toggleNoConnection() {{
  const noConn = document.getElementById('entryNoConnection').checked;
  const consumerCard = document.getElementById('consumerCard');
  const sameWrap = document.getElementById('sameAsConsumerWrap');
  if (noConn) {{
    consumerCard.style.display = 'none';
    sameWrap.style.display = 'none';
    // Clear consumer fields
    document.getElementById('entryAccount').value = '';
    document.getElementById('entryName').value = '';
    document.getElementById('entryFather').value = '';
    // Uncheck "same"
    document.getElementById('entrySameAsConsumer').checked = false;
  }} else {{
    consumerCard.style.display = 'block';
    sameWrap.style.display = 'flex';
  }}
}}

// ---- Sync User from Consumer (when "same" is ticked) ----
function syncUserFromConsumer() {{
  const same = document.getElementById('entrySameAsConsumer').checked;
  if (same) {{
    document.getElementById('entryUserName').value = document.getElementById('entryName').value;
    document.getElementById('entryUserFather').value = document.getElementById('entryFather').value;
    // Make user fields readonly visually
    document.getElementById('entryUserName').setAttribute('readonly', 'true');
    document.getElementById('entryUserFather').setAttribute('readonly', 'true');
    document.getElementById('entryUserName').style.background = '#f0f0f0';
    document.getElementById('entryUserFather').style.background = '#f0f0f0';
  }} else {{
    document.getElementById('entryUserName').removeAttribute('readonly');
    document.getElementById('entryUserFather').removeAttribute('readonly');
    document.getElementById('entryUserName').style.background = '';
    document.getElementById('entryUserFather').style.background = '';
  }}
}}

// Auto-sync user when consumer name/father changes (if "same" is ticked)
document.addEventListener('DOMContentLoaded', () => {{
  const consName = document.getElementById('entryName');
  const consFather = document.getElementById('entryFather');
  if (consName) consName.addEventListener('input', () => {{
    if (document.getElementById('entrySameAsConsumer').checked)
      document.getElementById('entryUserName').value = consName.value;
  }});
  if (consFather) consFather.addEventListener('input', () => {{
    if (document.getElementById('entrySameAsConsumer').checked)
      document.getElementById('entryUserFather').value = consFather.value;
  }});
}});

// ---- Consumer Fetch ----
async function fetchConsumer() {{
  const acct = document.getElementById('entryAccount').value.trim();
  if (!acct) return;
  try {{
    const r = await fetch(BASE+'/api/consumers/'+encodeURIComponent(acct));
    const d = await r.json();
    if (d.ok && d.data.consumer) {{
      const c = d.data.consumer;
      document.getElementById('entryName').value = c.name || '';
      document.getElementById('entryFather').value = c.father_name || '';
      document.getElementById('entryVillage').value = c.village || '';
      document.getElementById('entryLandmark').value = c.landmark || '';
      document.getElementById('entryPost').value = c.post_office || '';
      document.getElementById('entryPin').value = c.pin_code || '';
      document.getElementById('entryMobile').value = c.mobile || '';
      document.getElementById('entryLoad').value = c.load_value || '';
      // Re-sync user fields if "same" is checked
      syncUserFromConsumer();
      document.getElementById('consumerInfo').innerHTML =
        '<span class="msg msg-ok">✅ Consumer found: '+c.name+'</span>';
    }} else {{
      document.getElementById('consumerInfo').innerHTML =
        '<span class="msg msg-info">Consumer DB mein nahi mila — manually bharo</span>';
    }}
  }} catch(e) {{ console.error(e); }}
}}

// ---- Devices ----
let devices = [];
function addDevice() {{
  devices.push({{name:'',L:0,F:1,H:8,D:365}});
  renderDevices();
}}
function renderDevices() {{
  document.getElementById('deviceList').innerHTML = devices.map((d,i) => `
    <div style="background:#f8f9fa;padding:8px;border-radius:8px;margin-bottom:6px;font-size:13px;">
      <input placeholder="Device name" value="${{d.name}}" onchange="devices[${{i}}].name=this.value" style="margin-bottom:4px">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:4px;">
        <input type="number" placeholder="L(W)" value="${{d.L}}" onchange="devices[${{i}}].L=+this.value">
        <input type="number" placeholder="F" value="${{d.F}}" step="0.1" onchange="devices[${{i}}].F=+this.value">
        <input type="number" placeholder="H" value="${{d.H}}" onchange="devices[${{i}}].H=+this.value">
        <input type="number" placeholder="D" value="${{d.D}}" onchange="devices[${{i}}].D=+this.value">
      </div>
    </div>`).join('');
}}

// ---- Save Case ----
async function saveCase() {{
  const noConn = document.getElementById('entryNoConnection').checked;
  const sameAsConsumer = document.getElementById('entrySameAsConsumer').checked;

  // User fields (always required)
  let userName = document.getElementById('entryUserName').value.trim();
  let userFather = document.getElementById('entryUserFather').value.trim();

  // Consumer fields (skip if no-connection)
  let account = '', consName = '', consFather = '';
  if (!noConn) {{
    account = document.getElementById('entryAccount').value.trim();
    consName = document.getElementById('entryName').value.trim();
    consFather = document.getElementById('entryFather').value.trim();
    // If "same" ticked, copy consumer to user
    if (sameAsConsumer) {{
      userName = consName;
      userFather = consFather;
    }}
  }}

  // Validation
  if (!userName) {{
    document.getElementById('entryMsg').innerHTML =
      '<div class="msg msg-err">❌ User Name is required</div>';
    return;
  }}

  const payload = {{
    account_number: account,
    name: consName,
    father_name: consFather,
    user_name: userName,
    user_father: userFather,
    village: document.getElementById('entryVillage').value.trim(),
    landmark: document.getElementById('entryLandmark').value.trim(),
    post_office: document.getElementById('entryPost').value.trim(),
    pin_code: document.getElementById('entryPin').value.trim(),
    mobile: document.getElementById('entryMobile').value.trim(),
    section: document.getElementById('entrySection').value,
    inspection_date: document.getElementById('entryDate').value,
    checking_type: document.getElementById('entryCheckType').value,
    je_name: document.getElementById('entryJE').value.trim(),
    connected_load_kw: parseFloat(document.getElementById('entryLoad').value) || 0,
    devices: devices.filter(d => d.name && d.L > 0),
    created_by: 'mobile',
    no_connection: noConn,
  }};

  try {{
    const r = await fetch(BASE+'/api/cases', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify(payload)
    }});
    const d = await r.json();
    if (d.ok) {{
      const cid = d.data.case.case_id;
      document.getElementById('entryMsg').innerHTML =
        `<div class="msg msg-ok">✅ Case saved: ${{cid}}<br>Assessment: ₹${{(d.data.case.total_assessment||0).toLocaleString()}}</div>`;
      document.getElementById('uploadCaseId').value = cid;
    }} else {{
      document.getElementById('entryMsg').innerHTML =
        `<div class="msg msg-err">❌ ${{d.error||'Save failed'}}</div>`;
    }}
  }} catch(e) {{
    document.getElementById('entryMsg').innerHTML = `<div class="msg msg-err">❌ ${{e.message}}</div>`;
  }}
}}

// ---- Upload ----
let uploadFiles = [];
function handleUploadFiles(input) {{
  Array.from(input.files).forEach(f => {{ if(uploadFiles.length<10) uploadFiles.push(f); }});
  renderUploadPreviews();
  input.value = '';
}}
function renderUploadPreviews() {{
  const area = document.getElementById('uploadPreview');
  area.innerHTML = uploadFiles.map((f,i) => {{
    if (f.type.startsWith('image/'))
      return `<div class="preview-item"><img src="${{URL.createObjectURL(f)}}"></div>`;
    return `<div class="preview-item" style="display:flex;align-items:center;justify-content:center;font-size:20px;">📄</div>`;
  }}).join('');
  document.getElementById('btnUpload').disabled = uploadFiles.length === 0;
}}
async function doUpload() {{
  const caseId = document.getElementById('uploadCaseId').value.trim();
  if (!caseId) {{ document.getElementById('uploadMsg').innerHTML='<div class="msg msg-err">Case ID bharo!</div>'; return; }}
  const fd = new FormData();
  uploadFiles.forEach(f => fd.append('files', f));
  fd.append('category', document.getElementById('uploadCategory').value);
  fd.append('uploaded_by', 'mobile');
  document.getElementById('uploadMsg').innerHTML='<div class="msg msg-info">Uploading...</div>';
  try {{
    const r = await fetch(BASE+'/api/cases/'+caseId+'/upload-multiple', {{method:'POST',body:fd}});
    const d = await r.json();
    if (d.ok) {{
      document.getElementById('uploadMsg').innerHTML=`<div class="msg msg-ok">✅ ${{d.data.uploaded}} files uploaded!</div>`;
      uploadFiles = []; renderUploadPreviews();
    }} else {{
      document.getElementById('uploadMsg').innerHTML=`<div class="msg msg-err">❌ ${{d.error}}</div>`;
    }}
  }} catch(e) {{ document.getElementById('uploadMsg').innerHTML=`<div class="msg msg-err">❌ ${{e.message}}</div>`; }}
}}

// ---- Appeal & Revision ----
function showAppealTab(which) {{
  ['file','proc','rev'].forEach(t => {{
    const el = document.getElementById('appealTab' + t.charAt(0).toUpperCase() + t.slice(1));
    if (el) el.style.display = (t === which) ? 'block' : 'none';
  }});
}}

async function loadAppeals() {{
  const cid = document.getElementById('appealCaseId').value.trim();
  if (!cid) return;
  // Get case info
  try {{
    const r = await fetch(BASE+'/api/cases/'+cid);
    const d = await r.json();
    if (d.ok) {{
      const c = d.data.case || {{}};
      document.getElementById('appealCaseInfo').innerHTML =
        `<div class="msg msg-ok">✅ ${{c.user_name||'-'}} | ${{c.section||''}} | ₹${{(c.total_assessment||0).toLocaleString()}} | Status: ${{c.case_status}}</div>`;
    }} else {{
      document.getElementById('appealCaseInfo').innerHTML =
        '<div class="msg msg-err">Case not found</div>';
      return;
    }}
  }} catch(e) {{ console.error(e); return; }}

  // Get appeals
  try {{
    const r = await fetch(BASE+'/api/cases/'+cid+'/appeals');
    const d = await r.json();
    const list = document.getElementById('appealList');
    const procSel = document.getElementById('procAppealId');
    const revSel = document.getElementById('revAppealId');
    procSel.innerHTML = '<option value="">--Select--</option>';
    revSel.innerHTML = '<option value="">--Select--</option>';

    if (d.ok && d.data.appeals.length > 0) {{
      list.innerHTML = d.data.appeals.map(a => `
        <div class="result-item">
          <div class="name">Appeal #${{a.id}} — ${{a.appellant_name}}</div>
          <div class="detail">Date: ${{a.appeal_date}} | Status: <b>${{a.appeal_status}}</b></div>
          <div class="detail">Reason: ${{a.appeal_reason || 'N/A'}}</div>
          <div class="detail">Proceedings: ${{a.proceedings_count || 0}} docs attached</div>
          ${{a.review_comments ? `<details><summary style="font-size:11px;cursor:pointer;color:#667eea">View proceedings</summary><pre style="white-space:pre-wrap;font-size:11px;background:#f8f8f8;padding:6px;border-radius:4px;margin-top:4px;">${{a.review_comments}}</pre></details>` : ''}}
        </div>
      `).join('');
      d.data.appeals.forEach(a => {{
        procSel.innerHTML += `<option value="${{a.id}}">Appeal #${{a.id}} — ${{a.appellant_name}}</option>`;
        revSel.innerHTML += `<option value="${{a.id}}">Appeal #${{a.id}} — ${{a.appellant_name}}</option>`;
      }});
    }} else {{
      list.innerHTML = '<p style="color:#999;text-align:center;font-size:13px;">No appeals yet — file one above</p>';
    }}
  }} catch(e) {{ console.error(e); }}
}}

async function fileAppeal() {{
  const cid = document.getElementById('appealCaseId').value.trim();
  if (!cid) {{ document.getElementById('appFileMsg').innerHTML='<div class="msg msg-err">Case ID dalo</div>'; return; }}
  const name = document.getElementById('appAppellantName').value.trim();
  if (!name) {{ document.getElementById('appFileMsg').innerHTML='<div class="msg msg-err">Name required</div>'; return; }}

  document.getElementById('appFileMsg').innerHTML='<div class="msg msg-info">Filing appeal...</div>';
  try {{
    // If file attached, use shortcut endpoint
    const fileEl = document.getElementById('appAttach');
    if (fileEl.files.length > 0) {{
      const fd = new FormData();
      fd.append('file', fileEl.files[0]);
      fd.append('appellant_name', name);
      fd.append('relationship', document.getElementById('appRelation').value);
      fd.append('appeal_reason', document.getElementById('appReason').value);
      const r = await fetch(BASE+'/api/cases/'+cid+'/appeal-upload', {{method:'POST', body:fd}});
      const d = await r.json();
      if (d.ok) {{
        document.getElementById('appFileMsg').innerHTML=`<div class="msg msg-ok">✅ Appeal #${{d.data.appeal_id}} filed + document attached!</div>`;
        loadAppeals();
      }} else {{
        document.getElementById('appFileMsg').innerHTML=`<div class="msg msg-err">❌ ${{d.error}}</div>`;
      }}
    }} else {{
      // Just file the appeal record
      const r = await fetch(BASE+'/api/cases/'+cid+'/appeals', {{
        method:'POST', headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{
          appellant_name: name,
          appellant_relation: document.getElementById('appRelation').value,
          appeal_reason: document.getElementById('appReason').value,
        }})
      }});
      const d = await r.json();
      if (d.ok) {{
        document.getElementById('appFileMsg').innerHTML=`<div class="msg msg-ok">✅ Appeal #${{d.data.appeal_id}} filed!</div>`;
        loadAppeals();
      }} else {{
        document.getElementById('appFileMsg').innerHTML=`<div class="msg msg-err">❌ ${{d.error}}</div>`;
      }}
    }}
  }} catch(e) {{ document.getElementById('appFileMsg').innerHTML=`<div class="msg msg-err">❌ ${{e.message}}</div>`; }}
}}

async function addProceeding() {{
  const cid = document.getElementById('appealCaseId').value.trim();
  const aid = document.getElementById('procAppealId').value;
  if (!cid || !aid) {{ document.getElementById('procMsg').innerHTML='<div class="msg msg-err">Case ID + Appeal select karo</div>'; return; }}

  document.getElementById('procMsg').innerHTML='<div class="msg msg-info">Saving...</div>';
  try {{
    const r = await fetch(BASE+'/api/cases/'+cid+'/appeals/'+aid+'/proceedings', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        officer_name: document.getElementById('procOfficer').value.trim(),
        proceeding_date: document.getElementById('procDate').value,
        summary: document.getElementById('procSummary').value.trim(),
        order_passed: document.getElementById('procOrder').value.trim(),
        next_date: document.getElementById('procNextDate').value,
        outcome: document.getElementById('procOutcome').value,
      }})
    }});
    const d = await r.json();
    if (d.ok) {{
      // Upload PDF if attached
      const fileEl = document.getElementById('procAttach');
      if (fileEl.files.length > 0) {{
        const fd = new FormData();
        fd.append('file', fileEl.files[0]);
        await fetch(BASE+'/api/cases/'+cid+'/appeals/'+aid+'/upload', {{method:'POST', body:fd}});
      }}
      document.getElementById('procMsg').innerHTML=`<div class="msg msg-ok">✅ Proceeding saved! Status: ${{d.data.appeal_status}}</div>`;
      loadAppeals();
    }} else {{
      document.getElementById('procMsg').innerHTML=`<div class="msg msg-err">❌ ${{d.error}}</div>`;
    }}
  }} catch(e) {{ document.getElementById('procMsg').innerHTML=`<div class="msg msg-err">❌ ${{e.message}}</div>`; }}
}}

async function reviseCase() {{
  const cid = document.getElementById('appealCaseId').value.trim();
  const aid = document.getElementById('revAppealId').value;
  if (!cid || !aid) {{ document.getElementById('revMsg').innerHTML='<div class="msg msg-err">Case + Appeal select karo</div>'; return; }}

  const overrides = {{}};
  const m = document.getElementById('revMultiplier').value;
  const lu = document.getElementById('revLessUnit').value;
  const ld = document.getElementById('revLoad').value;
  const sec = document.getElementById('revSection').value;
  if (m) overrides.multiplier = parseFloat(m);
  if (lu) overrides.less_unit = parseFloat(lu);
  if (ld) overrides.connected_load_kw = parseFloat(ld);
  if (sec) overrides.section = sec;

  document.getElementById('revMsg').innerHTML='<div class="msg msg-info">Recalculating...</div>';
  try {{
    const r = await fetch(BASE+'/api/cases/'+cid+'/appeals/'+aid+'/revise', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        overrides: overrides,
        revised_by: document.getElementById('revBy').value.trim() || 'mobile',
      }})
    }});
    const d = await r.json();
    if (d.ok) {{
      const r2 = d.data;
      document.getElementById('revMsg').innerHTML =
        `<div class="msg msg-ok">✅ Revised!<br>
         Original: ₹${{(r2.original_assessment||0).toLocaleString()}}<br>
         Revised:  ₹${{(r2.revised_assessment||0).toLocaleString()}}<br>
         Relief:   ₹${{(r2.relief_given||0).toLocaleString()}}<br>
         Final notice: section3 / section5 ab generate kar sakte ho</div>`;
      loadAppeals();
    }} else {{
      document.getElementById('revMsg').innerHTML=`<div class="msg msg-err">❌ ${{d.error}}</div>`;
    }}
  }} catch(e) {{ document.getElementById('revMsg').innerHTML=`<div class="msg msg-err">❌ ${{e.message}}</div>`; }}
}}

// ---- Init ----
document.getElementById('entryDate').value = new Date().toISOString().split('T')[0];
const _td = new Date().toISOString().split('T')[0];
const _pd = document.getElementById('procDate'); if(_pd) _pd.value = _td;
loadDashboard();
</script>
</body></html>"""
