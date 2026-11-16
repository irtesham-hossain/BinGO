"""Web control page for BinGo. Started by bingo_pi.py; uses only the Python standard library.

Open  http://<pi-address>:8000  on a phone or laptop on the same Wi-Fi.
Find the address on the Pi with:  hostname -I
"""
import json, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class Shared:
    """Data passed between the robot loop and the web page."""
    def __init__(self):
        self.lock = threading.Lock()
        self.jpeg = None
        self.frame_id = 0
        self.mode = "auto"            # "auto" follows raised hands, "manual" follows the buttons
        self.manual_cmd = "S"
        self.manual_t = 0.0
        self.lid_open = False
        self.requests = []            # one-off actions for the robot loop: "lid_open", "say_thanks", ...
        self.status = {}

    def set_frame(self, jpeg_bytes):
        with self.lock:
            self.jpeg = jpeg_bytes
            self.frame_id += 1

    def manual(self, now, hold=0.4):
        """The manual command, or S if the button was let go."""
        with self.lock:
            return self.manual_cmd if now - self.manual_t < hold else "S"

    def pop_requests(self):
        with self.lock:
            r, self.requests = self.requests, []
            return r


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>BinGo Control</title>
<style>
:root{--bg:#f3f4f1;--card:#fff;--ink:#17201b;--muted:#5b665f;--line:#d9ddd6;--green:#1f7a4d;--red:#b3261e;--btn:#e9ece6}
@media (prefers-color-scheme:dark){:root{--bg:#121513;--card:#1b1f1c;--ink:#e8ece9;--muted:#9aa49d;--line:#2c322e;--btn:#262b27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:16px;display:grid;gap:16px;grid-template-columns:1fr}
@media (min-width:820px){main{grid-template-columns:1.4fr 1fr}}
h1{font-size:20px;margin:0}header{max-width:960px;margin:0 auto;padding:16px 16px 0;display:flex;align-items:baseline;gap:10px}
header span{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
img{width:100%;border-radius:8px;background:#000;aspect-ratio:4/3;object-fit:cover;display:block}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.stat{background:var(--btn);border-radius:8px;padding:8px;text-align:center}
.stat b{display:block;font-size:18px}.stat small{color:var(--muted)}
.mode{display:flex;gap:6px;margin-bottom:12px}.mode button{flex:1}
button{font:inherit;border:0;border-radius:10px;padding:14px 10px;background:var(--btn);color:var(--ink);cursor:pointer;touch-action:none;user-select:none}
button.on{background:var(--green);color:#fff}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.pad button{font-size:22px;padding:18px 0}.pad .stop{background:var(--red);color:#fff;font-size:15px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.note{color:var(--muted);font-size:13px;margin:10px 0 0}
.disabled{opacity:.4;pointer-events:none}
</style></head><body>
<header><h1>BinGo</h1><span id="conn">connecting</span></header>
<main>
<section class="card">
  <img id="cam" src="/stream" alt="Robot camera">
  <div class="stats">
    <div class="stat"><b id="s_cmd">S</b><small>command</small></div>
    <div class="stat"><b id="s_hand">no</b><small>hand up</small></div>
    <div class="stat"><b id="s_dist">?</b><small>distance cm</small></div>
    <div class="stat"><b id="s_fps">0</b><small>FPS</small></div>
  </div>
  <p class="note" id="s_esp">ESP32: ?</p>
</section>
<section class="card">
  <div class="mode">
    <button id="m_auto" onclick="setMode('auto')">Auto (hand raise)</button>
    <button id="m_manual" onclick="setMode('manual')">Manual</button>
  </div>
  <div class="pad" id="pad">
    <span></span><button data-c="F">&#9650;</button><span></span>
    <button data-c="L">&#9664;</button><button class="stop" data-c="S">STOP</button><button data-c="R">&#9654;</button>
  </div>
  <p class="note">Hold a button to drive, let go to stop. Keyboard: W A D, space to stop.
  Forward is blocked when something is closer than 80 cm.</p>
  <div class="row">
    <button id="lid" onclick="act('lid')">Open lid</button>
    <button onclick="act('say_thanks')">ধন্যবাদ</button>
  </div>
  <div class="row">
    <button onclick="act('say_coming')">আসছি</button>
    <button onclick="act('reset')">Reset (next person)</button>
  </div>
</section>
</main>
<script>
let mode='auto', holdTimer=null, holding=null;
function q(u){return fetch(u,{cache:'no-store'}).catch(()=>{});}
function setMode(m){q('/mode?m='+m).then(refresh);}
function act(a){q('/act?a='+a).then(refresh);}
function start(c){ if(mode!=='manual')return; stop(); holding=c; q('/cmd?c='+c);
  if(c!=='S') holdTimer=setInterval(()=>q('/cmd?c='+c),150); }
function stop(){ if(holdTimer){clearInterval(holdTimer);holdTimer=null;} if(holding&&holding!=='S')q('/cmd?c=S'); holding=null; }
document.querySelectorAll('#pad button').forEach(b=>{
  b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);start(b.dataset.c);});
  ['pointerup','pointercancel','lostpointercapture'].forEach(ev=>b.addEventListener(ev,stop));
});
const keys={w:'F',a:'L',d:'R',' ':'S'};
addEventListener('keydown',e=>{const c=keys[e.key.toLowerCase()]; if(c&&!e.repeat){e.preventDefault();start(c);}});
addEventListener('keyup',e=>{if(keys[e.key.toLowerCase()])stop();});
addEventListener('blur',stop);
async function refresh(){
  try{const s=await (await fetch('/status',{cache:'no-store'})).json();
    mode=s.mode;
    document.getElementById('m_auto').classList.toggle('on',mode==='auto');
    document.getElementById('m_manual').classList.toggle('on',mode==='manual');
    document.getElementById('pad').classList.toggle('disabled',mode!=='manual');
    document.getElementById('s_cmd').textContent=s.cmd||'S';
    document.getElementById('s_hand').textContent=s.hand?'yes':'no';
    document.getElementById('s_dist').textContent=s.dist??'?';
    document.getElementById('s_fps').textContent=s.fps??0;
    document.getElementById('s_esp').textContent='ESP32: '+(s.esp||'?')+(s.arrived?'   |   arrived at person':'');
    document.getElementById('lid').textContent=s.lid_open?'Close lid':'Open lid';
    document.getElementById('conn').textContent='connected';
  }catch(e){document.getElementById('conn').textContent='no connection';}
}
setInterval(refresh,500); refresh();
const cam=document.getElementById('cam');
cam.onerror=()=>setTimeout(()=>{cam.src='/stream?'+Date.now();},1500);
</script></body></html>"""


def make_handler(sh):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="text/plain; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            arg = lambda k: (qs.get(k) or [""])[0]
            if u.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/status":
                with sh.lock:
                    st = dict(sh.status, mode=sh.mode, lid_open=sh.lid_open)
                return self._send(200, json.dumps(st, ensure_ascii=False), "application/json")
            if u.path == "/mode":
                m = arg("m")
                if m in ("auto", "manual"):
                    with sh.lock:
                        sh.mode = m
                        sh.manual_cmd, sh.manual_t = "S", 0.0
                return self._send(200, "ok")
            if u.path == "/cmd":
                c = arg("c")
                if c in ("F", "L", "R", "S"):
                    with sh.lock:
                        sh.manual_cmd, sh.manual_t = c, time.time()
                return self._send(200, "ok")
            if u.path == "/act":
                a = arg("a")
                if a in ("lid", "say_thanks", "say_coming", "reset"):
                    with sh.lock:
                        if a == "lid":
                            sh.lid_open = not sh.lid_open
                            a = "lid_open" if sh.lid_open else "lid_close"
                        sh.requests.append(a)
                return self._send(200, "ok")
            if u.path == "/stream":
                return self._stream()
            return self._send(404, "not found")

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = -1
            try:
                while True:
                    with sh.lock:
                        fid, jpg = sh.frame_id, sh.jpeg
                    if jpg is None or fid == last:
                        time.sleep(0.03)
                        continue
                    last = fid
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
    return H


def start(sh, port=8000):
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(sh))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
