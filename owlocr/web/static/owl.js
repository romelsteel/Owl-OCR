'use strict';
// Pixel-art owl mascot (design 10.5): 16 x 16 grids drawn as SVG rectangles.
// sleeping = engine stopped, awake = ready/loading, reading = busy (eyes move), ruffled = error.
// Five clicks: the owl hoots and turns its head.
window.OwlMascot = (function () {
  const PALETTE = {
    k: '#2b2233', b: '#8a5a3c', l: '#b98552', c: '#f1dfb8',
    w: '#fffbea', p: '#1b1b1b', y: '#f2b632', f: '#e0a020'
  };
  const FRAMES = /*FRAMES-BEGIN*/{
    "sleeping": [
      "..k..........k..",
      "..kk........kk..",
      "..klk......klk..",
      "..kllkkkkkkllk..",
      ".kbbbbbbbbbbbbk.",
      ".kbbbbbbbbbbbbk.",
      ".kbbbbbbbbbbbbk.",
      ".kbkkkkbbkkkkbk.",
      ".kbbbbbyybbbbbk.",
      ".kbbbbbyybbbbbk.",
      ".kbbccccccccbbk.",
      ".kbccccccccccbk.",
      ".kbcclcclcclcbk.",
      "..kbccccccccbk..",
      "...kkkkkkkkkk...",
      "....ff....ff...."
    ],
    "awake": [
      "..k..........k..",
      "..kk........kk..",
      "..klk......klk..",
      "..kllkkkkkkllk..",
      ".kbbbbbbbbbbbbk.",
      ".kbwwwwbbwwwwbk.",
      ".kbwppwbbwppwbk.",
      ".kbwppwbbwppwbk.",
      ".kbwwwwyywwwwbk.",
      ".kbbbbbyybbbbbk.",
      ".kbbccccccccbbk.",
      ".kbccccccccccbk.",
      ".kbcclcclcclcbk.",
      "..kbccccccccbk..",
      "...kkkkkkkkkk...",
      "....ff....ff...."
    ],
    "reading_left": [
      "..k..........k..",
      "..kk........kk..",
      "..klk......klk..",
      "..kllkkkkkkllk..",
      ".kbbbbbbbbbbbbk.",
      ".kbwwwwbbwwwwbk.",
      ".kbppwwbbppwwbk.",
      ".kbppwwbbppwwbk.",
      ".kbwwwwyywwwwbk.",
      ".kbbbbbyybbbbbk.",
      ".kbbccccccccbbk.",
      ".kbccccccccccbk.",
      ".kbcclcclcclcbk.",
      "..kbccccccccbk..",
      "...kkkkkkkkkk...",
      "....ff....ff...."
    ],
    "reading_right": [
      "..k..........k..",
      "..kk........kk..",
      "..klk......klk..",
      "..kllkkkkkkllk..",
      ".kbbbbbbbbbbbbk.",
      ".kbwwwwbbwwwwbk.",
      ".kbwwppbbwwppbk.",
      ".kbwwppbbwwppbk.",
      ".kbwwwwyywwwwbk.",
      ".kbbbbbyybbbbbk.",
      ".kbbccccccccbbk.",
      ".kbccccccccccbk.",
      ".kbcclcclcclcbk.",
      "..kbccccccccbk..",
      "...kkkkkkkkkk...",
      "....ff....ff...."
    ],
    "ruffled": [
      ".k.k........k.k.",
      "..kk..k..k..kk..",
      ".kklk......klkk.",
      "..kllkkkkkkllk..",
      "kkbbbbbbbbbbbbkk",
      ".kbwwwwbbwwwwbk.",
      ".kbwwwwbbwwwwbk.",
      ".kbwwpwbbwpwwbk.",
      ".kbwwwwyywwwwbk.",
      "kkbbbbbyybbbbbkk",
      ".kbbccccccccbbk.",
      "kkbccccccccccbkk",
      ".kbcclcclcclcbk.",
      "..kbccccccccbk..",
      "...kkkkkkkkkk...",
      "....ff....ff...."
    ],
    "turned": [
      "..k..........k..",
      "..kk........kk..",
      "..klk......klk..",
      "..kllkkkkkkllk..",
      ".kbbbbbbbbbbbbk.",
      ".kbbbbbbbbbbbbk.",
      ".kblbbblbbblbbk.",
      ".kbbbbbbbbbbbbk.",
      ".kbblbbbblbbbbk.",
      ".kbbbbbbbbbbbbk.",
      ".kbbccccccccbbk.",
      ".kbccccccccccbk.",
      ".kbcclcclcclcbk.",
      "..kbccccccccbk..",
      "...kkkkkkkkkk...",
      "....ff....ff...."
    ]
  }/*FRAMES-END*/;

  let el = null;
  let state = null;
  let frameTimer = null;
  let turning = false;
  let clicks = 0;
  let clickTimer = null;
  let onHoot = function () {};

  const SVG_NS = 'http://www.w3.org/2000/svg';

  function node(tag, attrs) {
    const n = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs).forEach(function (k) { n.setAttribute(k, String(attrs[k])); });
    return n;
  }

  // Built with DOM calls (no innerHTML); runs of one colour in a row become one rectangle.
  function svg(name) {
    const rows = FRAMES[name];
    const out = node('svg', { viewBox: '0 0 16 16', 'shape-rendering': 'crispEdges', 'aria-hidden': 'true' });
    rows.forEach(function (row, y) {
      let x = 0;
      while (x < 16) {
        const ch = row[x];
        let w = 1;
        while (x + w < 16 && row[x + w] === ch) w++;
        if (ch !== '.') out.appendChild(node('rect', { x: x, y: y, width: w, height: 1, fill: PALETTE[ch] }));
        x += w;
      }
    });
    return out;
  }

  function show(name) { el.replaceChildren(svg(name)); }

  function stateFor(engine, hasError) {
    if (hasError) return 'ruffled';
    if (engine === 'busy') return 'reading';
    if (engine === 'ready' || engine === 'loading') return 'awake';
    return 'sleeping';
  }

  function apply() {
    clearInterval(frameTimer);
    frameTimer = null;
    if (!el || turning) return;
    el.dataset.state = state;
    if (state === 'reading') {
      let right = false;
      show('reading_left');
      frameTimer = setInterval(function () {
        right = !right;
        show(right ? 'reading_right' : 'reading_left');
      }, 450);
    } else {
      show(state);
    }
  }

  function setState(engine, hasError) {
    const next = stateFor(engine, hasError);
    if (next === state) return;
    state = next;
    apply();
  }

  function hootSound() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      [0, 0.45].forEach(function (start) {
        const t0 = ctx.currentTime + start;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(420, t0);
        osc.frequency.exponentialRampToValueAtTime(330, t0 + 0.35);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.4);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t0);
        osc.stop(t0 + 0.42);
      });
      setTimeout(function () { ctx.close(); }, 1500);
    } catch (e) { /* no sound available: the toast is enough */ }
  }

  function hoot() {
    turning = true;
    clearInterval(frameTimer);
    el.classList.add('turning');
    show('turned');
    hootSound();
    onHoot();
    setTimeout(function () {
      turning = false;
      el.classList.remove('turning');
      apply();
    }, 1200);
  }

  function init(element, hootCallback) {
    el = element;
    onHoot = hootCallback || onHoot;
    el.addEventListener('click', function () {
      clicks++;
      clearTimeout(clickTimer);
      clickTimer = setTimeout(function () { clicks = 0; }, 2500);
      if (clicks >= 5) {
        clicks = 0;
        hoot();
      }
    });
    setState('stopped', false);
  }

  return { init: init, setState: setState };
})();
