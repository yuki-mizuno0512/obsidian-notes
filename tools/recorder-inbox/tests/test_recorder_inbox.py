"""recorder-inbox のテスト: python3 -m unittest discover -s tools/recorder-inbox で実行."""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashboard  # noqa: E402
import recorder_inbox as ri  # noqa: E402

PLAUD_RAW = {
    "source": "plaud",
    "id": "a97d015dc6299b3712c7bd429423583e",
    # PLAUD の start_at は UTC。名前の "08-19" は JST 表記。
    "name": "08-19 08:07 の打ち合わせ",
    "start_at": "2026-08-18T23:07:02",
    "duration": 4176000,
    "kind": "meeting",
    "summary": "打ち合わせの要約",
    "todos": [
        {"text": "資料を共有する", "priority": "A", "due": "2026-08-20"},
        "議事録をNotionに転記",
    ],
    "memories": ["朝の光がきれいだった"],
    "transcript": [
        {"speaker": "yuki", "content": "おはようございます", "start_time": 1000, "end_time": 2500},
        {"speaker": "Speaker 2", "content": "よろしくお願いします", "start_time": 3000, "end_time": 4200},
    ],
}


class NormalizeTest(unittest.TestCase):
    def test_plaud_utc_is_converted_to_jst(self):
        rec = ri.normalize_recording(PLAUD_RAW)
        self.assertEqual(rec["date"], "2026-08-19")
        self.assertEqual(rec["time"], "08:07")
        self.assertTrue(rec["recorded_at"].endswith("+09:00"))

    def test_switchbot_times_are_local(self):
        rec = ri.normalize_recording(
            {"source": "switchbot", "tz": "jst", "title": "散歩", "recorded_at": "2026-08-19T07:20:00"}
        )
        self.assertEqual(rec["time"], "07:20")

    def test_plaud_name_prefix_and_bare_timestamp_titles_are_cleaned(self):
        self.assertEqual(ri.normalize_recording(PLAUD_RAW)["title"], "08:07 の打ち合わせ")
        bare = dict(PLAUD_RAW, name="2026-08-19 08:07:02")
        self.assertEqual(ri.normalize_recording(bare)["title"], "08:07 の録音")

    def test_todo_ids_are_stable_and_text_scoped(self):
        first = ri.normalize_recording(PLAUD_RAW)["todos"]
        second = ri.normalize_recording(PLAUD_RAW)["todos"]
        self.assertEqual([t["id"] for t in first], [t["id"] for t in second])
        self.assertNotEqual(first[0]["id"], first[1]["id"])

    def test_long_japanese_title_stays_inside_filesystem_limits(self):
        long_title = "とても長い日本語のタイトル" * 20
        rec = ri.normalize_recording(dict(PLAUD_RAW, name=long_title))
        self.assertLessEqual(len(rec["basename"].encode("utf-8")), ri.MAX_BASENAME_BYTES)
        self.assertLessEqual(len((rec["basename"] + ".md").encode("utf-8")), 255)

    def test_filename_unsafe_characters_are_dropped(self):
        rec = ri.normalize_recording(dict(PLAUD_RAW, name="面接/鎌田様: 1次面接 (P職)"))
        self.assertNotRegex(rec["basename"], r'[/:*?"<>|]')

    def test_missing_source_id_falls_back_to_deterministic_hash(self):
        raw = {"source": "switchbot", "tz": "jst", "title": "メモ", "recorded_at": "2026-08-19T07:20:00"}
        self.assertEqual(
            ri.normalize_recording(raw)["source_id"], ri.normalize_recording(raw)["source_id"]
        )


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.vault = Path(tempfile.mkdtemp())
        self.layout = ri.Layout(self.vault)

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def build(self, recordings=None, today="2026-08-21"):
        payload = {"recordings": recordings or [PLAUD_RAW]}
        path = self.vault / "in.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        args = ri.build_parser().parse_args(
            ["--vault", str(self.vault), "build", "-i", str(path), "--today", today]
        )
        return args.func(args)

    def test_build_writes_note_transcript_diary_and_todo(self):
        self.build()
        notes = list((self.vault / "Recorder/Recordings/2026").glob("*.md"))
        self.assertEqual(len(notes), 1)
        body = notes[0].read_text(encoding="utf-8")
        self.assertIn("## 要約", body)
        self.assertIn("資料を共有する", body)
        self.assertTrue((self.vault / "Recorder/Diary/2026-08-19.md").exists())
        self.assertTrue((self.vault / "Recorder/TODO.md").exists())
        self.assertEqual(len(list((self.vault / "Recorder/Transcripts/2026").glob("*.md"))), 1)
        state = json.loads((self.vault / "Recorder/.recorder-state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["todos"]), 2)
        self.assertFalse(any(t["done"] for t in state["todos"].values()))

    def test_rebuild_is_idempotent(self):
        self.build()
        todo_before = (self.vault / "Recorder/TODO.md").read_text(encoding="utf-8")
        note = next((self.vault / "Recorder/Recordings/2026").glob("*.md"))
        before = note.read_text(encoding="utf-8")
        self.build()
        self.assertEqual(note.read_text(encoding="utf-8"), before)
        self.assertEqual((self.vault / "Recorder/TODO.md").read_text(encoding="utf-8"), todo_before)

    def test_checked_box_survives_rebuild_and_moves_to_done(self):
        self.build()
        todo_file = self.vault / "Recorder/TODO.md"
        text = todo_file.read_text(encoding="utf-8")
        checked = text.replace("- [ ] 資料を共有する", "- [x] 資料を共有する", 1)
        self.assertNotEqual(text, checked)
        todo_file.write_text(checked, encoding="utf-8")

        self.build(today="2026-08-22")
        state = json.loads((self.vault / "Recorder/.recorder-state.json").read_text(encoding="utf-8"))
        done = [t for t in state["todos"].values() if t["done"]]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["text"], "資料を共有する")
        self.assertEqual(done[0]["done_at"], "2026-08-22")
        after = todo_file.read_text(encoding="utf-8")
        self.assertIn("## 完了", after)
        self.assertIn("- [x] 資料を共有する", after)
        self.assertIn("未完了 **1** 件", after)

    def test_unchecking_reopens_the_todo(self):
        self.build()
        todo_file = self.vault / "Recorder/TODO.md"
        todo_file.write_text(
            todo_file.read_text(encoding="utf-8").replace("- [ ] 資料を共有する", "- [x] 資料を共有する", 1),
            encoding="utf-8",
        )
        self.build(today="2026-08-22")
        todo_file.write_text(
            todo_file.read_text(encoding="utf-8").replace("- [x] 資料を共有する", "- [ ] 資料を共有する", 1),
            encoding="utf-8",
        )
        self.build(today="2026-08-23")
        state = json.loads((self.vault / "Recorder/.recorder-state.json").read_text(encoding="utf-8"))
        reopened = [t for t in state["todos"].values() if t["text"] == "資料を共有する"][0]
        self.assertFalse(reopened["done"])
        self.assertIsNone(reopened["done_at"])

    def test_user_text_below_the_managed_block_is_preserved(self):
        self.build()
        note = next((self.vault / "Recorder/Recordings/2026").glob("*.md"))
        note.write_text(note.read_text(encoding="utf-8") + "\n私の追記メモ\n", encoding="utf-8")
        self.build(recordings=[dict(PLAUD_RAW, summary="更新された要約")])
        body = note.read_text(encoding="utf-8")
        self.assertIn("私の追記メモ", body)
        self.assertIn("更新された要約", body)
        self.assertNotIn("打ち合わせの要約", body)

    def test_user_frontmatter_keys_are_kept(self):
        self.build()
        note = next((self.vault / "Recorder/Recordings/2026").glob("*.md"))
        body = note.read_text(encoding="utf-8").replace("date: 2026-08-19", "date: 2026-08-19\nmy_key: 大事", 1)
        note.write_text(body, encoding="utf-8")
        self.build()
        self.assertIn("my_key: 大事", note.read_text(encoding="utf-8"))

    def test_dry_run_writes_nothing(self):
        payload = {"recordings": [PLAUD_RAW]}
        path = self.vault / "in.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        args = ri.build_parser().parse_args(
            ["--vault", str(self.vault), "build", "-i", str(path), "--dry-run", "--today", "2026-08-21"]
        )
        args.func(args)
        self.assertFalse((self.vault / "Recorder").exists())

    def test_dashboard_payload_and_html(self):
        self.build()
        state = ri.load_state(self.layout)
        payload = dashboard.build_payload(state, 60, date(2026, 8, 21), "vault")
        self.assertEqual(len(payload["recordings"]), 1)
        self.assertEqual(len(payload["todos"]), 2)
        self.assertEqual(len(payload["daily"]), 30)
        html = dashboard.render_dashboard(state, 60, date(2026, 8, 21), "vault")
        self.assertIn("<title>声のインボックス</title>", html)
        self.assertNotIn("/*__DATA__*/null", html)
        self.assertNotIn("</script>", html.split("<script>")[1].split("const DATA")[1].split(";")[0])


class SwitchBotTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_srt_export_is_parsed_with_speakers_and_times(self):
        path = self.dir / "2026-08-19_0930_チーム定例.srt"
        path.write_text(
            "1\n00:00:01,000 --> 00:00:04,500\nyuki: おはようございます\n\n"
            "2\n00:00:05,000 --> 00:00:09,000\n田中: 資料を確認しました\n",
            encoding="utf-8",
        )
        rec = ri.switchbot_file_to_recording(path)
        self.assertEqual(rec["source"], "switchbot")
        self.assertEqual(rec["recorded_at"], "2026-08-19T09:30:00")
        self.assertEqual(rec["title"], "チーム定例")
        self.assertEqual(len(rec["transcript"]), 2)
        self.assertEqual(rec["transcript"][0]["speaker"], "yuki")
        self.assertEqual(rec["transcript"][0]["start_time"], 1000)
        self.assertEqual(rec["duration_ms"], 9000)

    def test_plain_text_export_with_timestamps(self):
        path = self.dir / "20260819-1400 面談メモ.txt"
        path.write_text("[00:12] yuki: 冒頭のあいさつ\n(1:05:30) 田中: 締めの確認\nただの行\n", encoding="utf-8")
        rec = ri.switchbot_file_to_recording(path)
        self.assertEqual(rec["recorded_at"], "2026-08-19T14:00:00")
        self.assertEqual(rec["transcript"][0]["start_time"], 12000)
        self.assertEqual(rec["transcript"][1]["start_time"], 3930000)
        self.assertEqual(rec["transcript"][2]["content"], "ただの行")

    def test_json_export_passes_through(self):
        path = self.dir / "x.json"
        path.write_text(json.dumps({"title": "t", "recorded_at": "2026-08-19T10:00:00"}), encoding="utf-8")
        self.assertEqual(ri.switchbot_file_to_recording(path)["source"], "switchbot")

    def test_normalizing_a_switchbot_export_yields_a_note_path(self):
        path = self.dir / "2026-08-19_0930_チーム定例.srt"
        path.write_text("1\n00:00:01,000 --> 00:00:04,500\nyuki: おはよう\n", encoding="utf-8")
        rec = ri.normalize_recording(ri.switchbot_file_to_recording(path))
        self.assertEqual(rec["note"], "Recorder/Recordings/2026/2026-08-19-0930-チーム定例.md")


class HelperTest(unittest.TestCase):
    def test_duration_formatting(self):
        self.assertEqual(ri.fmt_duration(1105000), "18m25s")
        self.assertEqual(ri.fmt_duration(8575000), "2h22m")
        self.assertEqual(ri.fmt_duration(0), "")

    def test_clock_formatting(self):
        self.assertEqual(ri.fmt_clock(69820), "01:09")
        self.assertEqual(ri.fmt_clock(3930000), "1:05:30")

    def test_wiki_link_drops_redundant_label(self):
        self.assertEqual(ri.wiki_link("Recorder/TODO.md", "Recorder/TODO"), "[[Recorder/TODO]]")
        self.assertEqual(ri.wiki_link("a/b.md", "ラベル"), "[[a/b|ラベル]]")

    def test_frontmatter_roundtrip(self):
        text = ri.dump_frontmatter({"title": "a: b", "tags": ["x", "y"], "empty": ""}) + "\n\n本文"
        data, body = ri.load_frontmatter(text)
        self.assertEqual(data["title"], "a: b")
        self.assertEqual(data["tags"], ["x", "y"])
        self.assertNotIn("empty", data)
        self.assertEqual(body.strip(), "本文")


if __name__ == "__main__":
    unittest.main()
