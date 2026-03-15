"""
synth_realtime.py
A small realtime driver that uses sounddevice to play audio produced by SynthEngine.

Usage:
  python3 synth_realtime.py         # plays a demo arpeggio sequence
  python3 synth_realtime.py --midi  # if python-rtmidi is installed, listens to first MIDI input

Make sure to install dependencies:
  pip3 install numpy sounddevice
  pip3 install python-rtmidi   # optional, for MIDI input

On macOS you might need to allow Terminal / Python access to the microphone/audio devices.

"""
import argparse
import time
import numpy as np
import sounddevice as sd
from synth_engine import SynthEngine

def play_demo(engine, duration=8.0):
    # simple arpeggio sequence of MIDI notes
    notes = [60, 64, 67, 72]  # C4 E4 G4 C5
    note_len = 0.25
    t = 0.0
    start = time.time()
    i = 0
    while time.time() - start < duration:
        note = notes[i % len(notes)]
        engine.note_on(note, velocity=100)
        time.sleep(note_len * 0.9)
        engine.note_off(note)
        time.sleep(note_len * 0.1)
        i += 1

def audio_callback(outdata, frames, time_info, status, engine=None):
    if status:
        print("Audio status:", status)
    stereo = engine.render(frames)
    # outdata is (frames, channels)
    outdata[:] = stereo

def run_realtime(engine, device=None):
    stream = sd.OutputStream(channels=2, samplerate=engine.sample_rate,
                             callback=lambda out, frames, t, s: audio_callback(out, frames, t, s, engine),
                             blocksize=256,
                             device=device)
    with stream:
        print("Audio stream running. Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Stopping.")

def midi_listen(engine):
    try:
        import rtmidi
    except Exception as e:
        print("python-rtmidi not installed or failed to import:", e)
        print("Falling back to demo mode.")
        return False
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    if not ports:
        print("No MIDI ports found.")
        return False
    print("Opening MIDI port:", ports[0])
    midi_in.open_port(0)
    def callback(midi_msg, data=None):
        message, delta = midi_msg
        if not message:
            return
        # Note On: 0x90, Note Off: 0x80
        status = message[0] & 0xF0
        if status == 0x90 and len(message) >= 3 and message[2] > 0:
            note = message[1]
            vel = message[2]
            engine.note_on(note, vel)
        elif status == 0x80 or (status == 0x90 and len(message) >=3 and message[2] == 0):
            note = message[1]
            engine.note_off(note)
    midi_in.set_callback(callback)
    print("MIDI callback registered. Play notes on your MIDI keyboard.")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--midi', action='store_true', help='Enable MIDI input if python-rtmidi is available')
    args = parser.parse_args()

    engine = SynthEngine(sample_rate=44100, polyphony=8)
    # tweak engine defaults (optional)
    engine.master_gain = 0.15
    engine.filter_env_amount = 0.8

    midi_ok = False
    if args.midi:
        midi_ok = midi_listen(engine)

    # Start audio stream in a background thread and either play demo or wait for MIDI
    try:
        import threading
        rt = threading.Thread(target=run_realtime, args=(engine,), daemon=True)
        rt.start()
        if not midi_ok:
            print("Running demo arpeggio (no MIDI).")
            play_demo(engine, duration=20.0)
            print("Demo finished. Keep the stream running for a few seconds then exit.")
            time.sleep(1.0)
        else:
            # MIDI mode: keep main thread alive while audio thread runs
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("Interrupted by user. Exiting.")

if __name__ == '__main__':
    main()
