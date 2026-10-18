"use strict";
const $ = id => document.getElementById(id);
const socket = io();

const FILES = "abcdefgh";
const POINTS = {p: 1, n: 3, b: 3, r: 5, q: 9};
const SIDE = {w: "White", b: "Black"};
const PIECE = {k: "king", q: "queen", r: "rook", b: "bishop", n: "knight", p: "pawn"};
const DIALOGS = ["wait", "noopp", "promo", "drawq", "over"];

let G = null;                       // latest game state sent by the server
let grid = {};                      // square -> piece letter, from the FEN ("P" = white pawn, "p" = black pawn)
let selected = null, flipped = false, overDismissed = false;
let waitEnds = 0, waitTotal = 1;

/* ---------- settings (saved on this device) ---------- */
const DEFAULTS = {hints: true, lastMove: true, coords: true, sound: true, soundVol: .7, music: false, musicVol: .4};
const settings = {...DEFAULTS};
try {
  const saved = JSON.parse(localStorage.getItem("chessSettings")) || {};
  for (const key in DEFAULTS) if (typeof saved[key] === typeof DEFAULTS[key]) settings[key] = saved[key];
} catch (e) { /* storage blocked or damaged: use defaults */ }

const opp = side => side === "w" ? "b" : "w";
const esc = text => String(text).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const playerName = () => $("name").value.trim();
const upsideDown = () => G.mode === "local" && $("layout").value === "face";   // black pieces face the other player
const myTurn = () => G && !G.over && !G.thinking && (G.mode === "local" || G.you === G.turn);
const orientation = () => G.mode === "local" ? ($("layout").value === "flip" ? G.turn : "w") : (flipped ? opp(G.you) : G.you);

/** One piece as inline SVG. The drawing itself lives in _pieces.svg. */
function piece(type, color, extra = "") {
  const mini = extra === "mini";
  return `<svg class="pc ${color} ${extra}" viewBox="0 0 100 100" role="img" aria-label="${SIDE[color]} ${PIECE[type]}">` +
         `<use href="#${type}" fill="url(#g${color})"${mini ? "" : ' filter="url(#bevel)"'}/></svg>`;
}

function toast(text) {
  const el = $("toast");
  el.textContent = text; el.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove("show"), 2600);
}
function showDialog(id) {            // opens one dialog and closes the others; null closes all
  for (const name of DIALOGS) {
    const dialog = $(name);
    if (name === id) { if (!dialog.open) dialog.showModal(); } else if (dialog.open) dialog.close();
  }
}
function showScreen(name) { $("menu").hidden = name !== "menu"; $("game").hidden = name !== "game"; }
function goToMenu() { G = null; selected = null; showDialog(null); showScreen("menu"); }

function parseFen(fen) {
  const result = {};
  fen.split(" ")[0].split("/").forEach((row, i) => {
    let file = 0;
    for (const ch of row) { if (/\d/.test(ch)) file += +ch; else result[FILES[file++] + (8 - i)] = ch; }
  });
  return result;
}

/* ---------- drawing ---------- */
function drawBoard() {
  const view = orientation(), upside = upsideDown();
  const targets = selected && settings.hints ? G.legal[selected] || [] : [];
  const pawnSelected = selected && grid[selected].toLowerCase() === "p";
  let html = "";
  for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
    const file = view === "w" ? c : 7 - c, rank = view === "w" ? 8 - r : r + 1, sq = FILES[file] + rank, ch = grid[sq];
    const color = ch && ch === ch.toUpperCase() ? "w" : "b";
    const cls = ["sq", (file + rank) % 2 ? "dark" : "light"];
    if (settings.lastMove && G.last && G.last.includes(sq)) cls.push("last");
    if (sq === selected) cls.push("sel");
    if (sq === G.check) cls.push("check");
    if (targets.includes(sq)) cls.push(ch || (pawnSelected && sq[0] !== selected[0]) ? "cap" : "dot");   // 2nd case: en passant
    html += `<div class="${cls.join(" ")}" data-sq="${sq}" role="gridcell" aria-label="${sq}">` +
            (ch ? piece(ch.toLowerCase(), color, upside && color === "b" ? "up" : "") : "") + `</div>`;
  }
  $("board").innerHTML = html;
  $("files").hidden = $("ranks").hidden = !settings.coords;
  const labels = (items) => items.map(x => `<span>${x}</span>`).join("");
  $("files").innerHTML = labels([...Array(8)].map((_, i) => FILES[view === "w" ? i : 7 - i]));
  $("ranks").innerHTML = labels([...Array(8)].map((_, i) => view === "w" ? 8 - i : i + 1));
}

