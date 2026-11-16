"""KernelR Toggle Launcher — local server that serves UI + relaunches Chrome."""
import http.server
import json
import subprocess
import os
import signal
import sys
import time
import urllib.parse

PORT = 7700
PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_profile.json")
CHROME = r"C:\src\chromium\src\out\KernelR\chrome.exe"
TEST_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_toggles.html")
chrome_proc = None


def kill_chrome():
    global chrome_proc
    os.system("taskkill /F /IM chrome.exe >nul 2>&1")
    chrome_proc = None
    time.sleep(1)


def launch_chrome():
    global chrome_proc
    kill_chrome()
    chrome_proc = subprocess.Popen([
        CHROME,
        f"--kr-profile={PROFILE}",
        "--no-first-run",
        "--disable-default-apps",
        TEST_PAGE,
    ])


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/ui":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(build_ui().encode("utf-8"))
        elif self.path == "/api/profile":
            with open(PROFILE, "r", encoding="utf-8-sig") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/launch":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                toggles = json.loads(body)
                with open(PROFILE, "r", encoding="utf-8-sig") as f:
                    profile = json.load(f)
                profile["toggles"] = toggles
                with open(PROFILE, "w", encoding="utf-8") as f:
                    json.dump(profile, f, indent=2, ensure_ascii=False)
                launch_chrome()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif self.path == "/api/kill":
            kill_chrome()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # quiet


