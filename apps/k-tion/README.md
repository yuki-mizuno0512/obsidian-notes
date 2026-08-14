# K-tion Cockpit

Galaxy Z Fold8 向けの個人ダッシュボード（コックピット）プロトタイプ。
折りたたみを開くと **今日のフォーカス → 2ペインの司令室** へリフローします。
カラーは「ふんわりパステル」（ラベンダー × ピーチ × ミント）、ライト/ダーク両対応。

## 使い方
`apps/k-tion/index.html` をブラウザで開くだけ（依存ライブラリなしの自己完結HTML）。
上部の `折 / 開` トグルで Fold8 の開閉、`◐ Theme` でライト/ダークを切り替え。
PC ブラウザでも Fold8 実機ブラウザでも動作します。

## 画面カード（既存スキル/タスクの流れに対応）
| カード | 内容 | 対応する既存スキル |
|--------|------|--------------------|
| 今日のフォーカス | Work/Private/MTG から“今日やること”上位3件を横断集約 | `top3-calendar-update` / `mtg-todo-list` |
| タスク Work | 案件・業務TODO（MTG議事録由来・HRMOS採用含む）を S/A/B/C ランク表示 | `mtg-todo-list` / `hrmos-new-application-triage` |
| タスク Private | 私用タスクを S/A/B/C ランク表示 | — |
| 今日のMTG | 当日の予定をタイムライン表示（Notionリンク付き） | `mtg-notion-slack-notify` |
| 今週のスケジュール | 週ストリップ（各日の予定件数） | Google Calendar |
| 要対応インボックス | メール要対応 / Messenger未返信 / 経費要確認 の件数集約 | `gmail-morning-triage` / `messenger-morning-check` / `mf-expense-triage` |

## 現状 / 次のステップ
- 表示データは **すべてモック**（UI とリフローの確認用）。
- 次段階（データ連携の候補）:
  - **今日のMTG / MTG-TODO** … Notion（議事録DB）から取得
  - **要対応メール** … Gmail トリアージ結果
  - **Messenger 未返信** … 返信チェック結果（Yuki Dashboard）
  - **経費 要確認** … MF 経費精算の未処理件数
  - **今週のスケジュール** … Google Calendar
