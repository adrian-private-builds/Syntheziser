// frontend/js/app.js

const synth = new WebSynth();

// ── Factory presets ──────────────────────────────────────────────────────────

const FACTORY_PRESETS = {
  'Init': {
    waveform: 'saw', cutoff: 2000, attack: 0.01, decay: 0.1, sustain: 0.7,
    release: 0.2, gain: 0.15, osc2_waveform: 'saw', osc2_detune: 0.005,
    resonance: 0.25, filter_env_amount: 0.6,
    chorus_depth: 2.0, chorus_rate: 0.8, chorus_mix: 0.3,
  },
  'Fat Bass': {
    waveform: 'saw', cutoff: 500, attack: 0.005, decay: 0.2, sustain: 0.85,
    release: 0.12, gain: 0.22, osc2_waveform: 'square', osc2_detune: 0.008,
    resonance: 0.4, filter_env_amount: 0.35,
    chorus_depth: 1.0, chorus_rate: 0.4, chorus_mix: 0.1,
  },
  'Soft Pad': {
    waveform: 'triangle', cutoff: 4500, attack: 0.8, decay: 0.6, sustain: 0.65,
    release: 1.8, gain: 0.14, osc2_waveform: 'sine', osc2_detune: 0.003,
    resonance: 0.12, filter_env_amount: 0.15,
    chorus_depth: 3.5, chorus_rate: 0.5, chorus_mix: 0.55,
  },
  'Pluck': {
    waveform: 'saw', cutoff: 3500, attack: 0.001, decay: 0.12, sustain: 0.0,
    release: 0.25, gain: 0.18, osc2_waveform: 'saw', osc2_detune: 0.006,
    resonance: 0.3, filter_env_amount: 0.9,
    chorus_depth: 2.0, chorus_rate: 0.8, chorus_mix: 0.2,
  },
  'Sync Lead': {
    waveform: 'square', cutoff: 2800, attack: 0.01, decay: 0.25, sustain: 0.55,
    release: 0.2, gain: 0.16, osc2_waveform: 'saw', osc2_detune: 0.012,
    resonance: 0.45, filter_env_amount: 0.55,
    chorus_depth: 2.5, chorus_rate: 1.2, chorus_mix: 0.35,
  },
};

// ── Auto-start audio on first interaction ────────────────────────────────────

let audioStarted = false;

function ensureAudio() {
  if (audioStarted) return;
  audioStarted = true;
  synth.start();
}

// ── Waveform buttons ─────────────────────────────────────────────────────────

function setActiveWaveform(wave) {
  document.querySelectorAll('.wave-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.wave === wave);
  });
}

document.querySelectorAll('.wave-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    setActiveWaveform(btn.dataset.wave);
    ensureAudio();
    synth.setParams({ waveform: btn.dataset.wave });
  });
});

// ── Master gain slider ───────────────────────────────────────────────────────

const gainSlider = document.getElementById('gain');

function updateGainFill() {
  const ratio = (gainSlider.value - gainSlider.min) / (gainSlider.max - gainSlider.min);
  gainSlider.style.setProperty('--range-fill', (ratio * 100) + '%');
}

updateGainFill();

gainSlider.addEventListener('input', function () {
  ensureAudio();
  updateGainFill();
  synth.setParams({ gain: parseFloat(this.value) });
});

gainSlider.addEventListener('pointerup', () => gainSlider.blur());

// ── Rotary knobs ─────────────────────────────────────────────────────────────

const MIN_ANGLE = -135;
const MAX_ANGLE = 135;
// The indicator dot in knob_center.svg sits at ~49° from 12-o'clock when unrotated
const KNOB_DOT_OFFSET = 49;

const knobUpdaters = {};