def build_ui():
    return r"""<!DOCTYPE html>
<html><head>
<title>KR Launcher</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }
.container { max-width: 720px; margin: 0 auto; padding: 24px; }
h1 { color: #58a6ff; font-size: 20px; margin-bottom: 4px; }
.sub { color: #8b949e; font-size: 12px; margin-bottom: 20px; }
.toggles { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
.toggle-row { display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0; border-bottom: 1px solid #21262d; }
.toggle-row:last-child { border-bottom: none; }
.toggle-info { flex: 1; }
.toggle-name { font-size: 14px; font-weight: 600; }
.toggle-desc { font-size: 11px; color: #8b949e; margin-top: 2px; }
.toggle-tag { font-size: 10px; background: #1f6feb33; color: #58a6ff; padding: 1px 5px;
  border-radius: 3px; margin-left: 6px; }

/* Switch */
.switch { position: relative; width: 44px; height: 24px; flex-shrink: 0; margin-left: 12px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
  background: #30363d; border-radius: 12px; transition: 0.2s; }
.slider:before { content: ''; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px;
  background: #8b949e; border-radius: 50%; transition: 0.2s; }
input:checked + .slider { background: #238636; }
input:checked + .slider:before { transform: translateX(20px); background: #fff; }

.actions { margin-top: 16px; display: flex; gap: 10px; }
.btn { padding: 10px 24px; border: none; border-radius: 6px; font-size: 14px; font-weight: 600;
  cursor: pointer; transition: 0.15s; }
.btn-launch { background: #238636; color: #fff; }
.btn-launch:hover { background: #2ea043; }
.btn-kill { background: #da3633; color: #fff; }
.btn-kill:hover { background: #f85149; }
.btn-all { background: #1f6feb; color: #fff; }
.btn-all:hover { background: #388bfd; }
.btn-none { background: #30363d; color: #c9d1d9; }
.btn-none:hover { background: #484f58; }
.btn:disabled { opacity: 0.5; cursor: wait; }

.status { margin-top: 12px; font-size: 12px; color: #8b949e; min-height: 20px; }
.status.ok { color: #3fb950; }
.status.err { color: #f85149; }

.presets { margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap; }
.preset-btn { padding: 6px 14px; border: 1px solid #30363d; background: #161b22; color: #c9d1d9;
  border-radius: 6px; font-size: 12px; cursor: pointer; transition: 0.15s; }
.preset-btn:hover { border-color: #58a6ff; color: #58a6ff; }
</style>
</head>
<body>
<div class="container">
<h1>Kernel-R Toggle Launcher</h1>
<p class="sub">Toggle fingerprint spoofing groups on/off, then launch KernelR to verify.</p>

<div class="actions" style="margin-bottom: 16px;">
  <button class="btn btn-all" onclick="setAll(true)">All ON</button>
  <button class="btn btn-none" onclick="setAll(false)">All OFF</button>
</div>

<div class="toggles" id="toggles"></div>

<div class="actions">
  <button class="btn btn-launch" id="btnLaunch" onclick="doLaunch()">Launch KernelR</button>
  <button class="btn btn-kill" onclick="doKill()">Kill Chrome</button>
</div>
<div class="status" id="status"></div>

<div class="presets">
  <span style="color:#8b949e; font-size:12px; line-height:30px;">Presets:</span>
  <button class="preset-btn" onclick="preset('screen_only')">Screen Only</button>
  <button class="preset-btn" onclick="preset('no_canvas')">No Canvas</button>
  <button class="preset-btn" onclick="preset('locale_only')">Locale Only</button>
  <button class="preset-btn" onclick="preset('gpu_only')">GPU Only</button>
  <button class="preset-btn" onclick="preset('minimal')">Minimal (CPU+Screen)</button>
</div>
</div>

<script>
const TOGGLE_META = [
  { key: 'screen',      name: 'Screen',         tag: 'T6',      desc: 'width, height, availWidth, availHeight, colorDepth, pixelDepth, DPR' },
  { key: 'cpu_memory',  name: 'CPU / Memory',    tag: 'T6',      desc: 'hardwareConcurrency, deviceMemory' },
  { key: 'gpu_webgl',   name: 'WebGL GPU',       tag: 'T9',      desc: 'vendor, renderer, MAX_* params, extensions' },
  { key: 'canvas',      name: 'Canvas 2D',       tag: 'T8',      desc: 'toDataURL / getImageData noise (deterministic)' },
  { key: 'audio',       name: 'WebAudio',        tag: 'T10',     desc: 'AudioBuffer sample noise (deterministic)' },
  { key: 'fonts',       name: 'Font Whitelist',   tag: 'T11',     desc: 'Block non-whitelisted fonts at render level' },
  { key: 'locale_tz',   name: 'Locale / Timezone',tag: 'T7+T12', desc: 'language, languages, timezone (Main+Worker+iframe)' },
  { key: 'network',     name: 'Network',          tag: 'T14',     desc: '(planned) connection type, downlink, rtt' },
  { key: 'voices',      name: 'Voices',           tag: 'T15',     desc: '(planned) speechSynthesis voices list' },
  { key: 'permissions', name: 'Permissions',       tag: 'T15',     desc: '(planned) permissions API responses' },
  { key: 'window_size', name: 'Window Size',       tag: 'T15',     desc: '(planned) innerWidth/Height, outerWidth/Height' },
];

let toggles = {};

async function loadProfile() {
  const r = await fetch('/api/profile');
  const p = await r.json();
  toggles = p.toggles || {};
  render();
}

function render() {
  const el = document.getElementById('toggles');
  el.innerHTML = TOGGLE_META.map(t => `
    <div class="toggle-row">
      <div class="toggle-info">
        <span class="toggle-name">${t.name}</span>
        <span class="toggle-tag">${t.tag}</span>
        <div class="toggle-desc">${t.desc}</div>
      </div>
      <label class="switch">
        <input type="checkbox" data-key="${t.key}" ${toggles[t.key] ? 'checked' : ''}
          onchange="toggles['${t.key}']=this.checked">
        <span class="slider"></span>
      </label>
    </div>
  `).join('');
}

function setAll(val) {
  TOGGLE_META.forEach(t => toggles[t.key] = val);
  render();
}

function preset(name) {
  setAll(false);
  const sets = {
    screen_only: ['screen'],
    no_canvas: ['screen','cpu_memory','gpu_webgl','audio','fonts','locale_tz'],
    locale_only: ['locale_tz'],
    gpu_only: ['gpu_webgl'],
    minimal: ['screen','cpu_memory'],
  };
  (sets[name] || []).forEach(k => toggles[k] = true);
  render();
}

async function doLaunch() {
  const btn = document.getElementById('btnLaunch');
  const st = document.getElementById('status');
  btn.disabled = true;
  st.className = 'status';
  st.textContent = 'Saving profile & launching...';
  try {
    const r = await fetch('/api/launch', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(toggles)
    });
    if (r.ok) {
      st.className = 'status ok';
      st.textContent = 'KernelR launched! Check the test page in the new window.';
    } else {
      st.className = 'status err';
      st.textContent = 'Error: ' + await r.text();
    }
  } catch(e) {
    st.className = 'status err';
    st.textContent = 'Error: ' + e.message;
  }
  btn.disabled = false;
}

async function doKill() {
  await fetch('/api/kill', {method:'POST'});
  document.getElementById('status').textContent = 'Chrome killed.';
  document.getElementById('status').className = 'status';
}

loadProfile();
</script>
</body></html>"""


if __name__ == "__main__":
    print(f"KR Launcher running at http://localhost:{PORT}")
    print(f"Profile: {PROFILE}")
    print(f"Chrome:  {CHROME}")
    print("Press Ctrl+C to stop.")
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        kill_chrome()
        server.server_close()
