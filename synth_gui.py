"""
synth_gui.py
Simple GUI for the synth_realtime engine using tkinter.

Controls:
- Waveform selector (sets osc1 waveform)
- Cutoff slider (affects per-voice filter cutoff)
- ADSR sliders (attack, decay, sustain, release)
- Master gain slider
- Start / Stop audio stream button

Usage:
  python3 synth_gui.py

Dependencies:
  pip3 install numpy sounddevice

If you want MIDI input, run synth_realtime.py --midi separately or extend this GUI to include MIDI handling.
"""
import tkinter as tk
from tkinter import ttk
import sounddevice as sd

from synth_engine import SynthEngine

class SynthGUI:
    def __init__(self, root):
        self.root = root
        root.title("Simple Synth GUI")
        self.engine = SynthEngine(sample_rate=44100, polyphony=8)
        # initial values
        self.engine.master_gain = 0.15
        self.engine.filter_env_amount = 0.8

        self.is_running = False
        self.stream = None

        # UI layout
        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        # Waveform
        ttk.Label(main, text="Osc1 Waveform").grid(row=0, column=0, sticky="w")
        self.wave_var = tk.StringVar(value='saw')
        wave_combo = ttk.Combobox(main, textvariable=self.wave_var, values=['sine','square','saw','triangle'], state='readonly', width=10)
        wave_combo.grid(row=0, column=1, sticky="ew")
        wave_combo.bind("<<ComboboxSelected>>", self.on_waveform_change)

        # Cutoff
        ttk.Label(main, text="Filter Cutoff (Hz)").grid(row=1, column=0, sticky="w")
        self.cutoff_var = tk.DoubleVar(value=2000.0)
        cutoff = ttk.Scale(main, from_=100.0, to=12000.0, variable=self.cutoff_var, orient='horizontal', command=self.on_cutoff_change)
        cutoff.grid(row=1, column=1, sticky="ew")

        # ADSR sliders
        ttk.Label(main, text="Attack (s)").grid(row=2, column=0, sticky="w")
        self.attack_var = tk.DoubleVar(value=0.01)
        ttk.Scale(main, from_=0.001, to=2.0, variable=self.attack_var, orient='horizontal', command=self.on_adsr_change).grid(row=2, column=1, sticky="ew")

        ttk.Label(main, text="Decay (s)").grid(row=3, column=0, sticky="w")
        self.decay_var = tk.DoubleVar(value=0.1)
        ttk.Scale(main, from_=0.001, to=2.0, variable=self.decay_var, orient='horizontal', command=self.on_adsr_change).grid(row=3, column=1, sticky="ew")

        ttk.Label(main, text="Sustain (0-1)").grid(row=4, column=0, sticky="w")
        self.sustain_var = tk.DoubleVar(value=0.7)
        ttk.Scale(main, from_=0.0, to=1.0, variable=self.sustain_var, orient='horizontal', command=self.on_adsr_change).grid(row=4, column=1, sticky="ew")

        ttk.Label(main, text="Release (s)").grid(row=5, column=0, sticky="w")
        self.release_var = tk.DoubleVar(value=0.2)
        ttk.Scale(main, from_=0.001, to=5.0, variable=self.release_var, orient='horizontal', command=self.on_adsr_change).grid(row=5, column=1, sticky="ew")

        # Master gain
        ttk.Label(main, text="Master Gain").grid(row=6, column=0, sticky="w")
        self.gain_var = tk.DoubleVar(value=0.15)
        ttk.Scale(main, from_=0.0, to=1.0, variable=self.gain_var, orient='horizontal', command=self.on_gain_change).grid(row=6, column=1, sticky="ew")

        # Buttons for start/stop
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=(10,0))
        self.start_btn = ttk.Button(btn_frame, text="Start Audio", command=self.start_audio)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="Stop Audio", command=self.stop_audio, state='disabled')
        self.stop_btn.grid(row=0, column=1, padx=5)

        # Simple keyboard (one octave)
        key_frame = ttk.Frame(main)
        key_frame.grid(row=8, column=0, columnspan=2, pady=(10,0))
        notes = [60, 62, 64, 65, 67, 69, 71, 72]  # C major scale
        for i, n in enumerate(notes):
            b = ttk.Button(key_frame, text=str(n), width=4)
            b.grid(row=0, column=i, padx=2)
            b.bind("<ButtonPress-1>", lambda e, note=n: self.note_on(note))
            b.bind("<ButtonRelease-1>", lambda e, note=n: self.note_off(note))

        # status label
        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(main, textvariable=self.status_var).grid(row=9, column=0, columnspan=2, pady=(8,0))

        # configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

    def on_waveform_change(self, _=None):
        w = self.wave_var.get()
        for v in self.engine.voices:
            v.osc1.set_waveform(w)

    def on_cutoff_change(self, _=None):
        cutoff = self.cutoff_var.get()
        for v in self.engine.voices:
            v.filter.set_cutoff(cutoff)

    def on_adsr_change(self, _=None):
        a = self.attack_var.get()
        d = self.decay_var.get()
        s = self.sustain_var.get()
        r = self.release_var.get()
        for v in self.engine.voices:
            v.envelope.attack = a
            v.envelope.decay = d
            v.envelope.sustain = s
            v.envelope.release = r

    def on_gain_change(self, _=None):
        self.engine.master_gain = float(self.gain_var.get())

    def note_on(self, note):
        self.engine.note_on(note, velocity=100)
        self.status_var.set(f"Note ON {note}")

    def note_off(self, note):
        self.engine.note_off(note)
        self.status_var.set(f"Note OFF {note}")

    def audio_callback(self, outdata, frames, time_info, status):
        if status:
            print("Audio status:", status)
        stereo = self.engine.render(frames)
        outdata[:] = stereo

    def start_audio(self):
        if self.is_running:
            return
        try:
            self.stream = sd.OutputStream(channels=2, samplerate=self.engine.sample_rate,
                                          callback=self.audio_callback, blocksize=256)
            self.stream.start()
        except Exception as e:
            self.status_var.set(f"Audio error: {e}")
            return
        self.is_running = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_var.set("Running")

    def stop_audio(self):
        if not self.is_running:
            return
        try:
            self.stream.stop()
            self.stream.close()
        except Exception as e:
            print("Error stopping stream:", e)
        self.is_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_var.set("Stopped")

def main():
    root = tk.Tk()
    app = SynthGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