document.querySelectorAll('.knob').forEach(knobEl => {
  const param = knobEl.dataset.param;
  const min = parseFloat(knobEl.dataset.min);
  const max = parseFloat(knobEl.dataset.max);
  let value = parseFloat(knobEl.dataset.value);
  const img = knobEl.querySelector('.knob-img');
  const valuePath = knobEl.querySelector('.knob-value');

  // Measure the arc path length for stroke-dasharray
  const arcLength = valuePath.getTotalLength();

  // Initialize stroke-dasharray
  valuePath.style.strokeDasharray = arcLength;

  function valueToRatio(v) {
    return (v - min) / (max - min);
  }

  function valueToAngle(v) {
    return MIN_ANGLE + valueToRatio(v) * (MAX_ANGLE - MIN_ANGLE);
  }

  function angleToValue(angle) {
    const clamped = Math.max(MIN_ANGLE, Math.min(MAX_ANGLE, angle));
    const ratio = (clamped - MIN_ANGLE) / (MAX_ANGLE - MIN_ANGLE);
    return min + ratio * (max - min);
  }

  function updateVisual() {
    const ratio = valueToRatio(value);
    const angle = valueToAngle(value);

    // Rotate the knob center image (offset by the indicator dot's default angle)
    img.style.transform = 'rotate(' + (angle - KNOB_DOT_OFFSET) + 'deg)';

    // Update the value arc: hide the unfilled portion from the end
    valuePath.style.strokeDashoffset = arcLength * (1 - ratio);
  }

  updateVisual();

  // Register updater so presets can set this knob externally
  knobUpdaters[param] = function (newValue) {
    value = Math.max(min, Math.min(max, newValue));
    knobEl.dataset.value = value;
    updateVisual();
  };

  let dragging = false;
  let startY = 0;
  let startAngle = 0;

  knobEl.addEventListener('pointerdown', e => {
    e.preventDefault();
    dragging = true;
    startY = e.clientY;
    startAngle = valueToAngle(value);
    knobEl.setPointerCapture(e.pointerId);
    ensureAudio();
  });

  knobEl.addEventListener('pointermove', e => {
    if (!dragging) return;
    const deltaY = startY - e.clientY;
    const newAngle = Math.max(MIN_ANGLE, Math.min(MAX_ANGLE, startAngle + deltaY * 1.5));
    value = angleToValue(newAngle);
    knobEl.dataset.value = value;
    updateVisual();
    synth.setParams({ [param]: value });
  });

  knobEl.addEventListener('pointerup', () => { dragging = false; knobEl.blur(); });
  knobEl.addEventListener('pointercancel', () => { dragging = false; });

  // Scroll wheel support
  knobEl.addEventListener('wheel', e => {
    e.preventDefault();
    ensureAudio();
    const step = (max - min) / 100;
    value = Math.max(min, Math.min(max, value - e.deltaY * step * 0.1));
    knobEl.dataset.value = value;
    updateVisual();
    synth.setParams({ [param]: value });
  });
});

// ── Preset system ────────────────────────────────────────────────────────────

const STORAGE_KEY = 'sroog-user-presets';
const presetSelect = document.getElementById('preset-select');
const presetSaveBtn = document.getElementById('preset-save');
const presetDeleteBtn = document.getElementById('preset-delete');

function getUserPresets() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch (_) {
    return {};
  }
}

function saveUserPresets(presets) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets));
}

function rebuildPresetList(selectValue) {
  presetSelect.innerHTML = '';

  // Factory group
  const factoryGroup = document.createElement('optgroup');
  factoryGroup.label = 'Factory';
  for (const name of Object.keys(FACTORY_PRESETS)) {
    const opt = document.createElement('option');
    opt.value = 'f:' + name;
    opt.textContent = name;
    factoryGroup.appendChild(opt);
  }
  presetSelect.appendChild(factoryGroup);

  // User group
  const userPresets = getUserPresets();
  const userNames = Object.keys(userPresets);
  if (userNames.length > 0) {
    const userGroup = document.createElement('optgroup');
    userGroup.label = 'User';
    for (const name of userNames) {
      const opt = document.createElement('option');
      opt.value = 'u:' + name;
      opt.textContent = name;
      userGroup.appendChild(opt);
    }
    presetSelect.appendChild(userGroup);
  }

  if (selectValue) presetSelect.value = selectValue;
  updateDeleteBtn();
}

function updateDeleteBtn() {
  presetDeleteBtn.disabled = !presetSelect.value.startsWith('u:');
}

function loadPreset(data) {
  // Send all params to synth engine
  synth.setParams(data);

  // Update waveform buttons
  if (data.waveform) setActiveWaveform(data.waveform);

  // Update gain slider
  if ('gain' in data) {
    gainSlider.value = data.gain;
    updateGainFill();
  }

  // Update knobs
  for (const [param, updater] of Object.entries(knobUpdaters)) {
    if (param in data) updater(data[param]);
  }
}

