// Lanewise front end: fetch a report, render tabs. No framework, no build step.
const $ = (s) => document.querySelector(s);
const ROLE = { TOP: "Top", JUNGLE: "Jungle", MIDDLE: "Mid", BOTTOM: "Bot", UTILITY: "Support" };
const MAP = 14870;
let DD = "16.21.1";
let REPORT = null;
const mapImg = new Image();

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pctColor = (p) => (p >= 60 ? "var(--good)" : p <= 40 ? "var(--bad)" : "var(--mid)");
const icon = (key) => `https://ddragon.leagueoflegends.com/cdn/${DD}/img/champion/${encodeURIComponent(key)}.png`;
const ord = (n) => n + (["th", "st", "nd", "rd"][(n % 100 - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th");

async function init() {
  try {
    const v = await (await fetch("https://ddragon.leagueoflegends.com/api/versions.json")).json();
    DD = v[0];
  } catch (_) { /* keep default */ }
  mapImg.crossOrigin = "anonymous";
  mapImg.src = `https://ddragon.leagueoflegends.com/cdn/${DD}/img/map/map11.png`;
  mapImg.onload = () => REPORT && drawMap();
  const meta = await (await fetch("/api/meta")).json();
  $("#platform").innerHTML = Object.entries(meta.platforms).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  const q = new URLSearchParams(location.search);
  if (q.get("riot_id")) { $("#riotid").value = q.get("riot_id"); $("#platform").value = q.get("platform") || "euw1"; load(); }
}

$("#search").addEventListener("submit", (e) => { e.preventDefault(); load(); });
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== "tab-" + b.dataset.tab));
  if (b.dataset.tab === "heatmap") drawMap();
  if (b.dataset.tab === "habits") drawHours();
}));
["#hm-phase", "#hm-champ", "#hm-mirror", "#hm-events"].forEach((s) => $(s).addEventListener("change", drawMap));

