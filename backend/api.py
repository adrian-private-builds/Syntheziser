# backend/api.py
# Flask REST API for the synthesizer.
# Usage: python3 run.py
# Then open http://localhost:8000 in your browser.

import os
import threading
import time

from flask import Flask, request, jsonify, send_from_directory
import sounddevice as sd

from backend.synth_engine import SynthEngine

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')

engine = SynthEngine(sample_rate=44100, polyphony=8)

audio_stream = None
stream_lock = threading.Lock()
running = False


# ── Audio helpers ────────────────────────────────────────────────────────────

def audio_callback(outdata, frames, time_info, status):
    if status:
        print("Audio status:", status)
    outdata[:] = engine.render(frames)


def start_audio():
    global audio_stream, running
    with stream_lock:
        if running:
            return True
        try:
            audio_stream = sd.OutputStream(
                channels=2,
                samplerate=engine.sample_rate,
                callback=audio_callback,
                blocksize=256,
            )
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


# ── Frontend ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route('/api/start', methods=['POST'])
def web_start():
    ok = start_audio()
    if ok:
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Failed to start audio'}), 500


@app.route('/api/stop', methods=['POST'])
def web_stop():
    stop_audio()
    return jsonify({'ok': True})


@app.route('/api/note_on', methods=['POST'])
def web_note_on():
    data = request.get_json(force=True)
    note = int(data.get('note', 60))
    vel = int(data.get('velocity', 100))
    engine.note_on(note, velocity=vel)
    return jsonify({'ok': True})


@app.route('/api/note_off', methods=['POST'])
def web_note_off():
    data = request.get_json(force=True)
    note = int(data.get('note', 60))
    engine.note_off(note)
    return jsonify({'ok': True})


@app.route('/api/set_params', methods=['POST'])
def web_set_params():
    data = request.get_json(force=True)
    if 'waveform' in data:
        for v in engine.voices:
            v.osc1.set_waveform(data['waveform'])
    if 'cutoff' in data:
        for v in engine.voices:
            v.filter.set_cutoff(float(data['cutoff']))
    if 'resonance' in data:
        engine.set_resonance(float(data['resonance']))
    for key in ('attack', 'decay', 'sustain', 'release'):
        if key in data:
            for v in engine.voices:
                setattr(v.envelope, key, max(1e-6, float(data[key])))
    if 'gain' in data:
        engine.master_gain = float(data['gain'])
    if 'filter_env_amount' in data:
        engine.filter_env_amount = float(data['filter_env_amount'])
    if 'osc2_waveform' in data:
        engine.set_osc2_waveform(data['osc2_waveform'])
    if 'osc2_detune' in data:
        engine.set_osc2_detune(float(data['osc2_detune']))
    if 'chorus_depth' in data:
        engine.chorus.depth_ms = float(data['chorus_depth'])
    if 'chorus_rate' in data:
        engine.chorus.rate = float(data['chorus_rate'])
    if 'chorus_mix' in data:
        engine.chorus.mix = float(data['chorus_mix'])
    return jsonify({'ok': True})


@app.route('/api/status', methods=['GET'])
def web_status():
    """Returns current engine state — useful for syncing UI on load."""
    sample_voice = engine.voices[0]
    return jsonify({
        'ok': True,
        'running': running,
        'waveform': sample_voice.osc1.waveform,
        'osc2_waveform': sample_voice.osc2.waveform,
        'osc2_detune': sample_voice.detune,
        'cutoff': sample_voice.filter.cutoff,
        'resonance': sample_voice.filter.resonance,
        'attack': sample_voice.envelope.attack,
        'decay': sample_voice.envelope.decay,
        'sustain': sample_voice.envelope.sustain,
        'release': sample_voice.envelope.release,
        'gain': engine.master_gain,
        'filter_env_amount': engine.filter_env_amount,
        'chorus_depth': engine.chorus.depth_ms,
        'chorus_rate': engine.chorus.rate,
        'chorus_mix': engine.chorus.mix,
    })
