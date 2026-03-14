# synth_web.py
# Simple web GUI for the local SynthEngine.
# Usage: python3 synth_web.py
# Then open http://localhost:8000 in your browser.

from flask import Flask, request, jsonify
import threading
import time
import sounddevice as sd
import json

from synth_engine import SynthEngine

app = Flask(__name__)

engine = SynthEngine(sample_rate=44100, polyphony=8)
engine.master_gain = 0.15
engine.filter_env_amount = 0.8

audio_stream = None
stream_lock = threading.Lock()
running = False

# Audio callback for sounddevice
def audio_callback(outdata, frames, time_info, status):
    if status:
        # print status occasionally for debugging
        print("Audio status:", status)
    stereo = engine.render(frames)
    outdata[:] = stereo

def start_audio():
    global audio_stream, running
    with stream_lock:
        if running:
            return True
        try:
            audio_stream = sd.OutputStream(channels=2, samplerate=engine.sample_rate,
                                           callback=audio_callback, blocksize=256)
            audio_stream.start()
            running = True
            print("Audio started")
            return True
        except Exception as e:
            print("Failed to start audio:", e)
            return False

def stop_audio():
    global audio_stream, running
    with stream_lock:
        if not running:
            return
        try:
            audio_stream.stop()
            audio_stream.close()
        except Exception as e:
            print("Error stopping audio:", e)
        audio_stream = None
        running = False
        print("Audio stopped")

# Web endpoints
@app.route("/")
def index():
    # Single-file HTML + JS UI
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Web Synth</title>
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; padding: 18px; }
    .row { margin-bottom: 10px; }
    label { display:inline-block; width: 120px; }
    input[type=range] { width: 320px; vertical-align: middle; }
    button { margin-right: 6px; }
    .keys button { width: 40px; height: 60px; margin-right:4px; }
    .keys button.active { background: #48a; color: white; }
    .hint { font-size: 0.9rem; color: #666; margin-top: 8px; }
  </style>
</head>
<body>
  <h2>Simple Web Synth</h2>

  <div class="row">
    <button id="startBtn">Start Audio</button>
    <button id="stopBtn" disabled>Stop Audio</button>
  </div>

  <div class="row">
    <label>Osc1 Waveform</label>
    <select id="waveform">
      <option value="saw">saw</option>
      <option value="sine">sine</option>
      <option value="square">square</option>
      <option value="triangle">triangle</option>
    </select>
  </div>

  <div class="row">
    <label>Filter cutoff</label>
    <input id="cutoff" type="range" min="100" max="12000" value="2000">
    <span id="cutoffVal">2000</span> Hz
  </div>

  <div class="row">
    <label>Attack</label>
    <input id="attack" type="range" min="0.001" max="2" step="0.001" value="0.01">
    <span id="attackVal">0.01</span> s
  </div>

  <div class="row">
    <label>Decay</label>
    <input id="decay" type="range" min="0.001" max="2" step="0.001" value="0.1">
    <span id="decayVal">0.1</span> s
  </div>

  <div class="row">
    <label>Sustain</label>
    <input id="sustain" type="range" min="0" max="1" step="0.01" value="0.7">
    <span id="sustainVal">0.7</span>
  </div>

  <div class="row">
    <label>Release</label>
    <input id="release" type="range" min="0.001" max="5" step="0.001" value="0.2">
    <span id="releaseVal">0.2</span> s
  </div>

  <div class="row">
    <label>Master gain</label>
    <input id="gain" type="range" min="0" max="1" step="0.01" value="0.15">
    <span id="gainVal">0.15</span>
  </div>

  <div class="row keys" id="keyboard">
    <label>Keyboard</label>
    <!-- C4..C5 -->
    <button data-note="60">C4<br><small>Z</small></button>
    <button data-note="62">D4<br><small>X</small></button>
    <button data-note="64">E4<br><small>C</small></button>
    <button data-note="65">F4<br><small>V</small></button>
    <button data-note="67">G4<br><small>B</small></button>
    <button data-note="69">A4<br><small>N</small></button>
    <button data-note="71">B4<br><small>M</small></button>
    <button data-note="72">C5<br><small>,</small></button>
    <button data-note="74">D5<br><small>.</small></button>
  </div>

  <div class="hint">
    Use keyboard keys Z X C V B N M , . to play notes. Click Start Audio first if needed.
  </div>

<script>
function postJSON(path, obj){
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj)
  }).then(r => r.json().catch(()=>{}));
}

document.getElementById("startBtn").onclick = async function(){
  const res = await postJSON("/start", {});
  if(res.ok){ document.getElementById("startBtn").disabled = true; document.getElementById("stopBtn").disabled = false; }
  else alert("Failed to start audio: " + (res.error || "unknown"));
};
document.getElementById("stopBtn").onclick = async function(){
  await postJSON("/stop", {});
  document.getElementById("startBtn").disabled = false; document.getElementById("stopBtn").disabled = true;
};

document.getElementById("waveform").onchange = function(){
  postJSON("/set_params", { waveform: this.value });
};