async function load() {
  const riot_id = $("#riotid").value.trim(), platform = $("#platform").value, count = $("#count").value;
  const st = $("#status");
  st.className = ""; st.textContent = "Fetching your ranked games… this takes a few seconds the first time.";
  $("#report").classList.add("hidden");
  history.replaceState(null, "", `?riot_id=${encodeURIComponent(riot_id)}&platform=${platform}`);
  try {
    const r = await fetch(`/api/report?riot_id=${encodeURIComponent(riot_id)}&platform=${platform}&count=${count}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Something went wrong");
    if (!data.player.games_analyzed) throw new Error("No ranked solo games found recently for this account.");
    REPORT = data;
    st.className = "hidden";
    $("#intro").classList.add("hidden");
    render();
  } catch (e) { st.className = "error"; st.textContent = e.message; }
}

function render() {
  const p = REPORT.player, a = REPORT.aspects;
  $("#report").classList.remove("hidden");
  $("#pname").textContent = p.riot_id;
  $("#prank").textContent = (p.rank ? `${cap(p.rank.tier)} ${p.rank.division ?? ""} · ${p.rank.lp} LP · ${p.rank.wins}W ${p.rank.losses}L` : "Unranked")
    + ` · ${p.games_analyzed} games analyzed · main role ${ROLE[a.main_role] || a.main_role}`;
  $("#poverall").textContent = a.overall != null ? ord(a.overall) : "-";
  $("#benchnote").textContent = `Percentiles against ${cap(p.benchmark_tier)} players in the same role, adjusted for champion. 50th = typical.`;
  renderOverview(); renderPool(); renderHabits(); renderMatches();
  const champs = [...new Set(REPORT.heatmap.map((g) => g.champion))];
  $("#hm-champ").innerHTML = `<option value="">All</option>` + champs.map((c) => `<option>${esc(c)}</option>`).join("");
  drawMap();
}
const cap = (s) => (s ? s[0] + s.slice(1).toLowerCase() : "");

// ------------------------------------------------------------------ overview
function renderOverview() {
  const asp = REPORT.aspects.aspects || {};
  const names = Object.keys(asp);
  radar(names, names.map((n) => asp[n].percentile));
  const s = REPORT.aspects;
  $("#sf").innerHTML =
    (s.strengths.length ? `<p><b class="win">Strengths</b></p>` + s.strengths.map((n) =>
      `<div class="trait"><b>${n}</b>: ${ord(asp[n].percentile)} percentile.</div>`).join("") : "") +
    (s.focus.length ? `<p><b class="loss">Focus on</b></p>` + s.focus.map((n) =>
      `<div class="trait"><b>${n}</b>: ${ord(asp[n].percentile)} percentile. ${esc(asp[n].tip)}</div>`).join("") : "") +
    (!s.strengths.length && !s.focus.length ? `<p class="muted">Balanced: every aspect is close to typical for your rank.</p>` : "");
  $("#aspects").innerHTML = names.map((n) => {
    const v = asp[n];
    const rows = v.details.map((d) => `<tr><td>${esc(d.metric)}${d.lower_is_better ? ' <span class="muted small">(lower is better)</span>' : ""}</td>
      <td class="num">${fmt(d.you)}</td><td class="num muted">${fmt(d.typical)}</td>
      <td class="num" style="color:${pctColor(d.percentile)}">${d.percentile != null ? ord(d.percentile) : "-"}</td></tr>`).join("");
    return `<div class="aspect"><div class="aspect-head"><span>${n}</span><span style="color:${pctColor(v.percentile)}">${ord(v.percentile)}</span></div>
      <div class="bar"><i style="width:${v.percentile}%;background:${pctColor(v.percentile)}"></i><span class="mark"></span></div>
      <table><tr><th>Measure</th><th class="num">You</th><th class="num">Typical</th><th class="num">Percentile</th></tr>${rows}</table></div>`;
  }).join("");
}
const fmt = (x) => (x == null ? "-" : Math.abs(x) >= 100 ? Math.round(x) : Math.round(x * 100) / 100);

function radar(labels, values) {
  const svg = $("#radar"), cx = 180, cy = 170, R = 120, n = labels.length;
  const pt = (i, r) => [cx + r * Math.sin((2 * Math.PI * i) / n), cy - r * Math.cos((2 * Math.PI * i) / n)];
  let h = "";
  [25, 50, 75, 100].forEach((lv) => {
    h += `<polygon points="${labels.map((_, i) => pt(i, (R * lv) / 100).join(",")).join(" ")}" fill="none" stroke="${lv === 50 ? "#4a5566" : "#263040"}" ${lv === 50 ? 'stroke-dasharray="4 3"' : ""}/>`;
  });
  labels.forEach((l, i) => {
    const [x, y] = pt(i, R + 22);
    h += `<line x1="${cx}" y1="${cy}" x2="${pt(i, R)[0]}" y2="${pt(i, R)[1]}" stroke="#263040"/>`;
    h += `<text x="${x}" y="${y}" fill="#aab3c0" font-size="12" text-anchor="middle" dominant-baseline="middle">${l} ${values[i]}</text>`;
  });
  h += `<polygon points="${values.map((v, i) => pt(i, (R * v) / 100).join(",")).join(" ")}" fill="rgba(63,182,196,.25)" stroke="#3fb6c4" stroke-width="2"/>`;
  svg.innerHTML = h;
}

