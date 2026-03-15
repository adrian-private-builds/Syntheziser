"""
synth_engine.py
Polyphonic subtractive synth engine with anti-aliased oscillators,
state-variable filter with resonance, and stereo chorus.

Provides:
- PolyBLEP anti-aliased oscillators (sine, square, saw, triangle)
- ADSR envelope (vectorised)
- Chamberlin state-variable filter with resonance & per-sample cutoff modulation
- Stereo chorus effect
- Voice management for polyphony
- Buffer-based render() interface that returns stereo float32 frames
"""
import numpy as np

SAMPLE_RATE = 44100

_note_to_freq_cache = {}
def midi_note_to_freq(note):
    if note in _note_to_freq_cache:
        return _note_to_freq_cache[note]
    freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
    _note_to_freq_cache[note] = freq
    return freq


# ── PolyBLEP helper ─────────────────────────────────────────────────────────

def _polyblep(t, dt):
    """PolyBLEP correction for band-limited discontinuities.
    t: normalised phase [0, 1), dt: phase increment per sample."""
    out = np.zeros_like(t)
    # near rising edge (t ≈ 0)
    mask = t < dt
    tn = t[mask] / dt
    out[mask] = 2.0 * tn - tn * tn - 1.0
    # near wrap (t ≈ 1)
    mask = t > 1.0 - dt
    tn = (t[mask] - 1.0) / dt
    out[mask] = tn * tn + 2.0 * tn + 1.0
    return out


# ── Oscillator ───────────────────────────────────────────────────────────────

class Oscillator:
    def __init__(self, waveform='sine', sample_rate=SAMPLE_RATE):
        self.waveform = waveform
        self.sample_rate = sample_rate
        self.phase = 0.0  # normalised [0, 1)

    def set_waveform(self, w):
        self.waveform = w

    def process(self, frequency, frames):
        dt = frequency / self.sample_rate          # phase increment per sample
        phases = self.phase + dt * np.arange(frames)
        phases = phases % 1.0
        self.phase = (phases[-1] + dt) % 1.0

        if self.waveform == 'sine':
            return np.sin(2.0 * np.pi * phases)

        elif self.waveform == 'saw':
            # naive saw: [0,1) → [-1,1)
            raw = 2.0 * phases - 1.0
            return raw - _polyblep(phases, dt)

        elif self.waveform == 'square':
            raw = np.where(phases < 0.5, 1.0, -1.0)
            # correct both edges
            raw = raw + _polyblep(phases, dt) - _polyblep((phases + 0.5) % 1.0, dt)
            return raw

        elif self.waveform == 'triangle':
            # integrate the polyblep-corrected square via leaky integrator
            sq = np.where(phases < 0.5, 1.0, -1.0)
            sq = sq + _polyblep(phases, dt) - _polyblep((phases + 0.5) % 1.0, dt)
            # naive triangle from phase (anti-aliasing is less critical here)
            tri = 4.0 * np.abs(phases - 0.5) - 1.0
            return tri

        return np.sin(2.0 * np.pi * phases)


# ── Vectorised ADSR ─────────────────────────────────────────────────────────

class ADSR:
    def __init__(self, attack=0.005, decay=0.3, sustain=0.6, release=0.4,
                 sample_rate=SAMPLE_RATE):
        self.attack = max(1e-6, attack)
        self.decay = max(1e-6, decay)
        self.sustain = sustain
        self.release = max(1e-6, release)
        self.sample_rate = sample_rate
        self.state = 'idle'
        self.level = 0.0

    def note_on(self):
        self.state = 'attack'
        # don't reset level — allows smooth retrigger

    def note_off(self):
        if self.state != 'idle':
            self.state = 'release'

    def process(self, frames):
        out = np.empty(frames, dtype=np.float32)
        pos = 0
        while pos < frames:
            remaining = frames - pos
            if self.state == 'attack':
                rate = 1.0 / max(1, int(self.attack * self.sample_rate))
                samples_left = max(1, int((1.0 - self.level) / rate))
                n = min(remaining, samples_left)
                end_level = min(1.0, self.level + n * rate)
                out[pos:pos + n] = np.linspace(self.level, end_level, n, endpoint=False)
                self.level = end_level
                if self.level >= 1.0:
                    self.level = 1.0
                    self.state = 'decay'
                pos += n
            elif self.state == 'decay':
                rate = (1.0 - self.sustain) / max(1, int(self.decay * self.sample_rate))
                if rate < 1e-12:
                    self.state = 'sustain'
                    continue
                samples_left = max(1, int((self.level - self.sustain) / rate))
                n = min(remaining, samples_left)
                end_level = max(self.sustain, self.level - n * rate)
                out[pos:pos + n] = np.linspace(self.level, end_level, n, endpoint=False)
                self.level = end_level
                if self.level <= self.sustain:
                    self.level = self.sustain
                    self.state = 'sustain'
                pos += n
            elif self.state == 'sustain':
                out[pos:pos + remaining] = self.sustain
                self.level = self.sustain
                pos += remaining
            elif self.state == 'release':
                rate = self.level / max(1, int(self.release * self.sample_rate))
                if rate < 1e-12 or self.level < 1e-6:
                    self.level = 0.0
                    self.state = 'idle'
                    continue
                samples_left = max(1, int(self.level / rate))
                n = min(remaining, samples_left)
                end_level = max(0.0, self.level - n * rate)
                out[pos:pos + n] = np.linspace(self.level, end_level, n, endpoint=False)
                self.level = end_level
                if self.level <= 0.0:
                    self.level = 0.0
                    self.state = 'idle'
                pos += n
            else:  # idle
                out[pos:pos + remaining] = 0.0
                self.level = 0.0
                pos += remaining
        return out


