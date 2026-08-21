---
name: "recorder-inbox"
description: "PLAUD と SwitchBot AIマインドクリップの録音を Obsidian vault に取り込むスキル。録音ごとのノート、その日の日記（おもいで付き）、やることリスト、ダッシュボードを生成する。「録音を取り込んで」「PLAUDを同期して」「今日の録音まとめて」「録音からTODO出して」「日記にしておいて」「ダッシュボード更新して」などの依頼で使う。定期実行にも対応。"
---

# 録音の取り込み（PLAUD / SwitchBot）

録音 → 要約・やること・おもいで → Obsidian ノート → ダッシュボード。
判断はこちらで行い、ファイル配置とチェック状態の保全はスクリプトに任せる。

- ツール: `tools/recorder-inbox/recorder_inbox.py`（標準ライブラリのみ）
- 正規化JSONの形: `tools/recorder-inbox/schema.md`
- 設計上の約束: `tools/recorder-inbox/README.md`

## 前提

- やることのチェックは `Recorder/TODO.md` **だけ**で行う。ノート側は参照用。
- ノートの `<!-- recorder:begin -->` 〜 `<!-- recorder:end -->` の外は再生成しない。
- PLAUD の `start_at` は **UTC**。JST 変換はスクリプトが行うので、`tz` を書き換えないこと。
- MTG由来のやることの完了管理は Notion「MTG TODO」DB に一本化されている。
  こちらは録音由来の私的なやること・おもいで側の受け皿。**自動でNotionに書き込まない**。
  会議・面接由来で登録した方がよいものは、最後に候補として提示するだけにする。

## 手順

### 1. 取り込み済みを確認する

```bash
python3 tools/recorder-inbox/recorder_inbox.py imported --json --since <14日前>
```

ここに出てくる `source_id` は再取得しない（差分だけを扱う）。

### 2. PLAUD から録音を取る

`mcp__Plaud__list_files` を使う。未ロードなら先に ToolSearch で
`select:mcp__Plaud__list_files,mcp__Plaud__get_note,mcp__Plaud__get_transcript` を実行する。

1. `list_files` に `date_from` / `date_to`（既定は直近7日）を渡して一覧を取る。
2. 未取り込みの各録音について `get_note`（PLAUDのAI要約）と
   `get_transcript`（`block: "transaction"`、`limit: 200`、`next_cursor` があれば続けて取得）。
3. **`get_note` と `get_transcript` が両方空なら、その録音はまだ処理中**。
   スキップして「未処理（次回に回す）」として報告する。取り込み済み扱いにしないこと。
4. 長い録音（1時間超）は全ページ読む前に、まず要約と最初の2ページで全体像を掴み、
   固有名詞・数字・依頼事項が出る箇所を重点的に読む。

### 3. SwitchBot のエクスポートを取る

```bash
python3 tools/recorder-inbox/recorder_inbox.py switchbot > /tmp/recorder-sb.json
```

`Recorder/Inbox/` が空なら 0 件。SwitchBot アプリからの書き出しをそこに置くよう案内する。
文字起こしは入っているが要約・やること・おもいでは空なので、こちらで埋める。

### 4. 正規化JSONを組む

`schema.md` の形で1本ずつ作る。書き分けは同ファイルの表に従う。加えて:

- `kind` を必ず決める（`meeting` / `interview` / `diary` / `memo` / `study` / `call` / `lecture` / `life`）。
- `summary` は3〜6行。逐語の言い換えではなく「何の場で何が起きたか」。
- `todos` は **自分が動くもの**を優先し、期日が会話に出ていれば `due` に入れる。
  他人の宿題は `owner` を明示。曖昧な言い切り（「そのうち」「またやる」）はやることにしない。
- `memories` は日記・生活系で厚めに。情景と気持ちを、本人の言い回しを残して1〜3行ずつ。
- `interview` は候補者名・所属・ポジションをそのまま残し、要約は事実ベースにする
  （評価・推測を混ぜない）。
- `quotes` は言い回しに価値がある発言だけ。2〜4件で十分。
- 文字起こしは取得できた範囲を `transcript` にそのまま渡す（別ノートに全文が書き出される）。

### 5. 生成する

```bash
python3 tools/recorder-inbox/recorder_inbox.py build -i /tmp/recorder-in.json
```

初回や大量取り込みでは `--dry-run` で配置を確認してから本実行する。

### 6. ダッシュボードを更新する

```bash
python3 tools/recorder-inbox/recorder_inbox.py dashboard --out Recorder/dashboard.html
```

Artifact として公開する場合は、このファイルを `Artifact` ツールで publish する。
**2回目以降は同じ `file_path` で publish し直す**（URLを変えない）。
favicon は `🎙` で固定。

### 7. 報告する

会話には次の形で短く返す。

```
取り込み: N本（PLAUD n / SwitchBot m）・未処理 k本
- 2026-08-19 09:17 AI＊HR勉強会（35m）→ やること2
やること: +3 / 完了 +1 / 未完了 12（期限切れ 1）
おもいで: 2件（2026-08-19 の日記に）
```

- 未処理があれば「PLAUD側の処理待ち。次回取り込む」と添える。
- 期限切れがあれば、その項目だけ本文を引用して先に出す。
- 面接・候補者の情報は vault の外（Slack・Notion・メール）へ自動で送らない。
- Notion「MTG TODO」に入れた方がよい項目があれば、候補として列挙して確認を取る。

## 注意

- `Recorder/TODO.md` のチェックは毎回読み戻される。ユーザーがチェックを外した項目を
  勝手に完了へ戻さないこと（スクリプトが正しく扱う）。
- やることの文面を直したいときは元の録音ノートを直して再取り込みする
  （ID が本文ハッシュのため、`TODO.md` 側の編集は次回上書きされる）。
- 同じ録音を2回 `build` しても中身は変わらない（冪等）。迷ったら再実行してよい。
- 定期実行（毎朝など）で呼ぶ場合は、直近1日分を対象にし、0本なら何も報告しない。
