#!/usr/bin/env python3
"""Recorder Inbox — PLAUD / SwitchBot の録音を Obsidian ノートに取り込むツール.

標準ライブラリのみで動く。判断が必要な処理（要約・TODO抽出・おもいで抽出）は
Claude 側で行い、このスクリプトは「正規化JSON → ファイル配置」を決定論的に担う。

    recorder_inbox.py build [--input FILE|-] [--vault DIR] [--dry-run]
    recorder_inbox.py switchbot [--dir Recorder/Inbox] [--move-processed]
    recorder_inbox.py todos [--json] [--all]
    recorder_inbox.py dashboard [--out PATH]

正規化JSONの形は schema.md を参照。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
BEGIN = "<!-- recorder:begin -->"
END = "<!-- recorder:end -->"
STATE_VERSION = 1
WDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]
PRIORITY_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "": 4, None: 4}
# このリポジトリには 255 バイトを超えるファイル名が既にあり、Linux 上で
# チェックアウトできない（File name too long）。生成側では必ず抑える。
MAX_SLUG_BYTES = 60
MAX_BASENAME_BYTES = 120


# ---------------------------------------------------------------- utilities
def find_vault(explicit: str | None) -> Path:
    """vault ルートを決める。Recorder/ か .git を目印に上へ辿る。"""
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("RECORDER_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path.cwd().resolve()
    for cand in [here, *here.parents]:
        if (cand / "Recorder").is_dir() or (cand / ".git").exists():
            return cand
    return here


def parse_dt(value: str, assume: str = "utc") -> datetime:
    """ISO8601 を datetime に。tz 無しの場合は assume（utc|jst）で補う。"""
    if not value:
        raise ValueError("empty datetime")
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc if assume == "utc" else JST)
    return dt


def to_jst(dt: datetime) -> datetime:
    return dt.astimezone(JST)


def truncate_bytes(text: str, limit: int) -> str:
    out = text
    while len(out.encode("utf-8")) > limit and out:
        out = out[:-1]
    return out


def slugify(title: str, limit: int = MAX_SLUG_BYTES) -> str:
    """日本語はそのまま残しつつ、ファイル名に使える形へ。長さはバイトで制限。"""
    text = unicodedata.normalize("NFC", title or "").strip()
    text = re.sub(r"[\s　]+", "-", text)
    text = re.sub(r'[\\/:*?"<>|#^\[\]{}%$!&;`\'\(\)（）【】「」『』、。,]+', "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    text = truncate_bytes(text, limit).strip("-._")
    return text or "untitled"


def todo_id(source_id: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip())
    key = source_id + "\n" + norm
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def fmt_duration(ms: int | None) -> str:
    if not ms:
        return ""
    total = int(round(ms / 1000))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_clock(ms: int | None) -> str:
    """再生位置の表示。切り上げると実際の発言位置より後ろになるため切り捨てる。"""
    if ms is None:
        return ""
    total = int(ms // 1000)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def ja_date(d: date) -> str:
    return f"{d.isoformat()} ({WDAY_JA[d.weekday()]})"


def yaml_escape(value: str) -> str:
    text = str(value)
    if text == "" or re.search(r'[:#\[\]{}&*!|>\'"%@`,]', text) or text != text.strip():
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def dump_frontmatter(data: dict) -> str:
    lines = ["---"]
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(yaml_escape(v) for v in value)}]")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {yaml_escape(value)}")
    lines.append("---")
    return "\n".join(lines)


def load_frontmatter(text: str) -> tuple[dict, str]:
    """フラットな frontmatter を素朴に読む（ユーザー追記キーの保全用）。"""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[4:end]
    rest = text[end + 4 :].lstrip("\n")
    data: dict = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            data[key.strip()] = [v for v in items if v]
        else:
            data[key.strip()] = value.strip('"').strip("'")
    return data, rest


# ---------------------------------------------------------------- paths / state
class Layout:
    def __init__(self, vault: Path):
        self.vault = vault
        self.root = vault / "Recorder"
        self.recordings = self.root / "Recordings"
        self.transcripts = self.root / "Transcripts"
        self.diary = self.root / "Diary"
        self.inbox = self.root / "Inbox"
        self.todo_file = self.root / "TODO.md"
        self.state_file = self.root / ".recorder-state.json"

    def rel(self, path: Path) -> str:
        return path.relative_to(self.vault).as_posix()


def load_state(layout: Layout) -> dict:
    if layout.state_file.exists():
        try:
            state = json.loads(layout.state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"状態ファイルが壊れています: {layout.state_file} ({exc})")
    else:
        state = {}
    state.setdefault("version", STATE_VERSION)
    state.setdefault("todos", {})
    state.setdefault("recordings", {})
    return state


def save_state(layout: Layout, state: dict) -> None:
    layout.state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    layout.state_file.write_text(payload, encoding="utf-8")


# ---------------------------------------------------------------- normalize
def as_list(value) -> list:
    if value in (None, "", []):
        return []
    return value if isinstance(value, list) else [value]


def normalize_recording(raw: dict) -> dict:
    source = str(raw.get("source") or "plaud").lower()
    assume = str(raw.get("tz") or ("utc" if source == "plaud" else "jst")).lower()
    stamp = raw.get("recorded_at") or raw.get("start_at") or raw.get("created_at")
    if not stamp:
        raise ValueError(f"recorded_at がありません: {raw.get('title') or raw.get('name')}")
    started = to_jst(parse_dt(str(stamp), assume=assume))

    title = str(raw.get("title") or raw.get("name") or "").strip()
    title = re.sub(r"^\d{2}-\d{2}\s+", "", title)  # PLAUD が付ける "08-19 " を除去
    title = re.sub(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$", "", title).strip()
    if not title:
        title = started.strftime("%H:%M の録音")

    source_id = str(raw.get("source_id") or raw.get("id") or "").strip()
    if not source_id:
        seed = f"{source}|{started.isoformat()}|{title}"
        source_id = "local-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    duration_ms = raw.get("duration_ms")
    if duration_ms is None:
        duration_ms = raw.get("duration") or 0
    duration_ms = int(duration_ms or 0)

    todos = []
    for item in as_list(raw.get("todos")):
        if isinstance(item, str):
            item = {"text": item}
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        todos.append(
            {
                "id": todo_id(source_id, text),
                "text": text,
                "priority": (str(item.get("priority") or "").strip().upper() or ""),
                "due": (str(item.get("due") or "").strip() or ""),
                "owner": (str(item.get("owner") or "self").strip() or "self"),
                "context": str(item.get("context") or "").strip(),
            }
        )

    quotes = []
    for item in as_list(raw.get("quotes")):
        if isinstance(item, str):
            item = {"text": item}
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        at = item.get("at_ms")
        if at is None:
            at = item.get("start_time")
        quotes.append(
            {
                "speaker": str(item.get("speaker") or "").strip(),
                "text": text,
                "at_ms": int(at) if isinstance(at, (int, float)) else None,
            }
        )

    segments = []
    for seg in as_list(raw.get("transcript")):
        content = str(seg.get("content") or seg.get("text") or "").strip()
        if not content:
            continue
        segments.append(
            {
                "speaker": str(seg.get("speaker") or "").strip(),
                "content": content,
                "start_time": seg.get("start_time"),
                "end_time": seg.get("end_time"),
            }
        )

    kind = str(raw.get("kind") or "memo").strip().lower()
    basename = truncate_bytes(
        f"{started:%Y-%m-%d-%H%M}-{slugify(title)}", MAX_BASENAME_BYTES
    ).rstrip("-._")

    return {
        "key": f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "title": title,
        "kind": kind,
        "recorded_at": started.isoformat(),
        "date": started.date().isoformat(),
        "time": started.strftime("%H:%M"),
        "duration_ms": duration_ms,
        "people": [str(p).strip() for p in as_list(raw.get("people")) if str(p).strip()],
        "topics": [str(t).strip() for t in as_list(raw.get("topics")) if str(t).strip()],
        "summary": str(raw.get("summary") or "").strip(),
        "highlights": [str(h).strip() for h in as_list(raw.get("highlights")) if str(h).strip()],
        "memories": [str(m).strip() for m in as_list(raw.get("memories")) if str(m).strip()],
        "todos": todos,
        "quotes": quotes,
        "transcript": segments,
        "basename": basename,
        "note": f"Recorder/Recordings/{started:%Y}/{basename}.md",
        "transcript_note": (
            f"Recorder/Transcripts/{started:%Y}/{basename}.md" if segments else ""
        ),
        "tags": ["recorder", f"recorder/{source}", f"recorder/{kind}"],
    }


# ---------------------------------------------------------------- managed write
def write_managed(path: Path, frontmatter: dict, heading: str, block: str, dry_run: bool) -> str:
    """frontmatter + 見出し + 管理ブロックを更新し、END 以降のユーザー追記は保全する。"""
    tail = ""
    action = "created"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        action = "updated"
        old_fm, body = load_frontmatter(existing)
        merged = dict(old_fm)
        merged.update(frontmatter)  # 生成キーを優先し、ユーザー追記キーは残す
        frontmatter = merged
        end_at = body.find(END)
        if end_at != -1:
            tail = body[end_at + len(END) :]
        elif BEGIN not in body:
            # ユーザーが管理ブロックを消した場合も追記内容は失わない
            tail = "\n" + body.strip() + "\n" if body.strip() else ""
    if not tail.strip():
        tail = "\n\n## メモ\n\n<!-- ここから下は自由記述。再取り込みでも消えません。 -->\n"
    content = (
        dump_frontmatter(frontmatter)
        + "\n\n"
        + heading
        + "\n\n"
        + BEGIN
        + "\n"
        + block.strip()
        + "\n"
        + END
        + tail.rstrip()
        + "\n"
    )
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return "unchanged"
        path.write_text(content, encoding="utf-8")
    return action


def short_label(text: str, limit: int = 24) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def wiki_link(note_rel: str, label: str = "") -> str:
    target = note_rel[:-3] if note_rel.endswith(".md") else note_rel
    safe_label = (label or "").replace("|", "／").replace("]]", "]")
    if not safe_label or safe_label == target:
        return f"[[{target}]]"
    return f"[[{target}|{safe_label}]]"


# ---------------------------------------------------------------- renderers
KIND_LABEL = {
    "meeting": "🗣 会議",
    "interview": "🎯 面接",
    "diary": "📔 日記",
    "memo": "🧠 メモ",
    "study": "📚 勉強会",
    "call": "📞 通話",
    "lecture": "🎓 講義",
    "life": "🌿 生活",
}


def todo_line(todo: dict, checked: bool = False, link: str = "", done_at: str = "") -> str:
    box = "[x]" if checked else "[ ]"
    parts = [f"- {box} {todo['text']}"]
    if todo.get("priority"):
        mark = "🔴S" if todo["priority"] == "S" else todo["priority"]
        parts.append(f"〔{mark}〕")
    if todo.get("due"):
        parts.append(f"📅 {todo['due']}")
    if todo.get("owner") and todo["owner"] not in ("self", "私", "me"):
        parts.append(f"@{todo['owner']}")
    if done_at:
        parts.append(f"✅ {done_at}")
    if link:
        parts.append(f"← {link}")
    parts.append(f"<!-- todo:{todo['id']} -->")
    return " ".join(parts)


def render_recording_block(rec: dict) -> str:
    lines: list[str] = []
    head = [KIND_LABEL.get(rec["kind"], rec["kind"])]
    if rec["duration_ms"]:
        head.append(fmt_duration(rec["duration_ms"]))
    head.append({"plaud": "PLAUD", "switchbot": "SwitchBot"}.get(rec["source"], rec["source"]))
    if rec["people"]:
        head.append("／".join(rec["people"]))
    lines.append(" ・ ".join(p for p in head if p))

    if rec["summary"]:
        lines += ["", "## 要約", "", rec["summary"].strip()]
    if rec["topics"]:
        lines += ["", "## 話したこと", ""] + [f"- {t}" for t in rec["topics"]]
    if rec["todos"]:
        lines += ["", f"## やること ({len(rec['todos'])})", ""]
        for todo in rec["todos"]:
            bullet = [f"- {todo['text']}"]
            if todo.get("priority"):
                bullet.append(f"〔{todo['priority']}〕")
            if todo.get("due"):
                bullet.append(f"📅 {todo['due']}")
            if todo.get("owner") not in ("self", "私", "me"):
                bullet.append(f"@{todo['owner']}")
            if todo.get("context"):
                bullet.append(f"— {todo['context']}")
            lines.append(" ".join(bullet))
        lines += ["", f"チェックは {wiki_link('Recorder/TODO.md', 'やることリスト')} で行う（ここは参照用）。"]
    if rec["highlights"]:
        lines += ["", "## ハイライト", ""] + [f"- {h}" for h in rec["highlights"]]
    if rec["memories"]:
        lines += ["", "## おもいで", ""] + [f"- {m}" for m in rec["memories"]]
    if rec["quotes"]:
        lines += ["", "## 気になった発言", ""]
        for quote in rec["quotes"]:
            who = quote["speaker"] or "?"
            at = f"（{fmt_clock(quote['at_ms'])}）" if quote["at_ms"] is not None else ""
            lines += [f"> **{who}**{at} {quote['text']}", ""]
        lines = lines[:-1]

    lines += ["", "## 元データ", ""]
    lines.append(f"- ソース: {rec['source']} / `{rec['source_id']}`")
    lines.append(f"- 録音開始: {rec['recorded_at']}")
    if rec["transcript_note"]:
        lines.append(f"- 文字起こし: {wiki_link(rec['transcript_note'], '全文')}")
    if rec["source"] == "plaud":
        lines.append("- 音声: PLAUDクラウド（署名URLは24時間で失効するため保存しない）")
    lines.append(f"- 日記: {wiki_link('Recorder/Diary/' + rec['date'] + '.md', rec['date'])}")
    return "\n".join(lines)


def render_transcript_block(rec: dict) -> str:
    lines = [f"{wiki_link(rec['note'], 'ノートに戻る')}", ""]
    current = None
    for seg in rec["transcript"]:
        speaker = seg["speaker"] or "?"
        stamp = fmt_clock(seg["start_time"]) if isinstance(seg["start_time"], (int, float)) else ""
        if speaker != current:
            lines.append("")
            lines.append(f"**{speaker}**" + (f" `{stamp}`" if stamp else ""))
            current = speaker
        lines.append(f"{seg['content']}")
    return "\n".join(lines).strip()


def render_diary_block(day: str, recs: list[dict], todos: list[dict]) -> str:
    lines: list[str] = []
    total_ms = sum(r.get("duration_ms") or 0 for r in recs)
    lines.append(f"録音 {len(recs)} 本 ・ 合計 {fmt_duration(total_ms) or '0m'}")
    lines += ["", "## 今日の記録", "", "| 時刻 | 長さ | 種別 | タイトル |", "| --- | --- | --- | --- |"]
    for rec in recs:
        lines.append(
            f"| {rec['time']} | {fmt_duration(rec.get('duration_ms')) or '-'} | "
            f"{KIND_LABEL.get(rec.get('kind'), rec.get('kind', ''))} | "
            f"{wiki_link(rec['note'], rec['title'])} |"
        )
    memories = [(m, rec) for rec in recs for m in rec.get("memories") or []]
    if memories:
        lines += ["", "## おもいで", ""]
        lines += [f"- {m} — {wiki_link(rec['note'], rec['time'])}" for m, rec in memories]
    highlights = [(h, rec) for rec in recs for h in rec.get("highlights") or []]
    if highlights:
        lines += ["", "## ハイライト", ""]
        lines += [f"- {h} — {wiki_link(rec['note'], rec['title'])}" for h, rec in highlights]
    if todos:
        lines += ["", f"## この日に出たやること ({len(todos)})", ""]
        for todo in todos:
            state_mark = "✅" if todo.get("done") else "☐"
            bullet = [f"- {state_mark} {todo['text']}"]
            if todo.get("due"):
                bullet.append(f"📅 {todo['due']}")
            lines.append(" ".join(bullet))
        lines += ["", f"→ {wiki_link('Recorder/TODO.md', 'やることリスト')} で管理"]
    return "\n".join(lines)


def sort_key_todo(todo: dict) -> tuple:
    due = todo.get("due") or "9999-12-31"
    return (due, PRIORITY_ORDER.get(todo.get("priority") or "", 4), todo.get("date") or "")


def render_todo_block(state: dict, today: date) -> str:
    todos = list(state["todos"].values())
    open_todos = sorted([t for t in todos if not t.get("done")], key=sort_key_todo)
    done_todos = sorted(
        [t for t in todos if t.get("done") and (t.get("done_at") or "") >= (today - timedelta(days=30)).isoformat()],
        key=lambda t: t.get("done_at") or "",
        reverse=True,
    )
    today_str = today.isoformat()
    overdue = [t for t in open_todos if t.get("due") and t["due"] <= today_str]
    upcoming = [t for t in open_todos if t.get("due") and t["due"] > today_str]
    undated = [t for t in open_todos if not t.get("due")]

    lines = [f"未完了 **{len(open_todos)}** 件 ・ 更新 {datetime.now(JST):%Y-%m-%d %H:%M}"]

    def section(title: str, items: list[dict]) -> None:
        if not items:
            return
        lines.extend(["", f"### {title} ({len(items)})", ""])
        for todo in items:
            link = wiki_link(todo["note"], short_label(todo.get("title") or todo.get("date") or "元ノート")) if todo.get("note") else ""
            lines.append(todo_line(todo, checked=False, link=link))

    lines += ["", "## 未完了"]
    section("🔴 期限切れ・今日", overdue)
    section("📅 期日あり", upcoming)
    section("🗓 期日なし", sorted(undated, key=lambda t: (PRIORITY_ORDER.get(t.get("priority") or "", 4), t.get("date") or ""), reverse=False))
    if not open_todos:
        lines += ["", "未完了のやることはありません。", ""]
    if done_todos:
        lines += ["", f"## 完了（直近30日 / {len(done_todos)}件）", ""]
        for todo in done_todos:
            link = wiki_link(todo["note"], short_label(todo.get("title") or todo.get("date") or "元ノート")) if todo.get("note") else ""
            lines.append(todo_line(todo, checked=True, link=link, done_at=todo.get("done_at") or ""))
    return "\n".join(lines)


# ---------------------------------------------------------------- todo state sync
TODO_ID_RE = re.compile(r"<!--\s*todo:([0-9a-f]{8})\s*-->")
CHECKED_RE = re.compile(r"^\s*-\s*\[([ xX])\]")


def read_checkbox_states(path: Path) -> dict[str, bool]:
    """TODO.md の現在のチェック状態を id -> bool で読む。"""
    if not path.exists():
        return {}
    states: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        found = TODO_ID_RE.search(line)
        box = CHECKED_RE.match(line)
        if found and box:
            states[found.group(1)] = box.group(1).lower() == "x"
    return states


def sync_todo_checks(layout: Layout, state: dict, today: date) -> tuple[int, int]:
    """ユーザーが付けた/外したチェックを状態ファイルへ取り込む。"""
    states = read_checkbox_states(layout.todo_file)
    newly_done = reopened = 0
    for todo_key, checked in states.items():
        todo = state["todos"].get(todo_key)
        if todo is None:
            continue
        if checked and not todo.get("done"):
            todo["done"] = True
            todo["done_at"] = today.isoformat()
            newly_done += 1
        elif not checked and todo.get("done"):
            todo["done"] = False
            todo["done_at"] = None
            reopened += 1
    return newly_done, reopened


def merge_todos(state: dict, rec: dict, today: date) -> int:
    added = 0
    for todo in rec["todos"]:
        existing = state["todos"].get(todo["id"])
        payload = {
            "id": todo["id"],
            "text": todo["text"],
            "priority": todo["priority"],
            "due": todo["due"],
            "owner": todo["owner"],
            "context": todo["context"],
            "source": rec["source"],
            "source_id": rec["source_id"],
            "note": rec["note"],
            "title": rec["title"],
            "date": rec["date"],
        }
        if existing:
            existing.update(payload)  # done / done_at は保持する
        else:
            payload.update({"done": False, "done_at": None, "created_at": today.isoformat()})
            state["todos"][todo["id"]] = payload
            added += 1
    return added


def state_recording(rec: dict) -> dict:
    keys = (
        "source source_id title kind recorded_at date time duration_ms people topics "
        "summary highlights memories quotes note transcript_note"
    ).split()
    entry = {k: rec[k] for k in keys}
    entry["todo_ids"] = [t["id"] for t in rec["todos"]]
    return entry


# ---------------------------------------------------------------- build
def read_input(source: str | None) -> dict:
    if source in (None, "-"):
        text = sys.stdin.read()
    else:
        text = Path(source).expanduser().read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit("入力が空です（正規化JSONを渡してください）")
    data = json.loads(text)
    if isinstance(data, list):
        return {"recordings": data}
    if isinstance(data, dict) and "recordings" not in data:
        return {"recordings": [data]}
    return data


def cmd_build(args: argparse.Namespace) -> int:
    layout = Layout(find_vault(args.vault))
    state = load_state(layout)
    today = date.fromisoformat(args.today) if args.today else datetime.now(JST).date()

    payload = read_input(args.input)
    recs = [normalize_recording(r) for r in payload.get("recordings", [])]
    if not recs:
        raise SystemExit("recordings が空です")

    newly_done, reopened = sync_todo_checks(layout, state, today)

    report: list[str] = []
    added_todos = 0
    touched_dates: set[str] = set()
    for rec in recs:
        note_path = layout.vault / rec["note"]
        frontmatter = {
            "recorder": rec["source"],
            "source_id": rec["source_id"],
            "title": rec["title"],
            "kind": rec["kind"],
            "recorded_at": rec["recorded_at"],
            "date": rec["date"],
            "duration": fmt_duration(rec["duration_ms"]),
            "people": rec["people"],
            "tags": rec["tags"],
        }
        heading = f"# {rec['date']} {rec['time']} {rec['title']}"
        action = write_managed(note_path, frontmatter, heading, render_recording_block(rec), args.dry_run)
        report.append(f"  {action:9} {rec['note']}")
        if rec["transcript"]:
            tpath = layout.vault / rec["transcript_note"]
            taction = write_managed(
                tpath,
                {
                    "recorder": rec["source"],
                    "source_id": rec["source_id"],
                    "type": "transcript",
                    "date": rec["date"],
                    "tags": ["recorder", "recorder/transcript"],
                },
                f"# 文字起こし: {rec['title']}",
                render_transcript_block(rec),
                args.dry_run,
            )
            report.append(f"  {taction:9} {rec['transcript_note']}")
        added_todos += merge_todos(state, rec, today)
        state["recordings"][rec["key"]] = state_recording(rec)
        touched_dates.add(rec["date"])

    for day in sorted(touched_dates):
        day_recs = sorted(
            [r for r in state["recordings"].values() if r["date"] == day], key=lambda r: r["recorded_at"]
        )
        day_todos = sorted(
            [t for t in state["todos"].values() if t.get("date") == day], key=sort_key_todo
        )
        dpath = layout.diary / f"{day}.md"
        action = write_managed(
            dpath,
            {"date": day, "type": "diary", "tags": ["recorder", "recorder/diary"]},
            f"# {ja_date(date.fromisoformat(day))}",
            render_diary_block(day, day_recs, day_todos),
            args.dry_run,
        )
        report.append(f"  {action:9} {layout.rel(dpath)}")

    action = write_managed(
        layout.todo_file,
        {"type": "recorder-todo", "updated": datetime.now(JST).isoformat(timespec="minutes")},
        "# 🎙 やること（録音から）\n\nチェックを入れて保存すると、次の取り込みで「完了」へ移動します。",
        render_todo_block(state, today),
        args.dry_run,
    )
    report.append(f"  {action:9} {layout.rel(layout.todo_file)}")

    if not args.dry_run:
        save_state(layout, state)

    open_count = sum(1 for t in state["todos"].values() if not t.get("done"))
    print(f"{'[dry-run] ' if args.dry_run else ''}取り込み {len(recs)} 本")
    print("\n".join(report))
    print(f"  やること: +{added_todos} / 完了 +{newly_done} / 再オープン {reopened} / 未完了 {open_count}")
    return 0


# ---------------------------------------------------------------- switchbot import
SB_EXTS = {".txt", ".md", ".srt", ".vtt", ".json"}
DATE_IN_NAME = re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})")
TIME_IN_NAME = re.compile(r"(?<!\d)([0-2]\d)[-_:]?([0-5]\d)(?!\d)")
SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
LINE_TS = re.compile(
    r"^\s*[\[(（]?(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)[\])）]?\s*"
    r"(?:(?P<speaker>[^:：]{1,24})\s*[:：])?\s*(?P<text>.+)$"
)
LINE_SPEAKER = re.compile(r"^\s*(?P<speaker>[^:：]{1,24})\s*[:：]\s*(?P<text>.+)$")


def hms_to_ms(text: str) -> int | None:
    parts = [int(p) for p in text.split(":")]
    if len(parts) == 2:
        return (parts[0] * 60 + parts[1]) * 1000
    if len(parts) == 3:
        return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
    return None


def parse_srt(text: str) -> list[dict]:
    segments: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        start = end = None
        body: list[str] = []
        for line in lines:
            stamps = SRT_TIME.findall(line)
            if len(stamps) >= 2 and "-->" in line:
                start, end = (
                    (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms) for h, m, s, ms in stamps[:2]
                )
                continue
            if re.fullmatch(r"\d+", line.strip()) and not body:
                continue
            if line.strip().upper().startswith("WEBVTT"):
                continue
            body.append(line.strip())
        if not body:
            continue
        joined = " ".join(body)
        speaker = ""
        found = LINE_SPEAKER.match(joined)
        if found:
            speaker, joined = found.group("speaker").strip(), found.group("text").strip()
        segments.append({"speaker": speaker, "content": joined, "start_time": start, "end_time": end})
    return segments


def parse_plain(text: str) -> list[dict]:
    segments: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or set(line) <= {"-", "="}:
            continue
        found = LINE_TS.match(line)
        if found:
            segments.append(
                {
                    "speaker": (found.group("speaker") or "").strip(),
                    "content": found.group("text").strip(),
                    "start_time": hms_to_ms(found.group("ts")),
                    "end_time": None,
                }
            )
            continue
        found = LINE_SPEAKER.match(line)
        if found and not found.group("text").startswith("//"):
            segments.append(
                {
                    "speaker": found.group("speaker").strip(),
                    "content": found.group("text").strip(),
                    "start_time": None,
                    "end_time": None,
                }
            )
            continue
        if segments and not segments[-1]["speaker"] and segments[-1]["start_time"] is None:
            segments[-1]["content"] += " " + line
        else:
            segments.append({"speaker": "", "content": line, "start_time": None, "end_time": None})
    return segments


def switchbot_file_to_recording(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    stem = path.stem
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        data.setdefault("source", "switchbot")
        return data

    date_found = DATE_IN_NAME.search(stem)
    if date_found:
        y, m, d = date_found.groups()
        rest = stem[date_found.end() :]
        time_found = TIME_IN_NAME.search(rest)
        hh, mm = time_found.groups() if time_found else ("09", "00")
        recorded = f"{y}-{m}-{d}T{hh}:{mm}:00"
        title_src = (stem[: date_found.start()] + " " + (rest[time_found.end():] if time_found else rest)).strip()
    else:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, JST)
        recorded = mtime.replace(microsecond=0).isoformat()
        title_src = stem
    title = re.sub(r"[-_]+", " ", title_src).strip()
    if not title:
        first = next((l.strip().lstrip("# ").strip() for l in text.splitlines() if l.strip()), "")
        title = truncate_bytes(first, 90)

    segments = parse_srt(text) if path.suffix.lower() in {".srt", ".vtt"} else parse_plain(text)
    duration = 0
    for seg in segments:
        for key in ("end_time", "start_time"):
            if isinstance(seg.get(key), (int, float)):
                duration = max(duration, int(seg[key]))
    return {
        "source": "switchbot",
        "tz": "jst",
        "source_id": "sb-" + hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:12],
        "title": title,
        "recorded_at": recorded,
        "duration_ms": duration,
        "kind": "memo",
        "transcript": segments,
        "import_file": path.name,
    }


def cmd_switchbot(args: argparse.Namespace) -> int:
    layout = Layout(find_vault(args.vault))
    src = Path(args.dir).expanduser() if args.dir else layout.inbox
    if not src.exists():
        src.mkdir(parents=True, exist_ok=True)
        print(f"{layout.rel(src) if src.is_relative_to(layout.vault) else src} を作成しました。"
              " SwitchBotアプリから書き出したテキストをここに置いてください。", file=sys.stderr)
        print(json.dumps({"recordings": []}, ensure_ascii=False))
        return 0
    files = sorted(p for p in src.iterdir() if p.is_file() and p.suffix.lower() in SB_EXTS)
    recordings = [switchbot_file_to_recording(p) for p in files]
    print(json.dumps({"recordings": recordings}, ensure_ascii=False, indent=2))
    if args.move_processed and files:
        done_dir = src / "_processed"
        done_dir.mkdir(exist_ok=True)
        for path in files:
            path.rename(done_dir / path.name)
        print(f"{len(files)} 件を {done_dir.name}/ へ移動しました。", file=sys.stderr)
    print(f"SwitchBot: {len(files)} 件を読み込みました。", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- todos
def cmd_todos(args: argparse.Namespace) -> int:
    layout = Layout(find_vault(args.vault))
    state = load_state(layout)
    todos = [t for t in state["todos"].values() if args.all or not t.get("done")]
    todos.sort(key=sort_key_todo)
    if args.json:
        print(json.dumps(todos, ensure_ascii=False, indent=2))
        return 0
    if not todos:
        print("未完了のやることはありません。")
        return 0
    print(f"未完了 {sum(1 for t in todos if not t.get('done'))} 件")
    for todo in todos:
        box = "[x]" if todo.get("done") else "[ ]"
        bits = [f"- {box} {todo['text']}"]
        if todo.get("priority"):
            bits.append(f"〔{todo['priority']}〕")
        if todo.get("due"):
            bits.append(f"📅{todo['due']}")
        bits.append(f"({todo.get('date')} {todo.get('title')})")
        print(" ".join(bits))
    return 0


# ---------------------------------------------------------------- dashboard
def cmd_dashboard(args: argparse.Namespace) -> int:
    from dashboard import render_dashboard

    layout = Layout(find_vault(args.vault))
    state = load_state(layout)
    out = Path(args.out).expanduser() if args.out else layout.root / "dashboard.html"
    vault_name = args.vault_name or os.environ.get("RECORDER_VAULT_NAME") or layout.vault.name
    html = render_dashboard(state, days=args.days, today=datetime.now(JST).date(), vault_name=vault_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"ダッシュボードを書き出しました: {out} ({len(html) // 1024} KB)")
    return 0


def cmd_imported(args: argparse.Namespace) -> int:
    """すでに取り込んだ録音を一覧する（差分取り込みの判定用）。"""
    layout = Layout(find_vault(args.vault))
    state = load_state(layout)
    rows = sorted(
        (
            {
                "source": r.get("source"),
                "source_id": r.get("source_id"),
                "date": r.get("date"),
                "time": r.get("time"),
                "title": r.get("title"),
                "note": r.get("note"),
            }
            for r in state["recordings"].values()
            if not args.since or (r.get("date") or "") >= args.since
        ),
        key=lambda r: (r["date"] or "", r["time"] or ""),
    )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("まだ取り込んだ録音はありません。")
        return 0
    print(f"取り込み済み {len(rows)} 本")
    for row in rows:
        print(f"- {row['date']} {row['time']} [{row['source']}] {row['source_id']} {row['title']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="recorder_inbox", description="録音をObsidianノートへ取り込む")
    parser.add_argument("--vault", help="vault のルート（既定: Recorder/ か .git を上へ探索）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="正規化JSONからノート・日記・TODOを生成")
    p_build.add_argument("--input", "-i", default="-", help="正規化JSONのパス（既定: 標準入力）")
    p_build.add_argument("--dry-run", action="store_true", help="書き込まず結果だけ表示")
    p_build.add_argument("--today", help="基準日 YYYY-MM-DD（テスト用）")
    p_build.set_defaults(func=cmd_build)

    p_sb = sub.add_parser("switchbot", help="SwitchBotのエクスポートを正規化JSONへ")
    p_sb.add_argument("--dir", help="読み込み元（既定: Recorder/Inbox）")
    p_sb.add_argument("--move-processed", action="store_true", help="読み込んだファイルを _processed/ へ移動")
    p_sb.set_defaults(func=cmd_switchbot)

    p_todo = sub.add_parser("todos", help="やることを一覧表示")
    p_todo.add_argument("--json", action="store_true")
    p_todo.add_argument("--all", action="store_true", help="完了済みも含める")
    p_todo.set_defaults(func=cmd_todos)

    p_imp = sub.add_parser("imported", help="取り込み済みの録音を一覧（差分判定用）")
    p_imp.add_argument("--json", action="store_true")
    p_imp.add_argument("--since", help="YYYY-MM-DD 以降のみ")
    p_imp.set_defaults(func=cmd_imported)

    p_dash = sub.add_parser("dashboard", help="ダッシュボードHTMLを生成")
    p_dash.add_argument("--out", "-o", help="出力先（既定: Recorder/dashboard.html）")
    p_dash.add_argument("--days", type=int, default=60, help="タイムラインに含める日数（既定60）")
    p_dash.add_argument(
        "--vault-name",
        help="obsidian:// リンクに使う Obsidian 側の vault 名（既定: vault ディレクトリ名 / 環境変数 RECORDER_VAULT_NAME）",
    )
    p_dash.set_defaults(func=cmd_dashboard)
    return parser


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
