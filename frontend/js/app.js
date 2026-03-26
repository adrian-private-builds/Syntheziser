// frontend/js/app.js

const synth = new WebSynth();

// ── Auto-start audio on first interaction ────────────────────────────────────

let audioStarted = false;

function ensureAudio() {
  if (audioStarted) return;
  audioStarted = true;
  synth.start();
}

// ── Waveform buttons ─────────────────────────────────────────────────────────

document.querySelectorAll('.wave-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.wave-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
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

// ── Rotary knobs ─────────────────────────────────────────────────────────────

const MIN_ANGLE = -135;
const MAX_ANGLE = 135;
// The indicator dot in knob_center.svg sits at ~49° from 12-o'clock when unrotated
const KNOB_DOT_OFFSET = 49;

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

  knobEl.addEventListener('pointerup', () => { dragging = false; });
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