// ------------------------------------------------------------------ heatmap
function drawMap() {
  if (!REPORT) return;
  const c = $("#map"), ctx = c.getContext("2d"), W = c.width;
  const phase = $("#hm-phase").value, champ = $("#hm-champ").value;
  const mirror = $("#hm-mirror").checked, events = $("#hm-events").checked;
  const inPhase = (m) => phase === "all" || (phase === "early" ? m < 14 : phase === "mid" ? m >= 14 && m < 25 : m >= 25);
  const toXY = (x, y, team) => {
    if (mirror && team === 200) { x = MAP - x; y = MAP - y; }
    return [(x / MAP) * W, W - (y / MAP) * W];
  };
  ctx.clearRect(0, 0, W, W);
  if (mapImg.complete && mapImg.naturalWidth) { ctx.globalAlpha = 0.55; ctx.drawImage(mapImg, 0, 0, W, W); ctx.globalAlpha = 1; }
  // density on an offscreen grid, then colour it
  const G = 128, grid = new Float32Array(G * G);
  let samples = 0, kills = [], deaths = [];
  REPORT.heatmap.filter((g) => !champ || g.champion === champ).forEach((g) => {
    g.positions.forEach(([m, x, y]) => {
      if (!inPhase(m)) return;
      const [px, py] = toXY(x, y, g.team);
      const gx = Math.floor((px / W) * G), gy = Math.floor((py / W) * G);
      for (let dx = -4; dx <= 4; dx++) for (let dy = -4; dy <= 4; dy++) {
        const X = gx + dx, Y = gy + dy;
        if (X >= 0 && Y >= 0 && X < G && Y < G) grid[Y * G + X] += Math.exp(-(dx * dx + dy * dy) / 6);
      }
      samples++;
    });
    g.kills.forEach(([m, x, y]) => inPhase(m) && kills.push(toXY(x, y, g.team)));
    g.deaths.forEach(([m, x, y]) => inPhase(m) && deaths.push(toXY(x, y, g.team)));
  });
  // scale to the 98th percentile so a few camping spots (fountain) don't wash everything else out
  const sorted = Array.from(grid).filter((v) => v > 0).sort((a, b) => a - b);
  const max = sorted[Math.floor(sorted.length * 0.98)] || 1, img = ctx.createImageData(G, G);
  for (let i = 0; i < G * G; i++) {
    const v = Math.min(1, grid[i] / max);
    // transparent -> blue -> yellow -> red
    const r = v < 0.5 ? 60 + 390 * v : 255, gch = v < 0.5 ? 120 + 200 * v : 220 - 300 * (v - 0.5), b = v < 0.5 ? 220 - 400 * v : 20;
    img.data[i * 4] = r; img.data[i * 4 + 1] = Math.max(0, gch); img.data[i * 4 + 2] = Math.max(0, b);
    img.data[i * 4 + 3] = v < 0.12 ? 0 : Math.round(60 + 170 * v);
  }
  const off = document.createElement("canvas"); off.width = G; off.height = G;
  off.getContext("2d").putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true; ctx.drawImage(off, 0, 0, W, W);
  if (events) {
    const dot = (pts, col) => pts.forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x, y, 4, 0, 7); ctx.fillStyle = col; ctx.fill(); ctx.strokeStyle = "#000"; ctx.stroke(); });
    dot(kills, "#4cc38a"); dot(deaths, "#e5656b");
  }
  $("#hm-summary").textContent = `${samples} position samples, ${kills.length} takedowns, ${deaths.length} deaths.` +
    (mirror ? " Red-side games are flipped so your base is always bottom-left." : "");
}

// ------------------------------------------------------------------ champion pool
function renderPool() {
  const p = REPORT.champion_pool;
  $("#pool").innerHTML = `<p class="muted small">${p.unique_champions} champions in your recent games. The score is your average
    overall percentile on that champion compared with similar players. 50 is typical.</p>
    <table><tr><th>Champion</th><th>Role</th><th class="num">Games</th><th class="num">Win</th><th class="num">Score</th>
    <th>Best / worst</th><th>Verdict</th><th>Watch out for</th></tr>` +
    p.champions.map((c) => `<tr><td><div class="champ"><img src="${icon(c.champion)}" alt="">${esc(c.name || c.champion)}</div>
      <div class="muted small">${esc(c.class || "")}${c.scaling ? " · " + esc(c.scaling) : ""}${c.mastery_points ? " · " + c.mastery_points.toLocaleString() + " pts" : ""}</div></td>
      <td>${ROLE[c.role] || c.role}</td><td class="num">${c.games}</td><td class="num">${Math.round((100 * c.wins) / c.games)}%</td>
      <td class="num" style="color:${pctColor(c.score)}">${c.score}</td>
      <td class="small">${esc(c.best_aspect || "")} / ${esc(c.worst_aspect || "")}</td><td class="small">${esc(c.verdict)}</td>
      <td class="small">${c.hard_matchups.slice(0, 3).map((m) => esc(m.name)).join(", ")}</td></tr>`).join("") + "</table>";
  $("#suggest").innerHTML = p.suggestions.length ? p.suggestions.map((s) =>
    `<div class="trait"><div class="champ"><img src="${icon(s.key)}" alt=""><b>${esc(s.champion)}</b></div>
     <span class="muted small">Plays a lot like ${esc(s.because)}, one of your best champions.</span></div>`).join("")
    : `<p class="muted">Play a few more games so we can find your best champions.</p>`;
  $("#legacy").innerHTML = p.legacy.length ? p.legacy.map((l) =>
    `<div class="kv"><span>${esc(l.champion)}</span><span class="muted">${l.mastery_points.toLocaleString()} pts · last played ${daysAgo(l.last_play)}</span></div>`).join("")
    : `<p class="muted">No other high-mastery champions.</p>`;
}
const daysAgo = (t) => { const d = Math.round((Date.now() / 1000 - t) / 86400); return d <= 0 ? "today" : `${d} days ago`; };

