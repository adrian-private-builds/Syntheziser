// frontend/js/synth.js
// Web Audio API synthesizer engine — browser-native port of synth_engine.py

function midiToFreq(note) {
  return 440 * Math.pow(2, (note - 69) / 12);
}

function toWebWave(w) {
  return { sine: 'sine', saw: 'sawtooth', square: 'square', triangle: 'triangle' }[w] || 'sawtooth';
}

function resonanceToQ(r) {
  // r in [0, 1]: 0 → barely resonant, 1 → high resonance
  return 0.5 + r * 19.5;
}


// ── Voice ─────────────────────────────────────────────────────────────────────

class Voice {
  constructor(ctx, destination) {
    this.ctx = ctx;
    this.destination = destination;
    this.active = false;
    this.note = null;
    this._nodes = null;
    this._releaseTimer = null;
  }

  isDone() {
    return !this.active;
  }

  noteOn(note, velocity, params) {
    this._stop();

    this.note = note;
    this.active = true;

    const ctx = this.ctx;
    const now = ctx.currentTime;
    const freq = midiToFreq(note);

    const osc1    = ctx.createOscillator();
    const osc2    = ctx.createOscillator();
    const oscMix  = ctx.createGain();
    const filter  = ctx.createBiquadFilter();
    const envGain = ctx.createGain();
    const velGain = ctx.createGain();

    osc1.type = params.osc1Wave;
    osc2.type = params.osc2Wave;
    osc1.frequency.value = freq;
    osc2.frequency.value = freq * (1 + params.osc2Detune);

    oscMix.gain.value = 0.5;

    filter.type = 'lowpass';
    filter.frequency.value = params.cutoff;
    filter.Q.value = resonanceToQ(params.resonance);

    velGain.gain.value = velocity / 127;

    osc1.connect(oscMix);
    osc2.connect(oscMix);
    oscMix.connect(filter);
    filter.connect(envGain);
    envGain.connect(velGain);
    velGain.connect(this.destination);

    // Amplitude ADSR
    const { attack, decay, sustain } = params;
    envGain.gain.setValueAtTime(0, now);
    envGain.gain.linearRampToValueAtTime(1.0, now + attack);
    envGain.gain.setTargetAtTime(sustain, now + attack, decay / 3);

    // Filter envelope
    const peakCutoff = params.cutoff + params.filterEnvAmount * 3000;
    filter.frequency.setValueAtTime(params.cutoff, now);
    filter.frequency.linearRampToValueAtTime(peakCutoff, now + attack);
    filter.frequency.setTargetAtTime(params.cutoff, now + attack, decay / 3);

    osc1.start(now);
    osc2.start(now);

    this._nodes = { osc1, osc2, filter, envGain };
    this._release = params.release;
  }

  noteOff() {
    if (!this.active || !this._nodes) return;

    const ctx = this.ctx;
    const now = ctx.currentTime;
    const { envGain, filter, osc1, osc2 } = this._nodes;
    const release = this._release;

    const currentGain = envGain.gain.value;
    envGain.gain.cancelScheduledValues(now);
    envGain.gain.setValueAtTime(currentGain, now);
    envGain.gain.linearRampToValueAtTime(0, now + release);

    filter.frequency.cancelScheduledValues(now);
    filter.frequency.setValueAtTime(filter.frequency.value, now);

    osc1.stop(now + release + 0.05);
    osc2.stop(now + release + 0.05);

    if (this._releaseTimer) clearTimeout(this._releaseTimer);
    this._releaseTimer = setTimeout(() => {
      this.active = false;
      this._nodes = null;
    }, (release + 0.1) * 1000);
  }

  _stop() {
    if (this._releaseTimer) {
      clearTimeout(this._releaseTimer);
      this._releaseTimer = null;
    }
    if (this._nodes) {
      try { this._nodes.osc1.stop(); } catch (_) {}
      try { this._nodes.osc2.stop(); } catch (_) {}
      this._nodes = null;
    }
    this.active = false;
    this.note = null;
  }
}


// ── WebSynth ──────────────────────────────────────────────────────────────────

class WebSynth {
  constructor() {
    this.ctx = null;
    this.running = false;
    this.voicePool = [];

    this.params = {
      osc1Wave:        'sawtooth',
      osc2Wave:        'sawtooth',
      osc2Detune:      0.005,
      cutoff:          2500,
      resonance:       0.25,
      attack:          0.005,
      decay:           0.3,
      sustain:         0.6,
      release:         0.4,
      gain:            0.15,
      filterEnvAmount: 0.6,
      chorusDepth:     2.0,
      chorusRate:      0.8,
      chorusMix:       0.3,
    };
  }

  start() {
    if (this.running) return;
    this.ctx = new AudioContext();
    this._buildGraph();
    this.running = true;
  }

  _buildGraph() {
    const ctx = this.ctx;

    this.masterGain = ctx.createGain();
    this.masterGain.gain.value = this.params.gain;

    this.voiceBus = ctx.createGain();

    this._buildChorus();

    this.voiceBus.connect(this.chorusInput);
    this.chorusOutput.connect(this.masterGain);
    this.masterGain.connect(ctx.destination);

    this.voicePool = Array.from({ length: 8 }, () => new Voice(ctx, this.voiceBus));
  }

