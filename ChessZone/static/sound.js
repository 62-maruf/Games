"use strict";
/* Sound effects and background music, generated live with the Web Audio API (no audio files to download).
   Browsers only allow audio after the first tap/click, so nothing starts before that. */
const Sound = (() => {
  const cfg = {sound: true, soundVol: .7, music: false, musicVol: .4};
  const BAR = 6;                                                        // seconds per chord
  const CHORDS = [[57, 60, 64], [53, 57, 60], [48, 55, 64], [55, 59, 62]];   // Am - F - C - G (MIDI note numbers)
  let ctx = null, sfx = null, musicOut = null, noise = null, bus = null, timer = null, unlocked = false;
  const hz = midi => 440 * 2 ** ((midi - 69) / 12);

  function volumes() { if (ctx) { sfx.gain.value = cfg.soundVol; musicOut.gain.value = cfg.musicVol * 1.2; } }

  function init() {
    if (!unlocked) return null;
    if (!ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return null;
      ctx = new AudioCtx();
      sfx = ctx.createGain(); sfx.connect(ctx.destination);
      musicOut = ctx.createGain(); musicOut.connect(ctx.destination);
      noise = ctx.createBuffer(1, Math.floor(ctx.sampleRate * .3), ctx.sampleRate);
      const data = noise.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      volumes();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  /** One soft note with a smooth fade in and out. */
  function tone(freq, t, length, {type = "sine", gain = .2, attack = .005, to = sfx} = {}) {
    const osc = ctx.createOscillator(), amp = ctx.createGain();
    osc.type = type; osc.frequency.value = freq;
    amp.gain.setValueAtTime(.0001, t);
    amp.gain.exponentialRampToValueAtTime(gain, t + attack);
    amp.gain.exponentialRampToValueAtTime(.0001, t + length);
    osc.connect(amp); amp.connect(to); osc.start(t); osc.stop(t + length + .05);
  }

  /** The "tock" of a wooden piece on a board: a short filtered noise burst plus a low thump. */
  function knock(t, freq, gain, length = .07) {
    const src = ctx.createBufferSource(), filter = ctx.createBiquadFilter(), amp = ctx.createGain();
    src.buffer = noise; filter.type = "bandpass"; filter.frequency.value = freq; filter.Q.value = 1.2;
    amp.gain.setValueAtTime(gain, t);
    amp.gain.exponentialRampToValueAtTime(.0001, t + length);
    src.connect(filter); filter.connect(amp); amp.connect(sfx); src.start(t); src.stop(t + length + .02);
    tone(freq / 5, t, length * 1.6, {gain: gain * .8, attack: .002});
  }

  const run = (notes, gap, length, type = "triangle") => t => notes.forEach((m, i) => tone(hz(m), t + i * gap, length, {type, gain: .14}));
  const EFFECTS = {
    move: t => knock(t, 1100, .45),
    capture: t => { knock(t, 900, .7, .09); knock(t + .07, 1400, .45); },
    check: t => { knock(t, 1000, .45); tone(988, t + .06, .4, {gain: .12}); tone(1319, t + .16, .5, {gain: .1}); },
    start: run([72, 79], .12, .8, "sine"),
    win: run([72, 76, 79, 84], .12, .7),
    lose: run([67, 63, 60, 55], .16, .7),
    draw: run([72, 67], .18, .7),
  };

  function play(name) {
    if (!cfg.sound || !EFFECTS[name] || !init()) return;
    EFFECTS[name](ctx.currentTime + .01);
  }

  /* ---- music: slow chords plus a few bell notes, with a soft echo ---- */
  function makeBus() {
    const input = ctx.createGain(), filter = ctx.createBiquadFilter(), echo = ctx.createDelay(1), feedback = ctx.createGain();
    filter.type = "lowpass"; filter.frequency.value = 2200;
    echo.delayTime.value = .42; feedback.gain.value = .38;
    input.connect(filter); input.connect(echo); echo.connect(feedback); feedback.connect(echo); echo.connect(filter);
    filter.connect(musicOut);
    return {input, filter};
  }
  function playBar(t, chord, to) {
    chord.forEach(m => tone(hz(m), t, BAR + 1.5, {type: "triangle", gain: .05, attack: 1.8, to}));
    for (let i = 0; i < 6; i++) {
      if (Math.random() < .25) continue;                                 // leave some silence
      const m = chord[Math.floor(Math.random() * 3)] + (Math.random() < .5 ? 12 : 24);
      tone(hz(m), t + i + Math.random() * .3, 3, {gain: .07, attack: .01, to});
    }
  }
  function startMusic() {
    if (timer || !init()) return;
    bus = makeBus();
    let next = ctx.currentTime + .2, bar = Math.floor(Math.random() * CHORDS.length);
    const schedule = () => { for (; next < ctx.currentTime + 2; next += BAR) playBar(next, CHORDS[bar++ % CHORDS.length], bus.input); };
    schedule(); timer = setInterval(schedule, 500);
  }
  function stopMusic() {
    if (!timer) return;
    clearInterval(timer); timer = null;
    const old = bus;
    old.input.gain.setTargetAtTime(0, ctx.currentTime, .25);              // fade out, then cut the echo tail
    setTimeout(() => old.filter.disconnect(), 1200);
  }

  function config(next) {
    Object.assign(cfg, next);
    volumes();
    if (cfg.music) startMusic(); else stopMusic();
  }

  const unlock = () => { unlocked = true; if (cfg.music) startMusic(); };
  addEventListener("pointerdown", unlock, {once: true});
  addEventListener("keydown", unlock, {once: true});
  document.addEventListener("visibilitychange", () => {                  // be quiet (and save battery) in background tabs
    if (ctx) document.hidden ? ctx.suspend() : ctx.resume();
  });

  return {play, config};
})();