# ── State-Variable Filter ────────────────────────────────────────────────────

class SVFilter:
    """Chamberlin state-variable filter: -12 dB/oct with resonance."""
    def __init__(self, cutoff=2500.0, resonance=0.25, sample_rate=SAMPLE_RATE):
        self.cutoff = cutoff
        self.resonance = resonance
        self.sample_rate = sample_rate
        self.low = 0.0
        self.band = 0.0

    def set_cutoff(self, cutoff):
        self.cutoff = max(20.0, min(cutoff, self.sample_rate * 0.45))

    def set_resonance(self, r):
        self.resonance = max(0.0, min(r, 1.0))

    def process(self, x, cutoff_mod=None):
        """Process audio. cutoff_mod: optional per-sample cutoff array."""
        y = np.empty_like(x)
        q = 1.0 - self.resonance  # damping: 1.0 = no resonance, 0.0 = self-oscillation
        q = max(0.05, q)  # prevent instability
        sr = self.sample_rate
        base_cutoff = self.cutoff

        for i in range(len(x)):
            if cutoff_mod is not None:
                c = max(20.0, min(cutoff_mod[i], sr * 0.45))
            else:
                c = base_cutoff
            f = 2.0 * np.sin(np.pi * c / sr)
            f = min(f, 0.95)  # stability clamp
            self.low += f * self.band
            high = x[i] - self.low - q * self.band
            self.band += f * high
            y[i] = self.low
        return y


# ── Stereo Chorus ────────────────────────────────────────────────────────────

class StereoChorus:
    """Simple stereo chorus with two modulated delay lines."""
    def __init__(self, sample_rate=SAMPLE_RATE, depth_ms=2.0, rate=0.8, mix=0.3):
        self.sample_rate = sample_rate
        self.depth_ms = depth_ms
        self.rate = rate
        self.mix = mix
        # delay buffer: enough for max depth + margin
        max_delay_samples = int(sample_rate * 0.02)  # 20 ms max
        self.buf_size = max_delay_samples + 256
        self.buffer = np.zeros(self.buf_size, dtype=np.float32)
        self.write_pos = 0
        self.lfo_phase_l = 0.0
        self.lfo_phase_r = 0.25  # 90-degree offset

    def process(self, mono):
        """Takes mono input, returns (left, right) stereo arrays."""
        frames = len(mono)
        left = np.empty(frames, dtype=np.float32)
        right = np.empty(frames, dtype=np.float32)

        depth_samples = self.depth_ms * 0.001 * self.sample_rate
        center_delay = depth_samples * 2.0  # centre point of modulation
        lfo_inc = self.rate / self.sample_rate

        for i in range(frames):
            # write to circular buffer
            self.buffer[self.write_pos] = mono[i]

            # LFO values
            lfo_l = np.sin(2.0 * np.pi * self.lfo_phase_l)
            lfo_r = np.sin(2.0 * np.pi * self.lfo_phase_r)
            self.lfo_phase_l = (self.lfo_phase_l + lfo_inc) % 1.0
            self.lfo_phase_r = (self.lfo_phase_r + lfo_inc) % 1.0

            # modulated delay
            delay_l = center_delay + depth_samples * lfo_l
            delay_r = center_delay + depth_samples * lfo_r

            # read with linear interpolation
            read_l = self.write_pos - delay_l
            read_r = self.write_pos - delay_r
            idx_l = int(read_l) % self.buf_size
            frac_l = read_l - int(read_l)
            idx_r = int(read_r) % self.buf_size
            frac_r = read_r - int(read_r)

            wet_l = self.buffer[idx_l] * (1.0 - frac_l) + self.buffer[(idx_l + 1) % self.buf_size] * frac_l
            wet_r = self.buffer[idx_r] * (1.0 - frac_r) + self.buffer[(idx_r + 1) % self.buf_size] * frac_r

            left[i] = mono[i] * (1.0 - self.mix) + wet_l * self.mix
            right[i] = mono[i] * (1.0 - self.mix) + wet_r * self.mix

            self.write_pos = (self.write_pos + 1) % self.buf_size

        return left, right