function cardHtml(side) {
  const mine = G.taken[side], theirs = G.taken[opp(side)];
  const sum = list => list.reduce((total, p) => total + POINTS[p], 0);
  const lead = sum(mine) - sum(theirs);
  const turn = !G.over && G.turn === side;
  let note = "";
  if (G.mode === "local" && turn) note = G.check ? "Your move: check!" : "Your move";
  if (G.thinking && turn) note = "thinking…";
  const buttons = G.mode === "local" && !G.over
    ? `<button class="btn mini-btn" data-act="resign" data-side="${side}">Resign</button><button class="btn mini-btn" data-act="draw" data-side="${side}">Draw</button>` : "";
  return `<span class="swatch ${side}"></span><b>${esc(G.names[side])}</b><span class="note">${note}</span>` +
         `<span class="taken">${mine.map(p => piece(p, opp(side), "mini")).join("")}${lead > 0 ? `<small>+${lead}</small>` : ""}</span>${buttons}`;
}
function drawCards() {
  const bottom = orientation(), upside = upsideDown();
  for (const [id, side] of [["botCard", bottom], ["topCard", opp(bottom)]]) {
    $(id).innerHTML = cardHtml(side);
    $(id).className = "pcard" + (!G.over && G.turn === side ? " turn" : "") + (upside && side === "b" ? " up" : "");
  }
}
function drawMoves() {
  let html = "";
  for (let i = 0; i < G.moves.length; i += 2)
    html += `<div><b>${i / 2 + 1}.</b><span>${esc(G.moves[i])}</span><span>${esc(G.moves[i + 1] || "")}</span></div>`;
  $("moves").innerHTML = html;
  $("moves").scrollTop = $("moves").scrollHeight;
}
function drawControls() {
  const local = G.mode === "local";
  $("bFlip").hidden = local;
  $("bDraw").hidden = $("bResign").hidden = local || G.over;
  $("bRematch").hidden = !G.over || G.opponent_gone;
  $("layout").hidden = !local;
  $("bRematch").textContent = G.rematch_me ? "Waiting…" : G.rematch_other ? "Accept rematch" : "Rematch";
  $("bRematch").disabled = G.rematch_me;
}

function resultTitle() {
  if (G.winner === null) return "Draw";
  if (G.mode === "local") return `${G.names[G.winner]} wins!`;
  return G.winner === G.you ? "You win!" : "You lose";
}
function statusText() {
  if (G.over) return `${resultTitle()} (${G.reason})`;
  if (G.draw_offer && G.mode === "online" && G.draw_offer === G.you) return "Draw offer sent…";
  if (G.thinking) return "Computer is thinking…";
  const check = G.check ? " Check!" : "";
  if (G.mode === "local") return `${G.names[G.turn]} to move.${check}`;
  return (G.turn === G.you ? "Your move." : `${G.names[G.turn]} is thinking…`) + check;
}
function showPrompts() {
  const local = G.mode === "local";
  const drawForMe = !G.over && G.draw_offer && (local || G.draw_offer !== G.you);
  if (drawForMe) {
    $("drawText").textContent = local ? `${G.names[G.draw_offer]} offers a draw. ${G.names[opp(G.draw_offer)]}, accept?`
                                      : `${G.names[G.draw_offer]} offers a draw`;
    $("drawq").classList.toggle("flip", upsideDown() && opp(G.draw_offer) === "b");
  }
  if (G.over) {
    $("overTitle").textContent = resultTitle();
    $("overText").textContent = G.reason === "opponent left" ? "Your opponent left the game." : `Game over by ${G.reason}.`;
    $("bOverRematch").hidden = G.opponent_gone;
    $("bOverRematch").textContent = $("bRematch").textContent;
    $("bOverRematch").disabled = G.rematch_me;
  }
  showDialog(drawForMe ? "drawq" : G.over && !overDismissed ? "over" : null);
}
function render() {
  grid = parseFen(G.fen);
  if (selected && !(G.legal[selected] && myTurn())) selected = null;
  drawBoard(); drawCards(); drawMoves(); drawControls();
  $("status").textContent = statusText();
  showPrompts();
}

/* ---------- playing ---------- */
function sendMove(from, to, promotion) { selected = null; socket.emit("move", {from, to, promotion}); }
function askPromotion(from, to) {
  const side = G.turn;
  $("promo").classList.toggle("flip", upsideDown() && side === "b");
  $("promoBtns").innerHTML = [..."qrbn"].map(p => `<button class="btn" data-promo="${p}" aria-label="${PIECE[p]}">${piece(p, side)}</button>`).join("");
  $("promoBtns").onclick = e => {
    const choice = e.target.closest("[data-promo]");
    if (choice) { showDialog(null); sendMove(from, to, choice.dataset.promo); }
  };
  showDialog("promo");
}
$("board").onclick = e => {
  const el = e.target.closest(".sq");
  if (!el || !myTurn()) return;
  const sq = el.dataset.sq;
  if (selected && (G.legal[selected] || []).includes(sq)) {
    const promotes = grid[selected].toLowerCase() === "p" && (sq[1] === "8" || sq[1] === "1");
    return promotes ? askPromotion(selected, sq) : sendMove(selected, sq);
  }
  selected = G.legal[sq] && selected !== sq ? sq : null;
  drawBoard();
};
document.addEventListener("click", e => {          // Resign / Draw buttons inside the player cards (face to face mode)
  const button = e.target.closest("[data-act]");
  if (!button || !G) return;
  const side = button.dataset.side;
  if (button.dataset.act === "resign" && confirm(`${G.names[side]}: resign this game?`)) socket.emit("resign", {side});
  if (button.dataset.act === "draw") socket.emit("offer_draw", {side});
});

