// ハイクラス人材マッチング — スコアリングエンジン & UI
(function () {
  "use strict";

  var SENIORITY_RANK = { manager: 1, director: 2, vp: 3, cxo: 4 };
  var SENIORITY_LABEL = {
    manager: "マネージャー", director: "ディレクター/部長", vp: "VP", cxo: "CxO",
  };
  var ROLE_LABEL = {
    engineering: "エンジニアリング", product: "プロダクト", sales: "セールス/CS",
    marketing: "マーケティング", finance: "ファイナンス", operations: "オペレーション/経営",
    hr: "人事/組織", data: "データ/AI", legal: "法務",
  };
  var IND_LABEL = {
    saas: "SaaS", fintech: "フィンテック", ecommerce: "EC/D2C",
    manufacturing: "製造業", gaming: "ゲーム", consulting: "コンサル",
  };
  var LOC_LABEL = { tokyo: "東京", osaka: "大阪", fukuoka: "福岡", remote: "リモート" };
  var LANG_LABEL = { ja: "日本語", en: "英語" };

  // 各要素の重み（合計で正規化するので相対値でよい）
  var WEIGHTS = {
    role: 26, seniority: 20, years: 12, industries: 14,
    salary: 8, locations: 8, languages: 4, mgmt: 4, keywords: 14,
  };

  // ---- チップ選択のトグル ----
  function wireChips(id) {
    document.getElementById(id).addEventListener("click", function (e) {
      if (e.target.classList.contains("chip")) e.target.classList.toggle("on");
    });
  }
  ["industries", "locations", "languages"].forEach(wireChips);

  function selectedChips(id) {
    return Array.prototype.map.call(
      document.querySelectorAll("#" + id + " .chip.on"),
      function (c) { return c.dataset.v; }
    );
  }

  // ---- レンジ表示 ----
  var yearsEl = document.getElementById("years");
  var budgetEl = document.getElementById("budget");
  var BUDGET_MAX = 4000; // 右端＝上限なし
  yearsEl.addEventListener("input", function () {
    var v = parseInt(yearsEl.value, 10);
    document.getElementById("yearsVal").textContent = v === 0 ? "指定なし" : v + "年";
  });
  budgetEl.addEventListener("input", function () {
    var v = parseInt(budgetEl.value, 10);
    document.getElementById("budgetVal").textContent = v >= BUDGET_MAX ? "上限なし" : v + "万円";
  });

  function readCriteria() {
    var kw = document.getElementById("keywords").value
      .split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    return {
      role: document.getElementById("role").value,
      seniority: document.getElementById("seniority").value, // "" / "0" / rank key
      years: parseInt(yearsEl.value, 10),
      budget: parseInt(budgetEl.value, 10),
      industries: selectedChips("industries"),
      locations: selectedChips("locations"),
      languages: selectedChips("languages"),
      mgmt: parseInt(document.getElementById("mgmt").value, 10) || 0,
      keywords: kw,
    };
  }

  // ---- スコアリング ----
  // 各項目を 0..1 で評価し重み付け。指定のない項目は分母から除外（＝公平）。
  function score(cand, c) {
    var parts = [];   // {w, s, reason, hit}
    function add(key, s, reason, hit) {
      parts.push({ w: WEIGHTS[key], s: s, reason: reason, hit: !!hit });
    }

    // 職種はハードフィルタ（呼び出し側で絞り込み済み）。合致は前提なのでスコアには影響させず、
    // コンテキストとしてバッジ表示のみ行う（重み0）。
    if (c.role) parts.push({ w: 0, s: 1, reason: "職種「" + ROLE_LABEL[c.role] + "」に合致", hit: true });

    if (c.seniority && c.seniority !== "0") {
      var need = SENIORITY_RANK[c.seniority];
      var have = SENIORITY_RANK[cand.seniority] || 0;
      var s = have >= need ? 1 : Math.max(0, 1 - (need - have) * 0.5);
      add("seniority", s,
        have >= need ? "役職レベル " + SENIORITY_LABEL[cand.seniority] + " が要件を満たす"
                     : "役職レベルがやや不足", have >= need);
    }

    if (c.years > 0) {
      var s2 = cand.years >= c.years ? 1
             : Math.max(0, 1 - (c.years - cand.years) * 0.15);
      add("years", s2,
        cand.years >= c.years ? "経験 " + cand.years + "年（要件 " + c.years + "年 を充足）"
                              : "経験 " + cand.years + "年（要件 " + c.years + "年 にやや不足）",
        cand.years >= c.years);
    }

    if (c.industries.length) {
      var matched = c.industries.filter(function (i) { return cand.industries.indexOf(i) >= 0; });
      var s3 = matched.length / c.industries.length;
      add("industries", s3,
        matched.length
          ? "業界一致: " + matched.map(function (m) { return IND_LABEL[m]; }).join("・")
          : "業界経験の一致なし",
        matched.length > 0);
    }

    // 予算：上限が設定されている場合のみ評価。希望下限が予算内なら満点、超過分で減点。
    if (c.budget < BUDGET_MAX) {
      if (cand.salaryMin <= c.budget) {
        add("salary", 1, "想定年収 " + cand.salaryMin + "〜" + cand.salaryMax + "万円（予算内）", true);
      } else {
        var over = cand.salaryMin - c.budget;
        add("salary", Math.max(0, 1 - over / 800), "想定年収が予算を " + over + "万円 超過", false);
      }
    }

    if (c.locations.length) {
      var lmatch = c.locations.some(function (l) { return cand.locations.indexOf(l) >= 0; });
      add("locations", lmatch ? 1 : 0,
        lmatch ? "勤務地の条件に対応可" : "勤務地の条件に非対応", lmatch);
    }

    if (c.languages.length) {
      var lang = c.languages.filter(function (l) { return cand.languages.indexOf(l) >= 0; });
      var s5 = lang.length / c.languages.length;
      add("languages", s5,
        s5 === 1 ? "語学要件を充足（" + c.languages.map(function (l) { return LANG_LABEL[l]; }).join("・") + "）"
                 : "語学要件を一部のみ充足",
        s5 === 1);
    }

    if (c.mgmt > 0) {
      var s6;
      if (c.mgmt === 1) { // IC / プレイヤー希望
        s6 = cand.management <= 5 ? 1 : 0.4;
        add("mgmt", s6, cand.management <= 5 ? "IC/プレイヤー志向に合致" : "マネジメント色が強い", cand.management <= 5);
      } else {
        s6 = cand.management >= c.mgmt ? 1 : Math.max(0, cand.management / c.mgmt);
        add("mgmt", s6,
          cand.management >= c.mgmt ? "マネジメント規模 約" + cand.management + "名（要件充足）"
                                    : "マネジメント規模 約" + cand.management + "名（要件にやや不足）",
          cand.management >= c.mgmt);
      }
    }

    if (c.keywords.length) {
      var hay = (cand.skills.join(" ") + " " + cand.summary + " " + cand.title).toLowerCase();
      var hits = c.keywords.filter(function (k) { return hay.indexOf(k.toLowerCase()) >= 0; });
      var s7 = hits.length / c.keywords.length;
      add("keywords", s7,
        hits.length ? "キーワード一致: " + hits.join("・") : "キーワードの一致なし",
        hits.length > 0);
    }

    if (!parts.length) return null; // 要件が何も指定されていない
    var wsum = parts.reduce(function (a, p) { return a + p.w; }, 0);
    // 重み付き要件が職種フィルタ（重み0）のみの場合、対象者は全員が満点扱い。
    if (wsum === 0) return { pct: 100, parts: parts };
    var ssum = parts.reduce(function (a, p) { return a + p.w * p.s; }, 0);
    return { pct: Math.round((ssum / wsum) * 100), parts: parts };
  }

  // ---- 描画 ----
  function initials(name) {
    var t = name.replace(/\s+/g, "");
    return t.slice(0, 1);
  }

  function render(ranked, anyCriteria) {
    var res = document.getElementById("results");
    var count = document.getElementById("count");
    var label = document.getElementById("countLabel");

    if (!anyCriteria) {
      count.textContent = "—";
      label.textContent = "要件が指定されていません。少なくとも1つ条件を選択してください。";
      res.innerHTML = '<div class="empty">条件を入力すると候補者が表示されます。</div>';
      return;
    }

    var THRESHOLD = 40; // これ未満は関連性が低いとみなし非表示
    var shown = ranked.filter(function (r) { return r.result.pct >= THRESHOLD; });
    count.textContent = shown.length + "名";
    label.textContent = "適合度 " + THRESHOLD + "% 以上を適合度順に表示（上位ほど要件に合致）";

    if (!shown.length) {
      res.innerHTML = '<div class="empty">適合度40%以上の候補者が見つかりませんでした。条件を緩めてみてください。</div>';
      return;
    }

    res.innerHTML = shown.map(function (r) {
      var cand = r.cand, pct = r.result.pct;
      var badges = r.result.parts
        .filter(function (p) { return p.hit; })
        .map(function (p) { return '<span class="badge hit">' + esc(p.reason) + "</span>"; })
        .join("");
      var misses = r.result.parts
        .filter(function (p) { return !p.hit; })
        .map(function (p) { return '<span class="badge">' + esc(p.reason) + "</span>"; })
        .join("");
      var av = cand.availability === "active"
        ? '<span class="avail active">積極検討中</span>'
        : '<span class="avail passive">良い話があれば</span>';
      return (
        '<div class="cand">' +
          '<div class="avatar">' + esc(initials(cand.name)) + "</div>" +
          "<div>" +
            "<h3>" + esc(cand.name) + av + "</h3>" +
            '<div class="tt">' + esc(cand.title) + "</div>" +
            '<div class="meta">' + esc(ROLE_LABEL[cand.role]) + " ・ 経験" + cand.years + "年 ・ " +
              esc(cand.industries.map(function (i) { return IND_LABEL[i]; }).join("/")) + " ・ " +
              esc(cand.locations.map(function (l) { return LOC_LABEL[l]; }).join("/")) + "</div>" +
            '<p class="sum">' + esc(cand.summary) + "</p>" +
            '<div class="badges">' + badges + misses + "</div>" +
          "</div>" +
          '<div class="score">' +
            '<div class="ring" style="--v:' + pct + '"><div>' + pct + "</div></div>" +
            '<div class="lab">適合度</div>' +
          "</div>" +
        "</div>"
      );
    }).join("");
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  // ---- 実行 ----
  document.getElementById("reqForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var c = readCriteria();
    var anyCriteria = c.role || (c.seniority && c.seniority !== "0") || c.years > 0 ||
      c.budget < BUDGET_MAX || c.industries.length || c.locations.length ||
      c.languages.length || c.mgmt > 0 || c.keywords.length;

    // 職種はハードフィルタ。指定時はその職種の候補者のみを対象にする。
    var pool = c.role
      ? window.CANDIDATES.filter(function (x) { return x.role === c.role; })
      : window.CANDIDATES;

    var ranked = pool.map(function (cand) {
      return { cand: cand, result: score(cand, c) };
    }).filter(function (r) { return r.result; });

    ranked.sort(function (a, b) {
      if (b.result.pct !== a.result.pct) return b.result.pct - a.result.pct;
      return b.cand.years - a.cand.years;
    });

    render(ranked, anyCriteria);
    document.getElementById("summary").scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  document.getElementById("resetBtn").addEventListener("click", function () {
    document.getElementById("reqForm").reset();
    document.getElementById("yearsVal").textContent = "指定なし";
    document.getElementById("budgetVal").textContent = "上限なし";
    document.querySelectorAll(".chip.on").forEach(function (c) { c.classList.remove("on"); });
    render([], false);
  });
})();