  _buildChorus() {
    const ctx = this.ctx;
    const p = this.params;

    this.chorusInput = ctx.createGain();

    const depthSec   = p.chorusDepth * 0.001;
    const centerDelay = depthSec * 2;

    // Left delay line + LFO
    this.delayL = ctx.createDelay(0.1);
    this.delayL.delayTime.value = centerDelay;
    this.lfoL = ctx.createOscillator();
    this.lfoL.type = 'sine';
    this.lfoL.frequency.value = p.chorusRate;
    this.lfoGainL = ctx.createGain();
    this.lfoGainL.gain.value = depthSec;
    this.lfoL.connect(this.lfoGainL);
    this.lfoGainL.connect(this.delayL.delayTime);

    // Right delay line + LFO (90° offset via delayed start)
    this.delayR = ctx.createDelay(0.1);
    this.delayR.delayTime.value = centerDelay;
    this.lfoR = ctx.createOscillator();
    this.lfoR.type = 'sine';
    this.lfoR.frequency.value = p.chorusRate;
    this.lfoGainR = ctx.createGain();
    this.lfoGainR.gain.value = depthSec;
    this.lfoR.connect(this.lfoGainR);
    this.lfoGainR.connect(this.delayR.delayTime);

    this.dryGain  = ctx.createGain();
    this.wetGainL = ctx.createGain();
    this.wetGainR = ctx.createGain();
    this.dryGain.gain.value  = 1 - p.chorusMix;
    this.wetGainL.gain.value = p.chorusMix;
    this.wetGainR.gain.value = p.chorusMix;

    const merger = ctx.createChannelMerger(2);

    this.chorusInput.connect(this.dryGain);
    this.dryGain.connect(merger, 0, 0);
    this.dryGain.connect(merger, 0, 1);

    this.chorusInput.connect(this.delayL);
    this.delayL.connect(this.wetGainL);
    this.wetGainL.connect(merger, 0, 0);

    this.chorusInput.connect(this.delayR);
    this.delayR.connect(this.wetGainR);
    this.wetGainR.connect(merger, 0, 1);

    this.chorusOutput = merger;

    const now = ctx.currentTime;
    this.lfoL.start(now);
    this.lfoR.start(now + 0.25 / p.chorusRate); // 90° phase offset
  }

  noteOn(note, velocity = 100) {
    if (!this.running) return;
    let voice = this.voicePool.find(v => v.isDone());
    if (!voice) voice = this.voicePool[0]; // steal oldest
    voice.noteOn(note, velocity, this.params);
  }

  noteOff(note) {
    if (!this.running) return;
    this.voicePool.forEach(v => {
      if (v.active && v.note === note) v.noteOff();
    });
  }

  setParams(obj) {
    const p = this.params;

    if ('waveform'         in obj) p.osc1Wave        = toWebWave(obj.waveform);
    if ('osc2_waveform'    in obj) p.osc2Wave         = toWebWave(obj.osc2_waveform);
    if ('osc2_detune'      in obj) p.osc2Detune       = obj.osc2_detune;
    if ('cutoff'           in obj) p.cutoff           = obj.cutoff;
    if ('resonance'        in obj) p.resonance        = obj.resonance;
    if ('attack'           in obj) p.attack           = Math.max(0.001, obj.attack);
    if ('decay'            in obj) p.decay            = Math.max(0.001, obj.decay);
    if ('sustain'          in obj) p.sustain          = obj.sustain;
    if ('release'          in obj) p.release          = Math.max(0.001, obj.release);
    if ('filter_env_amount' in obj) p.filterEnvAmount = obj.filter_env_amount;

    if ('gain' in obj) {
      p.gain = obj.gain;
      if (this.masterGain) this.masterGain.gain.value = obj.gain;
    }

    const chorusChanged = 'chorus_depth' in obj || 'chorus_rate' in obj || 'chorus_mix' in obj;
    if ('chorus_depth' in obj) p.chorusDepth = obj.chorus_depth;
    if ('chorus_rate'  in obj) p.chorusRate  = obj.chorus_rate;
    if ('chorus_mix'   in obj) p.chorusMix   = obj.chorus_mix;
    if (chorusChanged && this.running) this._updateChorus();
  }

  _updateChorus() {
    const p = this.params;
    const depthSec    = p.chorusDepth * 0.001;
    const centerDelay = depthSec * 2;
    this.delayL.delayTime.value  = centerDelay;
    this.delayR.delayTime.value  = centerDelay;
    this.lfoGainL.gain.value     = depthSec;
    this.lfoGainR.gain.value     = depthSec;
    this.lfoL.frequency.value    = p.chorusRate;
    this.lfoR.frequency.value    = p.chorusRate;
    this.dryGain.gain.value      = 1 - p.chorusMix;
    this.wetGainL.gain.value     = p.chorusMix;
    this.wetGainR.gain.value     = p.chorusMix;
  }
}