/* ---------- buttons ---------- */
const emitBot = (level, color) => socket.emit("play_bot", {name: playerName(), level, color});
$("bOnline").onclick = () => socket.emit("play_online", {name: playerName()});
$("bBot").onclick = () => emitBot($("level").value, $("color").value);
$("bLocal").onclick = () => socket.emit("play_local");
document.querySelectorAll("[data-bot]").forEach(b => b.onclick = () => emitBot(b.dataset.bot, "random"));
$("bCancel1").onclick = $("bCancel2").onclick = () => { socket.emit("cancel"); showDialog(null); };
$("bKeep").onclick = () => socket.emit("wait_more");
$("bResign").onclick = () => confirm("Resign this game?") && socket.emit("resign", {});
$("bDraw").onclick = () => { socket.emit("offer_draw", {}); if (G.mode === "online") toast("Draw offer sent"); };
$("bFlip").onclick = () => { flipped = !flipped; drawBoard(); drawCards(); };
$("bRematch").onclick = $("bOverRematch").onclick = () => socket.emit("rematch");
$("bLeave").onclick = $("bOverMenu").onclick = () => { socket.emit("leave"); goToMenu(); };
$("bOverView").onclick = () => { overDismissed = true; showDialog(null); };
$("bAcceptDraw").onclick = () => socket.emit("draw_response", {accept: true});
$("bDeclineDraw").onclick = () => socket.emit("draw_response", {accept: false});
$("layout").onchange = () => G && render();
document.addEventListener("cancel", e => { if (e.target.id !== "settings") e.preventDefault(); }, true);   // Esc must not close dialogs the game is waiting on

try { $("name").value = localStorage.getItem("chessName") || ""; } catch (e) { /* storage blocked: ignore */ }
$("name").oninput = () => { try { localStorage.setItem("chessName", playerName()); } catch (e) { /* ignore */ } };

setInterval(() => {
  if (!$("wait").open) return;
  const left = Math.max(0, waitEnds - Date.now());
  $("waitBar").style.width = `${left / waitTotal * 100}%`;
  $("waitText").textContent = `Waiting for another player… ${Math.ceil(left / 1000)}s`;
}, 250);

/* ---------- settings panel ---------- */
document.querySelectorAll("[data-settings]").forEach(b => b.onclick = () => $("settings").showModal());
$("bCloseSettings").onclick = () => $("settings").close();
document.querySelectorAll("[data-set]").forEach(input => {
  const key = input.dataset.set;
  if (input.type === "checkbox") input.checked = settings[key]; else input.value = settings[key];
  input.oninput = () => {
    settings[key] = input.type === "checkbox" ? input.checked : +input.value;
    try { localStorage.setItem("chessSettings", JSON.stringify(settings)); } catch (e) { /* ignore */ }
    applySettings();
  };
  if (input.type === "range") input.onchange = () => Sound.play("move");              // let the player hear the new volume
});
$("settings").addEventListener("click", e => { if (e.target === $("settings")) $("settings").close(); });   // tap outside
function applySettings() { Sound.config(settings); if (G) drawBoard(); }
applySettings();

/** Pick the right sound by comparing the new game state with the previous one. */
function playSounds(before, now) {
  if (!before || before.id !== now.id || (before.moves.length > 0 && now.moves.length === 0)) return Sound.play("start");
  if (now.moves.length > before.moves.length) {
    const san = now.moves[now.moves.length - 1];
    Sound.play(/[+#]/.test(san) ? "check" : san.includes("x") ? "capture" : "move");
  }
  if (now.over && !before.over)
    setTimeout(() => Sound.play(now.winner === null ? "draw" : now.mode === "local" || now.winner === now.you ? "win" : "lose"), 350);
}

/* ---------- messages from the server ---------- */
socket.on("lobby", info => {
  $("lobbyInfo").textContent = `${info.waiting} waiting · ${info.playing} online game${info.playing === 1 ? "" : "s"}`;
});
socket.on("queued", info => { waitTotal = info.wait * 1000; waitEnds = Date.now() + waitTotal; showDialog("wait"); });
socket.on("no_opponent", () => showDialog("noopp"));
socket.on("notice", info => toast(info.text));
socket.on("game", state => {
  if (!G || G.id !== state.id || state.moves.length === 0) { flipped = false; selected = null; overDismissed = false; }
  playSounds(G, state);
  G = state;
  showScreen("game");
  render();
});
socket.on("disconnect", () => {
  if (G) toast("Connection lost");
  goToMenu();
  $("lobbyInfo").textContent = "Reconnecting…";
});
