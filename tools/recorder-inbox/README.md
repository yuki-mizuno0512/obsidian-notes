# recorder-inbox

PLAUD と SwitchBot AIマインドクリップの録音を、この Obsidian vault の中に
「読める形」で溜めていくための取り込みツール。

- 判断（要約・やること抽出・おもいで抽出）は **Claude** が行う
- ファイル配置・ID付け・チェック状態の保全は **このスクリプト** が決定論的に行う

境界を分けているのは、再取り込みで手で書いた内容やチェックが消えないようにするため。

## 使い方

```bash
# 1. SwitchBot のエクスポートを正規化JSONにする（PLAUD は Claude が MCP から取得する）
python3 tools/recorder-inbox/recorder_inbox.py switchbot > /tmp/sb.json

# 2. 正規化JSON からノート・日記・やることリストを生成
python3 tools/recorder-inbox/recorder_inbox.py build -i /tmp/sb.json

# 3. 取り込み済みの確認 / やることの確認
python3 tools/recorder-inbox/recorder_inbox.py imported --since 2026-08-01
python3 tools/recorder-inbox/recorder_inbox.py todos

# 4. ダッシュボードHTMLを書き出す（Artifact として公開できる）
python3 tools/recorder-inbox/recorder_inbox.py dashboard --out Recorder/dashboard.html
```

`--dry-run` を付ければ書き込まずに結果だけ確認できる。
`--vault` を省略すると `Recorder/` か `.git` を目印に vault ルートを自動判定する。

通常は Claude 側から `/recorder-inbox`（`.claude/skills/recorder-inbox`）で呼ぶ。

## 生成されるもの

```
Recorder/
  Recordings/2026/2026-08-19-0917-AI＊HR勉強会.md   録音1本＝1ノート
  Transcripts/2026/...                              話者付き文字起こし全文
  Diary/2026-08-19.md                               その日の記録・おもいで・やること
  TODO.md                                           やることの唯一の管理場所
  Inbox/                                            SwitchBot のエクスポート置き場
  .recorder-state.json                              取り込み済みID・やることの状態
```

## 設計上の約束

**やることのチェックは `Recorder/TODO.md` だけ**。各録音ノートは参照用の箇条書きに
とどめる。同じ項目にチェックボックスが2箇所あると必ず食い違うため。
`TODO.md` のチェックは毎回読み戻され、`.recorder-state.json` に記録される
（完了 → `## 完了`、外す → 未完了に戻る）。

**管理ブロックの外は触らない**。ノートの `<!-- recorder:begin -->` 〜
`<!-- recorder:end -->` だけを再生成する。その下に書いた自由記述と、frontmatter に
自分で足したキーは再取り込みでも残る。

**PLAUD の `start_at` は UTC**。録音名の日付は JST。両方が一致することを確認済み
（`start_at: 2026-08-18T23:07:02` の録音名が `2026-08-19 08:07:02`）。
このツールは JST に変換して日付・時刻・ファイル名を決める。SwitchBot 由来は
`"tz": "jst"` を付けてローカル時刻として扱う。

**音声URLは保存しない**。PLAUD の presigned URL は24時間で失効するため、
`source_id` だけを残し、必要になったら MCP で取り直す。

**ファイル名は 120 バイトまで**。この vault には 255 バイトを超える日本語ファイル名が
既にあり、Linux 環境ではチェックアウトできない（`File name too long`）。
生成側では slug を 60 バイト、ファイル名全体を 120 バイトに抑えている。

**やることのIDは `source_id` と本文のハッシュ**。文面を編集すると別項目になるので、
表現を直すときは `TODO.md` ではなく元の録音ノートを直して再取り込みする。

## SwitchBot について

SwitchBot AIマインドクリップには公開APIが無いため、アプリから書き出したファイルを
`Recorder/Inbox/` に置いて取り込む。対応形式は `.txt` `.md` `.srt` `.vtt` `.json`。

ファイル名に日付（`2026-08-19` / `20260819`）と時刻（`0930` / `09-30`）が入っていれば
それを録音時刻として使い、残りをタイトルにする。無ければファイルの更新時刻を使う。
`--move-processed` を付けると読み込んだファイルを `Inbox/_processed/` へ移す。

## テスト

```bash
cd tools/recorder-inbox && python3 -m unittest discover -s tests -t .
```