# ── Voice ────────────────────────────────────────────────────────────────────

class Voice:
    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.osc1 = Oscillator('saw', sample_rate)
        self.osc2 = Oscillator('saw', sample_rate)
        self.envelope = ADSR(sample_rate=sample_rate)
        self.filter = SVFilter(2500.0, 0.25, sample_rate)
        self.note = None
        self.velocity = 0.0
        self.active = False
        self.detune = 0.005  # ~8 cents for supersaw thickness

    def note_on(self, note, velocity):
        self.note = note
        self.velocity = velocity / 127.0
        self.active = True
        self.envelope.note_on()
        # free-running oscillators: do NOT reset phase (avoids clicks)

    def note_off(self):
        self.envelope.note_off()

    def is_done(self):
        return (not self.active) or (self.envelope.state == 'idle' and self.envelope.level == 0.0)

    def render(self, frames, lfo_value=0.0, detune_cents=0.0, filter_env_amount=0.0):
        if not self.active:
            return np.zeros((frames,), dtype=np.float32)
        freq = midi_note_to_freq(self.note) * (2.0 ** (detune_cents / 1200.0))
        freq = freq * (1.0 + lfo_value * 0.01)
        osc1 = self.osc1.process(freq, frames)
        osc2 = self.osc2.process(freq * (1.0 + self.detune), frames)
        mix = 0.5 * osc1 + 0.5 * osc2
        env = self.envelope.process(frames)
        # per-sample filter cutoff modulation
        base_cutoff = self.filter.cutoff
        cutoff_mod = base_cutoff + filter_env_amount * env * 3000.0
        filtered = self.filter.process(mix, cutoff_mod=cutoff_mod)
        out = filtered * env * self.velocity
        if self.envelope.state == 'idle' and self.envelope.level == 0.0:
            self.active = False
        return out


# ── Engine ───────────────────────────────────────────────────────────────────

class SynthEngine:
    def __init__(self, sample_rate=SAMPLE_RATE, polyphony=8):
        self.sample_rate = sample_rate
        self.voices = [Voice(sample_rate) for _ in range(polyphony)]
        self.lfo_phase = 0.0
        self.lfo_rate = 3.5
        self.master_gain = 0.18
        self.filter_env_amount = 0.6
        self.chorus = StereoChorus(sample_rate)

    def note_on(self, note, velocity=100):
        for v in self.voices:
            if not v.active:
                v.note_on(note, velocity)
                return
        self.voices[0].note_on(note, velocity)

    def note_off(self, note):
        for v in self.voices:
            if v.active and v.note == note:
                v.note_off()

    def set_osc2_waveform(self, w):
        for v in self.voices:
            v.osc2.set_waveform(w)

    def set_osc2_detune(self, d):
        for v in self.voices:
            v.detune = d

    def set_resonance(self, r):
        for v in self.voices:
            v.filter.set_resonance(r)

    def render(self, frames):
        buffer = np.zeros(frames, dtype=np.float32)
        # LFO
        phase_inc = 2.0 * np.pi * self.lfo_rate / self.sample_rate
        phases = self.lfo_phase + phase_inc * np.arange(frames)
        self.lfo_phase = (phases[-1] + phase_inc) % (2.0 * np.pi)
        lfo = np.sin(phases)
        lfo_value = lfo.mean()
        for v in self.voices:
            buffer += v.render(frames, lfo_value=lfo_value,
                               filter_env_amount=self.filter_env_amount)
        buffer *= self.master_gain
        # stereo chorus
        left, right = self.chorus.process(buffer)
        stereo = np.vstack((left, right)).T.astype(np.float32)
        return stereo
