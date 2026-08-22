# 正規化JSON

`build` が受け取る形。`recordings` の配列だけが必須で、単体オブジェクトや
配列を直接渡してもよい（内部で包む）。要約・やること・おもいでは Claude が埋める。

```json
{
  "recordings": [
    {
      "source": "plaud",                      // plaud | switchbot（既定 plaud）
      "source_id": "a97d015d...",             // PLAUD の file_id。無ければ自動生成
      "tz": "utc",                            // 時刻の解釈。plaud は utc、switchbot は jst
      "title": "AI＊HR勉強会",                 // 先頭の "08-19 " は自動で外す
      "recorded_at": "2026-08-19T09:17:51",   // start_at / created_at も可
      "duration_ms": 2102000,                 // duration でも可（ミリ秒）
      "kind": "study",                        // meeting|interview|diary|memo|study|call|lecture|life
      "people": ["yuki", "田中"],
      "topics": ["話題1", "話題2"],
      "summary": "Markdown可。3〜6行を目安に。",
      "highlights": ["決まったこと・効いた一言"],
      "memories": ["後から読み返したい情景・気持ち"],
      "todos": [
        {
          "text": "資料を共有する",            // 必須
          "priority": "A",                    // S|A|B|C（任意）
          "due": "2026-08-20",                // YYYY-MM-DD（任意）
          "owner": "self",                    // self 以外は @表示（任意）
          "context": "勉強会の最後に依頼された" // 任意
        },
        "文字列だけでも可"
      ],
      "candidate": {                          // kind=interview のときだけ
        "name": "山田 太郎",
        "position": "キャピタリスト／東京【P職】",
        "channel": "ビズリーチ（スカウト）",
        "stage": "1次面接",
        "agency": "—"
      },
      "interview": {
        "interviewers": ["水野", "堀江"],       // 配列は ／ で連結される
        "next_step": "2次面接の日程調整",
        "scheduled": "2026-08-25 10:00"
      },
      "quotes": [{ "speaker": "yuki", "text": "…", "at_ms": 150000 }],
      "transcript": [
        { "speaker": "Speaker 1", "content": "…", "start_time": 69820, "end_time": 99260 }
      ]
    }
  ]
}
```

## 書き分けの指針

| フィールド | 入れるもの | 入れないもの |
| --- | --- | --- |
| `summary` | 何の会で何が決まったか | 逐語の言い換え |
| `highlights` | 決定・数字・効いた一言 | 感想 |
| `memories` | 情景・気持ち・後で読み返したいこと | 業務上の決定事項 |
| `todos` | 自分が動くこと（owner=self が既定） | 他人の宿題（owner を明示） |
| `quotes` | そのままの言い回しに価値がある発言 | 要約で足りる発言 |

`candidate` / `interview` は「## 候補者・選考」の表として出力され、`name` と `position` は
frontmatter にも入る（Obsidian の検索・プロパティで引ける）。評価や推測は入れず、
本人が言ったこと・決まったことだけを書く。

`kind` は日記・生活系（`diary` / `life`）なら `memories` を厚めに、
会議・面接（`meeting` / `interview`）なら `highlights` と `todos` を厚めに。