function wireRange(id, key, transform){
  const el = document.getElementById(id);
  const val = document.getElementById(id+"Val");
  el.oninput = function(){
    val.textContent = this.value;
    const payload = {};
    payload[key] = transform ? transform(this.value) : parseFloat(this.value);
    postJSON("/set_params", payload);
  };
}
wireRange("cutoff","cutoff", v=>parseFloat(v));
wireRange("attack","attack", v=>parseFloat(v));
wireRange("decay","decay", v=>parseFloat(v));
wireRange("sustain","sustain", v=>parseFloat(v));
wireRange("release","release", v=>parseFloat(v));
wireRange("gain","gain", v=>parseFloat(v));

/* Mouse / touch handlers for the on-screen keys */
document.querySelectorAll(".keys button").forEach(b=>{
  b.addEventListener("pointerdown", async (e)=> {
    const note = parseInt(b.getAttribute("data-note"));
    postJSON("/note_on", { note: note, velocity: 100 });
    b.classList.add("active");
  });
  b.addEventListener("pointerup", async (e)=> {
    const note = parseInt(b.getAttribute("data-note"));
    postJSON("/note_off", { note: note });
    b.classList.remove("active");
  });
  b.addEventListener("pointerleave", async (e)=> {
    const note = parseInt(b.getAttribute("data-note"));
    postJSON("/note_off", { note: note });
    b.classList.remove("active");
  });
});

/* Keyboard mapping */
// define which physical key maps to which MIDI note
const keyMap = {
  'z': 60, // C4
  'x': 62, // D4
  'c': 64, // E4
  'v': 65, // F4
  'b': 67, // G4
  'n': 69, // A4
  'm': 71, // B4
  ',': 72, // C5
  '.': 74  // D5
};

// track currently pressed keys to avoid repeats while holding key down
const pressedKeys = new Set();

function noteButtonForMidi(note) {
  return document.querySelector('.keys button[data-note="'+note+'"]');
}

window.addEventListener('keydown', (ev) => {
  // ignore if focus is in an input or textarea
  const tag = document.activeElement && document.activeElement.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

  const k = ev.key.toLowerCase();
  if (!keyMap.hasOwnProperty(k)) return;

  if (pressedKeys.has(k)) {
    // already pressed, ignore repeat
    ev.preventDefault();
    return;
  }
  pressedKeys.add(k);
  ev.preventDefault();
  const note = keyMap[k];
  const btn = noteButtonForMidi(note);
  if (btn) btn.classList.add('active');
  postJSON('/note_on', { note: note, velocity: 100 });
});

window.addEventListener('keyup', (ev) => {
  const k = ev.key.toLowerCase();
  if (!keyMap.hasOwnProperty(k)) return;
  pressedKeys.delete(k);
  ev.preventDefault();
  const note = keyMap[k];
  const btn = noteButtonForMidi(note);
  if (btn) btn.classList.remove('active');
  postJSON('/note_off', { note: note });
});

// ensure notes release when window loses focus
window.addEventListener('blur', () => {
  pressedKeys.forEach(k => {
    const note = keyMap[k];
    if (note) postJSON('/note_off', { note: note });
    const btn = noteButtonForMidi(note);
    if (btn) btn.classList.remove('active');
  });
  pressedKeys.clear();
});
</script>
</body>
</html>
"""

@app.route("/start", methods=["POST"])
def web_start():
    ok = start_audio()
    if ok:
        return jsonify({"ok": True})
    else:
        return jsonify({"ok": False, "error": "Failed to start audio"}), 500

@app.route("/stop", methods=["POST"])
def web_stop():
    stop_audio()
    return jsonify({"ok": True})

@app.route("/note_on", methods=["POST"])
def web_note_on():
    data = request.get_json(force=True)
    note = int(data.get("note", 60))
    vel = int(data.get("velocity", 100))
    engine.note_on(note, velocity=vel)
    return jsonify({"ok": True})

@app.route("/note_off", methods=["POST"])
def web_note_off():
    data = request.get_json(force=True)
    note = int(data.get("note", 60))
    engine.note_off(note)
    return jsonify({"ok": True})

@app.route("/set_params", methods=["POST"])
def web_set_params():
    data = request.get_json(force=True)
    # possible keys: waveform, cutoff, attack, decay, sustain, release, gain
    if "waveform" in data:
        w = data["waveform"]
        for v in engine.voices:
            v.osc1.set_waveform(w)
    if "cutoff" in data:
        cutoff = float(data["cutoff"])
        for v in engine.voices:
            v.filter.set_cutoff(cutoff)
    if "attack" in data or "decay" in data or "sustain" in data or "release" in data:
        for v in engine.voices:
            if "attack" in data: v.envelope.attack = float(data["attack"])
            if "decay" in data: v.envelope.decay = float(data["decay"])
            if "sustain" in data: v.envelope.sustain = float(data["sustain"])
            if "release" in data: v.envelope.release = float(data["release"])
    if "gain" in data:
        engine.master_gain = float(data["gain"])
    return jsonify({"ok": True})

if __name__ == "__main__":
    # start Flask in a separate thread so we can run other things if needed
    def run_server():
        app.run(host="0.0.0.0", port=8000, threaded=True)
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Flask server running at http://localhost:8000")
    # auto-start audio so user gets sound immediately (optional)
    start_audio()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("Shutting down...")
        stop_audio()
        # Flask thread will exit when process exits