function getCurrentPatch() {
  const p = synth.params;
  // Convert back from Web Audio waveform names to our short names
  const fromWebWave = w => ({ sine: 'sine', sawtooth: 'saw', square: 'square', triangle: 'triangle' })[w] || 'saw';
  return {
    waveform: fromWebWave(p.osc1Wave),
    cutoff: p.cutoff,
    attack: p.attack,
    decay: p.decay,
    sustain: p.sustain,
    release: p.release,
    gain: p.gain,
    osc2_waveform: fromWebWave(p.osc2Wave),
    osc2_detune: p.osc2Detune,
    resonance: p.resonance,
    filter_env_amount: p.filterEnvAmount,
    chorus_depth: p.chorusDepth,
    chorus_rate: p.chorusRate,
    chorus_mix: p.chorusMix,
  };
}

presetSelect.addEventListener('change', () => {
  presetSelect.blur();
  const val = presetSelect.value;
  updateDeleteBtn();
  let data;
  if (val.startsWith('f:')) {
    data = FACTORY_PRESETS[val.slice(2)];
  } else if (val.startsWith('u:')) {
    data = getUserPresets()[val.slice(2)];
  }
  if (data) loadPreset(data);
});

presetSaveBtn.addEventListener('click', () => {
  presetSaveBtn.blur();
  const name = prompt('Preset name:');
  if (!name || !name.trim()) return;
  const trimmed = name.trim();

  if (FACTORY_PRESETS[trimmed]) {
    alert('Cannot overwrite a factory preset.');
    return;
  }

  const presets = getUserPresets();
  presets[trimmed] = getCurrentPatch();
  saveUserPresets(presets);
  rebuildPresetList('u:' + trimmed);
});

presetDeleteBtn.addEventListener('click', () => {
  presetDeleteBtn.blur();
  const val = presetSelect.value;
  if (!val.startsWith('u:')) return;
  const name = val.slice(2);

  if (!confirm('Delete preset "' + name + '"?')) return;

  const presets = getUserPresets();
  delete presets[name];
  saveUserPresets(presets);
  rebuildPresetList('f:Init');
});

// Initialize preset list
rebuildPresetList('f:Init');

// ── On-screen keyboard ──────────────────────────────────────────────────────

document.querySelectorAll('#keyboard button').forEach(b => {
  const note = () => parseInt(b.getAttribute('data-note'));

  b.addEventListener('pointerdown', e => {
    e.preventDefault();
    ensureAudio();
    synth.noteOn(note(), 100);
    b.classList.add('active');
  });
  b.addEventListener('pointerup', () => {
    synth.noteOff(note());
    b.classList.remove('active');
  });
  b.addEventListener('pointerleave', () => {
    synth.noteOff(note());
    b.classList.remove('active');
  });
});

// ── Computer keyboard mapping ────────────────────────────────────────────────

const keyMap = {
  // White keys
  z: 60, x: 62, c: 64, v: 65,
  b: 67, n: 69, m: 71, ',': 72, '.': 74, '/': 76,
  // Black keys
  s: 61, d: 63, g: 66, h: 68, j: 70, l: 73, ';': 75,
};

const pressedKeys = new Set();

function noteButtonForMidi(note) {
  return document.querySelector(`#keyboard button[data-note="${note}"]`);
}

window.addEventListener('keydown', ev => {
  const tag = document.activeElement && document.activeElement.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

  const k = ev.key.toLowerCase();
  if (!Object.prototype.hasOwnProperty.call(keyMap, k)) return;
  if (pressedKeys.has(k)) { ev.preventDefault(); return; }

  pressedKeys.add(k);
  ev.preventDefault();
  ensureAudio();
  const note = keyMap[k];
  noteButtonForMidi(note)?.classList.add('active');
  synth.noteOn(note, 100);
});

window.addEventListener('keyup', ev => {
  const k = ev.key.toLowerCase();
  if (!Object.prototype.hasOwnProperty.call(keyMap, k)) return;
  pressedKeys.delete(k);
  ev.preventDefault();
  const note = keyMap[k];
  noteButtonForMidi(note)?.classList.remove('active');
  synth.noteOff(note);
});

window.addEventListener('blur', () => {
  pressedKeys.forEach(k => {
    const note = keyMap[k];
    if (note) synth.noteOff(note);
    noteButtonForMidi(note)?.classList.remove('active');
  });
  pressedKeys.clear();
});
