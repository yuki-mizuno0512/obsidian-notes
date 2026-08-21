#!/usr/bin/env python3
"""Recorder Inbox のダッシュボードHTMLを生成する（自己完結・外部依存なし）."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
WDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


def _minutes(ms) -> float:
    return round((ms or 0) / 60000, 1)


def build_payload(state: dict, days: int, today: date, vault_name: str = "") -> dict:
    window_start = (today - timedelta(days=days)).isoformat()
    recordings = [
        {
            "date": r["date"],
            "time": r.get("time") or "",
            "title": r.get("title") or "",
            "kind": r.get("kind") or "memo",
            "source": r.get("source") or "",
            "minutes": _minutes(r.get("duration_ms")),
            "summary": r.get("summary") or "",
            "highlights": r.get("highlights") or [],
            "memories": r.get("memories") or [],
            "people": r.get("people") or [],
            "note": r.get("note") or "",
            "transcript": r.get("transcript_note") or "",
        }
        for r in state.get("recordings", {}).values()
        if (r.get("date") or "") >= window_start
    ]
    recordings.sort(key=lambda r: (r["date"], r["time"]), reverse=True)

    cutoff_done = (today - timedelta(days=30)).isoformat()
    todos = [
        {
            "id": t["id"],
            "text": t.get("text") or "",
            "priority": t.get("priority") or "",
            "due": t.get("due") or "",
            "owner": t.get("owner") or "self",
            "context": t.get("context") or "",
            "date": t.get("date") or "",
            "title": t.get("title") or "",
            "note": t.get("note") or "",
            "source": t.get("source") or "",
            "done": bool(t.get("done")),
            "done_at": t.get("done_at") or "",
        }
        for t in state.get("todos", {}).values()
        if not t.get("done") or (t.get("done_at") or "") >= cutoff_done
    ]

    daily = []
    by_day: dict[str, dict] = {}
    for rec in recordings:
        slot = by_day.setdefault(rec["date"], {"count": 0, "minutes": 0.0})
        slot["count"] += 1
        slot["minutes"] += rec["minutes"]
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        slot = by_day.get(key, {"count": 0, "minutes": 0.0})
        daily.append(
            {
                "date": key,
                "label": f"{day.month}/{day.day}",
                "wday": WDAY_JA[day.weekday()],
                "count": slot["count"],
                "minutes": round(slot["minutes"], 1),
            }
        )

    week_start = (today - timedelta(days=6)).isoformat()
    week_recs = [r for r in recordings if r["date"] >= week_start]
    return {
        "meta": {
            "vault": vault_name,
            "today": today.isoformat(),
            "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
            "days": days,
            "week_count": len(week_recs),
            "week_minutes": round(sum(r["minutes"] for r in week_recs)),
            "total_recordings": len(recordings),
        },
        "recordings": recordings,
        "todos": todos,
        "daily": daily,
    }


def render_dashboard(state: dict, days: int = 60, today: date | None = None, vault_name: str = "") -> str:
    today = today or datetime.now(JST).date()
    payload = build_payload(state, days, today, vault_name)
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return TEMPLATE.replace("/*__DATA__*/null", data)


TEMPLATE = r'''<title>声のインボックス</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Old+Mincho:wght@400;700&family=Zen+Kaku+Gothic+New:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root {
    --ground: #f3f4f8;
    --surface: #ffffff;
    --surface-2: #eceef5;
    --ink: #171a21;
    --ink-2: #4b515e;
    --muted: #757d8d;
    --line: #dfe2ea;
    --accent: #2c3e7a;
    --accent-soft: #e5e9f6;
    --accent-dim: #8b98c4;
    --overdue: #ad3529;
    --today: #9a6714;
    --moss: #46693f;
    --radius: 14px;
    --display: "Zen Old Mincho", "Hiragino Mincho ProN", serif;
    --body: "Zen Kaku Gothic New", "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
    --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #11131a;
      --surface: #191c24;
      --surface-2: #21252f;
      --ink: #e8eaef;
      --ink-2: #aab1bf;
      --muted: #7d8595;
      --line: #282d38;
      --accent: #93a6e6;
      --accent-soft: #232a3d;
      --accent-dim: #5b688f;
      --overdue: #e08376;
      --today: #d5a446;
      --moss: #8bb383;
    }
  }
  :root[data-theme="dark"] {
    --ground: #11131a;
    --surface: #191c24;
    --surface-2: #21252f;
    --ink: #e8eaef;
    --ink-2: #aab1bf;
    --muted: #7d8595;
    --line: #282d38;
    --accent: #93a6e6;
    --accent-soft: #232a3d;
    --accent-dim: #5b688f;
    --overdue: #e08376;
    --today: #d5a446;
    --moss: #8bb383;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: var(--body);
    font-size: 15px;
    line-height: 1.7;
    -webkit-text-size-adjust: 100%;
  }
  .wrap { max-width: 880px; margin: 0 auto; padding: 28px 18px 64px; display: flex; flex-direction: column; gap: 22px; }
  .masthead { display: flex; flex-direction: column; gap: 4px; }
  .eyebrow { margin: 0; font-family: var(--mono); font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
  h1 { margin: 0; font-family: var(--display); font-weight: 700; font-size: clamp(28px, 6vw, 40px); line-height: 1.2; letter-spacing: .02em; text-wrap: balance; }
  .sub { margin: 0; color: var(--ink-2); font-size: 13px; font-family: var(--mono); }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: 10px; }
  .tile { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 13px 16px; display: flex; flex-direction: column; gap: 1px; }
  .tile .row { display: flex; align-items: baseline; gap: 5px; }
  .tile .label { font-size: 11px; letter-spacing: .1em; color: var(--muted); font-family: var(--mono); text-transform: uppercase; }
  .tile .value { font-family: var(--mono); font-size: 26px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.25; }
  .tile .unit { font-size: 12px; color: var(--ink-2); font-family: var(--body); }
  .tile.alert .value { color: var(--overdue); }
  .chart-card { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px 8px; }
  .chart-card figcaption { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
  .chart-title { font-weight: 700; font-size: 14px; }
  .chart-note { font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .chart { width: 100%; overflow-x: auto; }
  .chart svg { display: block; width: 100%; height: 84px; }
  .chart .bar { fill: var(--accent-dim); }
  .chart .bar.is-today { fill: var(--accent); }
  .chart .bar:hover, .chart .bar:focus { fill: var(--accent); outline: none; }
  .chart .axis { stroke: var(--line); stroke-width: 1; }
  .chart .tick { fill: var(--muted); font-family: var(--mono); font-size: 9px; }
  .controls { display: flex; flex-direction: column; gap: 10px; position: sticky; top: 0; padding: 10px 0; background: linear-gradient(var(--ground) 70%, transparent); z-index: 5; }
  .tabs { display: flex; gap: 6px; background: var(--surface-2); border-radius: 999px; padding: 4px; align-self: flex-start; }
  .tabs button { border: 0; background: transparent; color: var(--ink-2); font-family: var(--body); font-size: 13px; font-weight: 500; padding: 7px 15px; border-radius: 999px; cursor: pointer; }
  .tabs button[aria-selected="true"] { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
  .tabs button:focus-visible, .search input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .search { display: block; }
  .search input { width: 100%; padding: 11px 14px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); font-family: var(--body); font-size: 14px; }
  .group { display: flex; flex-direction: column; gap: 8px; margin-bottom: 22px; }
  .group > h2 { margin: 0; font-family: var(--display); font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
  .group > h2 .n { font-family: var(--mono); font-size: 12px; color: var(--muted); font-weight: 400; }
  .card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 13px 15px; display: flex; flex-direction: column; gap: 6px; }
  .todo { border-left: 3px solid var(--accent-dim); }
  .todo.overdue { border-left-color: var(--overdue); }
  .todo.today { border-left-color: var(--today); }
  .todo.someday { border-left-color: var(--line); }
  .todo.done { opacity: .62; }
  .todo .text { font-size: 15px; line-height: 1.6; }
  .todo.done .text { text-decoration: line-through; text-decoration-color: var(--muted); }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); font-family: var(--mono); }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); color: var(--ink-2); font-family: var(--mono); font-size: 11px; letter-spacing: .02em; }
  .chip.state-overdue { background: color-mix(in oklab, var(--overdue) 16%, var(--surface)); color: var(--overdue); }
  .chip.state-today { background: color-mix(in oklab, var(--today) 18%, var(--surface)); color: var(--today); }
  .chip.state-done { background: color-mix(in oklab, var(--moss) 16%, var(--surface)); color: var(--moss); }
  .chip.pri-S { background: color-mix(in oklab, var(--overdue) 14%, var(--surface)); color: var(--overdue); }
  a { color: var(--accent); text-decoration-color: color-mix(in oklab, var(--accent) 40%, transparent); text-underline-offset: 2px; }
  a:hover { text-decoration-color: var(--accent); }
  .day { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
  .day > header { display: flex; align-items: baseline; gap: 10px; border-bottom: 1px solid var(--line); padding-bottom: 6px; }
  .day > header .d { font-family: var(--display); font-size: 19px; font-weight: 700; }
  .day > header .w { font-family: var(--mono); font-size: 12px; color: var(--muted); }
  .rec { display: grid; grid-template-columns: 58px 1fr; gap: 4px 12px; }
  .rec .when { font-family: var(--mono); font-size: 13px; color: var(--ink-2); font-variant-numeric: tabular-nums; padding-top: 2px; }
  .rec .body { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .rec .title { font-weight: 500; font-size: 15px; }
  .rec .summary { color: var(--ink-2); font-size: 14px; }
  .rec ul { margin: 0; padding-left: 1.1em; color: var(--ink-2); font-size: 14px; }
  blockquote.memory { margin: 0; padding: 10px 14px; border-left: 2px solid var(--accent-dim); background: var(--accent-soft); border-radius: 0 10px 10px 0; font-family: var(--display); font-size: 15px; line-height: 1.75; }
  blockquote.memory .src { display: block; margin-top: 6px; font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .empty { color: var(--muted); font-size: 14px; padding: 18px 0; }
  footer { border-top: 1px solid var(--line); padding-top: 14px; color: var(--muted); font-size: 12px; font-family: var(--mono); display: flex; flex-direction: column; gap: 4px; }
  .tip { position: fixed; pointer-events: none; z-index: 20; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 6px 9px; font-family: var(--mono); font-size: 11px; color: var(--ink); box-shadow: 0 4px 14px rgba(0,0,0,.18); }
  @media (prefers-reduced-motion: no-preference) {
    .tabs button, .card { transition: background-color .15s ease, color .15s ease, opacity .15s ease; }
  }
  @media (max-width: 480px) {
    .rec { grid-template-columns: 48px 1fr; }
    .wrap { padding: 20px 14px 56px; }
  }
</style>

<div class="wrap">
  <header class="masthead">
    <p class="eyebrow">PLAUD ・ SwitchBot MindClip</p>
    <h1>声のインボックス</h1>
    <p class="sub" id="metaLine"></p>
  </header>

  <section class="tiles" id="tiles"></section>

  <figure class="chart-card">
    <figcaption>
      <span class="chart-title">録音した時間</span>
      <span class="chart-note">直近30日・分</span>
    </figcaption>
    <div class="chart" id="chart"></div>
  </figure>

  <div class="controls">
    <div class="tabs" role="tablist" id="tabs">
      <button role="tab" data-panel="todo" aria-selected="true">やること</button>
      <button role="tab" data-panel="timeline" aria-selected="false">タイムライン</button>
      <button role="tab" data-panel="memories" aria-selected="false">おもいで</button>
    </div>
    <label class="search"><input id="q" type="search" placeholder="やること・要約・おもいでを検索（/ でフォーカス）" autocomplete="off"></label>
  </div>

  <main>
    <section id="panel-todo"></section>
    <section id="panel-timeline" hidden></section>
    <section id="panel-memories" hidden></section>
  </main>

  <footer>
    <span id="footMeta"></span>
    <span>チェックを入れるのは Obsidian の Recorder/TODO。このページは読むためのビュー。</span>
  </footer>
</div>
<div class="tip" id="tip" hidden></div>

<script>
const DATA = /*__DATA__*/null;
const KIND = {meeting:"会議", interview:"面接", diary:"日記", memo:"メモ", study:"勉強会", call:"通話", lecture:"講義", life:"生活"};
const SRC = {plaud:"PLAUD", switchbot:"SwitchBot"};
const WD = ["日","月","火","水","木","金","土"];
const TODAY = DATA.meta.today;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const noteHref = (p) => p ? "obsidian://open?vault=" + encodeURIComponent(DATA.meta.vault || "") + "&file=" + encodeURIComponent(p.replace(/\.md$/, "")) : "";
const noteLink = (p, label) => p ? '<a href="' + noteHref(p) + '">' + esc(label) + "</a>" : esc(label);
const fmtMin = (m) => m >= 60 ? Math.floor(m / 60) + "h" + String(Math.round(m % 60)).padStart(2, "0") : Math.round(m) + "m";

function todoState(t) {
  if (t.done) return "done";
  if (!t.due) return "someday";
  if (t.due < TODAY) return "overdue";
  if (t.due === TODAY) return "today";
  return "planned";
}
const STATE_LABEL = {overdue:"期限切れ", today:"今日", planned:"予定", someday:"未定", done:"完了"};

function matches(q, ...fields) {
  if (!q) return true;
  const hay = fields.flat().filter(Boolean).join(" ").toLowerCase();
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}

/* ---------- tiles + chart ---------- */
function renderHead() {
  const open = DATA.todos.filter((t) => !t.done);
  const overdue = open.filter((t) => t.due && t.due <= TODAY);
  const tiles = [
    {label:"未完了", value:open.length, unit:"件", alert:false},
    {label:"期限切れ・今日", value:overdue.length, unit:"件", alert:overdue.length > 0},
    {label:"今週の録音", value:DATA.meta.week_count, unit:"本"},
    {label:"今週の長さ", value:fmtMin(DATA.meta.week_minutes), unit:""},
  ];
  document.getElementById("tiles").innerHTML = tiles.map((t) =>
    '<div class="tile' + (t.alert ? " alert" : "") + '"><span class="label">' + esc(t.label) + '</span>' +
    '<span class="row"><span class="value">' + esc(t.value) + '</span>' + (t.unit ? '<span class="unit">' + esc(t.unit) + "</span>" : "") + "</span></div>"
  ).join("");
  document.getElementById("metaLine").textContent =
    DATA.meta.generated_at + " 時点 ・ 録音 " + DATA.meta.total_recordings + " 本（直近 " + DATA.meta.days + " 日）";
  document.getElementById("footMeta").textContent =
    "recorder-inbox で生成 ・ " + DATA.meta.generated_at;
}

function renderChart() {
  const days = DATA.daily, W = 720, H = 84, PAD = 16, BASE = H - 16;
  const max = Math.max(10, ...days.map((d) => d.minutes));
  const slot = (W - PAD * 2) / days.length;
  const bw = Math.max(3, slot - 2);
  let svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="直近30日の録音時間（分）" preserveAspectRatio="none">';
  svg += '<line class="axis" x1="' + PAD + '" y1="' + (BASE + 0.5) + '" x2="' + (W - PAD) + '" y2="' + (BASE + 0.5) + '"></line>';
  days.forEach((d, i) => {
    const h = d.minutes > 0 ? Math.max(3, (d.minutes / max) * (BASE - 12)) : 0;
    const x = PAD + i * slot + (slot - bw) / 2;
    if (h > 0) {
      svg += '<rect class="bar' + (d.date === TODAY ? " is-today" : "") + '" x="' + x.toFixed(1) + '" y="' + (BASE - h).toFixed(1) +
        '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="2" tabindex="0" data-d="' + d.date +
        '" data-t="' + d.label + "（" + d.wday + "） " + d.count + "本 " + fmtMin(d.minutes) + '"></rect>';
    }
    if (i % 7 === 0) {
      svg += '<text class="tick" x="' + (x + bw / 2).toFixed(1) + '" y="' + (H - 3) + '" text-anchor="middle">' + d.label + "</text>";
    }
  });
  svg += "</svg>";
  const host = document.getElementById("chart");
  host.innerHTML = svg;
  const tip = document.getElementById("tip");
  const show = (el, ev) => {
    tip.textContent = el.dataset.t;
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const x = (ev && ev.clientX) || r.left + r.width / 2;
    tip.style.left = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, x - tip.offsetWidth / 2)) + "px";
    tip.style.top = Math.max(8, r.top - tip.offsetHeight - 8) + "px";
  };
  host.querySelectorAll(".bar").forEach((bar) => {
    bar.addEventListener("pointerenter", (e) => show(bar, e));
    bar.addEventListener("focus", () => show(bar, null));
    bar.addEventListener("pointerleave", () => { tip.hidden = true; });
    bar.addEventListener("blur", () => { tip.hidden = true; });
  });
}

/* ---------- panels ---------- */
function renderTodos(q) {
  const order = {overdue:0, today:1, planned:2, someday:3, done:4};
  const pri = {S:0, A:1, B:2, C:3, "":4};
  const items = DATA.todos.filter((t) => matches(q, t.text, t.title, t.context)).map((t) => ({...t, st: todoState(t)}));
  items.sort((a, b) => order[a.st] - order[b.st] || (a.due || "9999").localeCompare(b.due || "9999") || pri[a.priority] - pri[b.priority]);
  const groups = [["overdue","期限切れ・今日"],["today","期限切れ・今日"],["planned","予定あり"],["someday","期日なし"],["done","完了（直近30日）"]];
  const seen = new Set();
  let html = "";
  for (const [key, label] of groups) {
    if (seen.has(label)) continue;
    seen.add(label);
    const list = items.filter((t) => (key === "overdue" || key === "today" ? (t.st === "overdue" || t.st === "today") : t.st === key));
    if (!list.length) continue;
    html += '<div class="group"><h2>' + esc(label) + '<span class="n">' + list.length + "</span></h2>";
    html += list.map((t) => {
      const chips = ['<span class="chip state-' + t.st + '">' + STATE_LABEL[t.st] + "</span>"];
      if (t.due) chips.push('<span class="chip">期日 ' + esc(t.due) + "</span>");
      if (t.priority) chips.push('<span class="chip pri-' + esc(t.priority) + '">' + esc(t.priority) + "</span>");
      if (t.owner && !["self","私","me"].includes(t.owner)) chips.push('<span class="chip">@' + esc(t.owner) + "</span>");
      if (t.done_at) chips.push('<span class="chip state-done">完了 ' + esc(t.done_at) + "</span>");
      return '<article class="card todo ' + t.st + '"><div class="text">' + esc(t.text) + "</div>" +
        (t.context ? '<div class="summary" style="color:var(--ink-2);font-size:13px">' + esc(t.context) + "</div>" : "") +
        '<div class="meta">' + chips.join("") + "<span>" + esc(t.date) + " " + noteLink(t.note, t.title || "元ノート") + "</span></div></article>";
    }).join("");
    html += "</div>";
  }
  return html || '<p class="empty">' + (q ? "一致するやることはありません。" : "やることは空です。いいことです。") + "</p>";
}

function renderTimeline(q) {
  const recs = DATA.recordings.filter((r) => matches(q, r.title, r.summary, r.highlights, r.memories, r.people));
  if (!recs.length) return '<p class="empty">' + (q ? "一致する録音はありません。" : "まだ録音が取り込まれていません。") + "</p>";
  const byDay = new Map();
  recs.forEach((r) => { if (!byDay.has(r.date)) byDay.set(r.date, []); byDay.get(r.date).push(r); });
  let html = "";
  for (const [day, list] of byDay) {
    const d = new Date(day + "T00:00:00+09:00");
    const mins = list.reduce((a, r) => a + r.minutes, 0);
    html += '<section class="day"><header><span class="d">' + esc(day) + '</span><span class="w">' + WD[d.getDay()] +
      " ・ " + list.length + "本 ・ " + fmtMin(mins) + '</span></header>';
    html += list.map((r) => {
      const bits = [];
      if (r.summary) bits.push('<div class="summary">' + esc(r.summary) + "</div>");
      if (r.highlights.length) bits.push("<ul>" + r.highlights.map((h) => "<li>" + esc(h) + "</li>").join("") + "</ul>");
      if (r.memories.length) bits.push(r.memories.map((m) => '<blockquote class="memory">' + esc(m) + "</blockquote>").join(""));
      return '<article class="card rec"><div class="when">' + esc(r.time) + '</div><div class="body">' +
        '<div class="title">' + noteLink(r.note, r.title) + "</div>" +
        '<div class="meta"><span class="chip">' + esc(KIND[r.kind] || r.kind) + '</span><span class="chip">' +
        esc(SRC[r.source] || r.source) + '</span><span>' + fmtMin(r.minutes) + "</span>" +
        (r.people.length ? "<span>" + esc(r.people.join("／")) + "</span>" : "") +
        (r.transcript ? "<span>" + noteLink(r.transcript, "文字起こし") + "</span>" : "") + "</div>" +
        bits.join("") + "</div></article>";
    }).join("");
    html += "</section>";
  }
  return html;
}

function renderMemories(q) {
  const rows = [];
  DATA.recordings.forEach((r) => (r.memories || []).forEach((m) => rows.push({m, r})));
  const hits = rows.filter(({m, r}) => matches(q, m, r.title));
  if (!hits.length) return '<p class="empty">' + (q ? "一致するおもいではありません。" : "おもいではまだありません。日記の録音を取り込むとここに並びます。") + "</p>";
  let html = "", month = "";
  for (const {m, r} of hits) {
    const ym = r.date.slice(0, 7);
    if (ym !== month) {
      if (month) html += "</div>";
      month = ym;
      html += '<div class="group"><h2>' + esc(Number(ym.slice(0, 4)) + "年" + Number(ym.slice(5, 7)) + "月") + "</h2>";
    }
    html += '<blockquote class="memory">' + esc(m) + '<span class="src">' + esc(r.date + " " + r.time) + " ・ " + noteLink(r.note, r.title) + "</span></blockquote>";
  }
  return html + (month ? "</div>" : "");
}

/* ---------- wiring ---------- */
let active = "todo";
function paint() {
  const q = document.getElementById("q").value.trim();
  document.getElementById("panel-todo").innerHTML = active === "todo" ? renderTodos(q) : "";
  document.getElementById("panel-timeline").innerHTML = active === "timeline" ? renderTimeline(q) : "";
  document.getElementById("panel-memories").innerHTML = active === "memories" ? renderMemories(q) : "";
  ["todo","timeline","memories"].forEach((name) => {
    document.getElementById("panel-" + name).hidden = name !== active;
  });
}
document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-panel]");
  if (!btn) return;
  active = btn.dataset.panel;
  document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
  paint();
});
document.getElementById("q").addEventListener("input", paint);
document.addEventListener("keydown", (e) => {
  const field = document.getElementById("q");
  if (e.key === "/" && document.activeElement !== field) { e.preventDefault(); field.focus(); }
  if (e.key === "Escape" && document.activeElement === field) { field.value = ""; paint(); field.blur(); }
});
renderHead();
renderChart();
paint();
window.addEventListener("resize", renderChart);
</script>
'''
