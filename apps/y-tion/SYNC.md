# Y-tion 同期手順（毎朝の自動リフレッシュ）

Y-tion のダッシュボードを Notion の最新状態に同期し、非公開 Artifact を更新する手順。
毎朝のスケジュールタスクがこの手順を実行する。**個人データは Artifact（非公開）にのみ反映し、GitHub には push しない。**

## 対象 Artifact
- URL: `https://claude.ai/code/artifact/680f81b4-50e6-432e-9cf1-c1d81976d1c3`
- 更新は Artifact ツールに `url` を渡して同一URLへ再パブリッシュする。

## データソースと取得クエリ

### 1. タスク Private ← Notion「パーソナルタスク」
- data source: `collection://af353e4a-dcf7-4e3f-bad1-966adff2d840`
- 未完了のみ:
  ```sql
  SELECT "やること" AS task, "ステータス" AS st, "種別" AS kind,
         "date:期限:start" AS due
  FROM "collection://af353e4a-dcf7-4e3f-bad1-966adff2d840"
  WHERE "ステータス" IS NULL OR "ステータス" != '完了'
  ORDER BY (due IS NULL), date(due) ASC
  ```
- ランク付け: 期限超過が長いほど高（S→A→B→C）。`ステータス='着手中'` は badge に表示。期限超過は `soon:true`（赤表示）。

### 2. タスク Work ← Notion MTG議事録のアクションアイテム
- `notion-query-meeting-notes` で直近2週間の会議を取得し、各会議の「### アクションアイテム」から未チェック `- [ ]` を収集。
- チーム定例（例: `weekly:GCP X`、`Xチーム<>篠原さん` 等）を優先。badge に会議の短縮名。

### 3.（任意）今日のMTG ← 当日の会議 / Google Calendar
### 4.（任意）今日の型・稼働中の習慣 ← Google Doc「矢田由貴_実践ノート」(`19KzT0kU5tOFHGC-nb9O7y4vhPyaYXhLuP5XEgmr7b58`)

## 実行手順
1. `apps/y-tion/index.html` をテンプレートとして読む。
2. 上記クエリで最新データを取得。
3. スクリプト内の `var priv=[…]`（`__SYNC__ Private` マーカー）と `var work=[…]`（`__SYNC__ Work` マーカー）を、取得データで置換。必要なら focus/型/習慣も実データへ。
4. Artifact ツールに `file_path`（生成HTML）と `url`（上記Artifact URL）を渡して再パブリッシュ。
5. **GitHub には push しない**（生成物は個人データを含むため）。テンプレート/手順の変更のみ commit 可。

## メモ
- 「パーソナルタスク」DBは2つ存在（`af353e4a…` に実データ、`9db9d39a…` は空）。実データ側を使用。
- 真の「開くたび同期」は Artifact の `mcp` 機能（閲覧者のNotionコネクタを直接呼ぶ）で実現可能。閲覧者側コネクタの応答形状を検証してから導入する。