// ------------------------------------------------------------------ habits
function renderHabits() {
  $("#traits").innerHTML = REPORT.traits.length ? REPORT.traits.map((t) => `<div class="trait"><b>${esc(t.trait)}</b>: ${esc(t.why)}</div>`).join("")
    : `<p class="muted">No strong traits yet. Analyze more games to find them.</p>`;
  $("#tendencies").innerHTML = Object.entries(REPORT.tendencies).map(([k, v]) => `<div class="aspect">
      <div class="aspect-head"><span>${k}</span><span class="muted">${v.score}</span></div>
      <div class="bar"><i style="width:${v.score}%;background:var(--accent)"></i><span class="mark"></span></div>
      <div class="muted small">${esc(v.text)}</div></div>`).join("");
  const s = REPORT.sessions;
  if (!s.game_times) { $("#sessions").innerHTML = `<p class="muted">Need at least 4 games.</p>`; return; }
  const row = (k, v) => `<div class="kv"><span>${k}</span><span>${v ?? "-"}</span></div>`;
  $("#sessions").innerHTML =
    row("Score in games right after a win", s.score_after_win != null ? `${s.score_after_win} (${s.games_after_win} games)` : null) +
    row("Score in games right after a loss", s.score_after_loss != null ? `${s.score_after_loss} (${s.games_after_loss} games)` : null) +
    Object.entries(s.score_by_game_in_session).map(([k, v]) => row(`Score in game ${k} of a session`, v)).join("") +
    row("Average games per session", s.avg_session_games) +
    row("Kept playing after two losses in a row", s.kept_playing_after_two_losses) +
    row("Games ended by early surrender", Math.round(100 * s.early_surrender_rate) + "%");
}

function drawHours() {
  const s = REPORT && REPORT.sessions; if (!s || !s.game_times) return;
  const c = $("#hours"), ctx = c.getContext("2d"), W = c.width, H = c.height;
  const b = Array.from({ length: 24 }, () => ({ n: 0, w: 0, sc: [] }));
  s.game_times.forEach((g) => { const h = new Date(g.start * 1000).getHours(); b[h].n++; b[h].w += g.win; if (g.score != null) b[h].sc.push(g.score); });
  ctx.clearRect(0, 0, W, H);
  const max = Math.max(...b.map((x) => x.n)) || 1, bw = W / 24;
  b.forEach((x, h) => {
    const bh = ((H - 30) * x.n) / max, avg = x.sc.length ? x.sc.reduce((a, c) => a + c, 0) / x.sc.length : null;
    ctx.fillStyle = avg == null ? "#263040" : avg >= 55 ? "#4cc38a" : avg <= 45 ? "#e5656b" : "#d8b45a";
    ctx.fillRect(h * bw + 3, H - 20 - bh, bw - 6, bh);
    ctx.fillStyle = "#8b95a5"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    if (h % 3 === 0) ctx.fillText(`${h}:00`, h * bw + bw / 2, H - 5);
  });
  ctx.textAlign = "left"; ctx.fillText("Games per hour (your local time). Green bars: you score above typical. Red: below.", 6, 12);
}

// ------------------------------------------------------------------ matches
function renderMatches() {
  $("#matches").innerHTML = `<table><tr><th>Champion</th><th>Role</th><th>Result</th><th class="num">K / D / A</th><th class="num">CS</th>
    <th>Against</th><th class="num">Score</th><th class="num">Length</th><th>When</th></tr>` +
    REPORT.matches.map((m) => `<tr><td><div class="champ"><img src="${icon(m.champion)}" alt="">${esc(m.champion)}</div></td>
      <td>${ROLE[m.role] || "-"}</td><td class="${m.win ? "win" : "loss"}">${m.win ? "Win" : "Loss"}</td>
      <td class="num">${m.k} / ${m.d} / ${m.a}</td><td class="num">${m.cs}</td><td>${esc(m.opp || "-")}</td>
      <td class="num" style="color:${m.score != null ? pctColor(m.score) : ""}">${m.score ?? "-"}</td>
      <td class="num">${Math.floor(m.minutes)}m</td><td class="muted small">${new Date(m.start * 1000).toLocaleString()}</td></tr>`).join("") + "</table>";
}

init();
