#!/usr/bin/env python3
"""
job_watch.py — 求人フィードを監視して「新着確認ページ」を生成するスクリプト
(GitHub Actions上で毎日実行し、GitHub Pagesで公開する想定。ローカルでも動きます)

仕組み:
  1. sources.yaml の各RSSフィードを取得
  2. include_keywords / exclude_keywords でフィルタ
  3. state.json(既読リスト)に無いURLだけ「新着」として記録
  4. site/index.html を生成(Actions → GitHub Pages に公開される)
     → ブラウザで開けば新着が確認できる
"""

import datetime
import html
import json
import pathlib
import sys
import urllib.parse

import yaml
import feedparser

ROOT = pathlib.Path(__file__).parent
STATE_PATH = ROOT / "state.json"
CONFIG_PATH = ROOT / "sources.yaml"
SITE_DIR = ROOT / "site"
USER_AGENT = "job-watch-pages/1.0"
MAX_HISTORY = 200  # ページに残す過去アイテムの上限

MUSTS = ["社会保険(厚生年金・健康保険)加入", "雇用保険加入", "週20時間以上",
         "時給1,500円以上", "残業なし", "副業可"]


def jst_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        conf = yaml.safe_load(f) or {}
    conf.setdefault("include_keywords", [])
    conf.setdefault("exclude_keywords", [])
    conf.setdefault("max_items_per_run", 20)
    conf.setdefault("sources", [])
    conf.setdefault("search_keywords", "動画編集 SNS")
    conf.setdefault("search_location", "仙台市")
    return conf


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("[warn] state.json が壊れていたので初期化します")
            data = {}
    else:
        data = {}
    data.setdefault("seen", [])
    data.setdefault("items", [])   # 過去に見つけたアイテムの履歴
    data.setdefault("last_run", None)
    return data


def fetch_items(source: dict) -> list:
    """1つのフィードからアイテム(title/link/source)の一覧を取り出す"""
    parsed = feedparser.parse(
        source["url"],
        request_headers={"User-Agent": USER_AGENT},
    )
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"フィード取得失敗: {parsed.bozo_exception}")

    items = []
    for e in parsed.entries:
        items.append({
            "title": (e.get("title") or "").strip(),
            "link": (e.get("link") or "").strip(),
            "source": source.get("name", source["url"]),
        })
    return items


def matches(title: str, conf: dict) -> bool:
    for word in conf["exclude_keywords"]:
        if word in title:
            return False
    for word in conf["include_keywords"]:
        if word not in title:
            return False
    return True


# ─────────────────────────────────────────────
# ページ生成(求人ウォッチ・コンソールと同じデザイン)
# ─────────────────────────────────────────────

def launcher_boards(conf: dict) -> list:
    kw = conf["search_keywords"]
    loc = conf["search_location"]
    enc = urllib.parse.quote
    return [
        ("Indeed", "最も求人が多く、メールアラートも強い。まずここ",
         f"https://jp.indeed.com/jobs?q={enc(kw)}&l={enc(loc)}"),
        ("スタンバイ", "契約・パート枠の時給表記が分かりやすい",
         f"https://jp.stanby.com/search?q={enc(kw)}&location={enc(loc)}"),
        ("Wantedly", "小規模制作会社の契約・パート枠が多い",
         f"https://www.wantedly.com/projects?keyword={enc(kw)}&address={enc(loc)}"),
        ("LinkedIn", "フルリモートの求人を含めて幅広く",
         f"https://www.linkedin.com/jobs/search/?keywords={enc(kw)}&location={enc(loc)}"),
        ("タウンワーク", "地域のパート求人が豊富(開いたら同じキーワードで検索)",
         "https://townwork.net/"),
        ("ハローワーク", "社会保険の適用欄が明記されていて確認が早い",
         "https://www.hellowork.go.jp/"),
        ("リクナビ派遣", "派遣なら時給1,600円超と保険加入が契約で明確",
         "https://haken.rikunabi.com/"),
    ]


def item_row(it: dict, is_new: bool, run_date: str) -> str:
    badge = '<span class="badge">NEW</span>' if is_new else ""
    seen = it.get("first_seen", run_date)
    fresh = ' fresh' if is_new or seen >= run_date else ''
    return f"""      <li class="item{fresh}">
        <a href="{html.escape(it['link'])}" target="_blank" rel="noopener">{html.escape(it['title'])}</a>
        <div class="meta"><span class="src">{html.escape(it['source'])}</span>{badge}
          <span class="date">{html.escape(seen)}</span></div>
      </li>"""


def build_html(new_items: list, history: list, run_date: str, conf: dict) -> str:
    sources_list = ", ".join(s.get("name", "") for s in conf["sources"])
    kw = "、".join(conf["include_keywords"]) or "(指定なし)"
    ex = "、".join(conf["exclude_keywords"]) or "(指定なし)"

    new_rows = "\n".join(item_row(it, True, run_date) for it in new_items) or \
        '      <li class="item none">新着はありません — 監視は正常に動いています</li>'
    past_rows = "\n".join(item_row(it, False, run_date) for it in history)

    boards = "\n".join(
        f'      <a class="board" href="{html.escape(u)}" target="_blank" rel="noopener">'
        f'<b>{html.escape(n)}</b><span class="d">{html.escape(d)}</span></a>'
        for n, d, u in launcher_boards(conf))

    musts = "\n".join(
        f'      <span class="must">{html.escape(m)}</span>' for m in MUSTS)

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>求人ウォッチ.console — {html.escape(run_date)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@700;900&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#151A23;--panel:#1F2733;--panel2:#242E3C;--line:#33404F;--ink:#ECF1F4;
--mut:#8A97A8;--teal:#4FC3B8;--amber:#F2B155;--rose:#E4707F}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--ink);
font-family:"Noto Sans JP","Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif;
line-height:1.8;font-size:14.5px;padding:0 0 80px}}
h1,h2,.disp{{font-family:"Zen Kaku Gothic New","Noto Sans JP",sans-serif}}
header{{border-bottom:1px solid var(--line);
background:linear-gradient(180deg,#1A212C 0%,var(--bg) 100%)}}
.hbar{{max-width:860px;margin:0 auto;padding:22px 20px 14px}}
.hbar .logo{{font-weight:900;font-size:22px;letter-spacing:.04em}}
.hbar .logo .dot{{color:var(--teal)}}
.hbar .tag{{color:var(--mut);font-size:12.5px;margin-top:2px}}
.wrap{{max-width:860px;margin:0 auto;padding:0 20px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:22px;margin-top:18px}}
.kicker{{display:inline-block;background:var(--teal);color:#10151D;font-size:11px;
font-weight:700;border-radius:4px;padding:1px 8px;letter-spacing:.08em;
vertical-align:2px;margin-right:9px}}
.panel h2{{font-size:16px;margin-bottom:4px;display:flex;align-items:center}}
.sub{{color:var(--mut);font-size:12.5px;margin-bottom:14px}}
.n{{color:var(--teal);font-weight:700;margin-left:6px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin-top:4px}}
.bcard{{flex:1;min-width:140px;background:var(--panel2);border:1px solid var(--line);
border-radius:8px;padding:12px 14px}}
.bcard .num{{font-family:"Zen Kaku Gothic New";font-size:24px;font-weight:900;color:var(--teal)}}
.bcard .lbl{{font-size:12px;color:var(--mut)}}
ul{{list-style:none}}
.item{{padding:11px 4px;border-bottom:1px solid var(--line);font-size:13.5px}}
.item:last-child{{border-bottom:none}}
.item a{{color:var(--ink);text-decoration:none}}
.item a:hover{{color:var(--teal)}}
.item.fresh a{{color:#BDEDE7;font-weight:700}}
.item.none{{color:var(--mut)}}
.meta{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11px;
color:var(--mut);margin-top:3px}}
.src{{background:rgba(79,195,184,.12);color:var(--teal);border-radius:999px;padding:0 9px}}
.badge{{background:var(--amber);color:#10151D;font-weight:700;border-radius:999px;
padding:0 8px;font-size:10.5px}}
.date{{margin-left:auto}}
.board-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}}
.board{{background:var(--panel2);border:1px solid var(--line);border-radius:8px;
padding:13px 14px;display:flex;flex-direction:column;gap:5px;color:var(--ink);
text-decoration:none}}
.board b{{font-size:14px}}
.board:hover b{{color:var(--teal)}}
.board .d{{font-size:11.5px;color:var(--mut)}}
.musts{{display:flex;flex-wrap:wrap;gap:8px}}
.must{{border:1px solid var(--teal);color:var(--teal);border-radius:999px;
padding:4px 13px;font-size:12.5px;font-weight:700;
background:rgba(79,195,184,.08)}}
.cond{{font-size:12.5px;color:var(--mut)}}
.cond b{{color:var(--ink);font-weight:600}}
footer{{text-align:center;color:var(--mut);font-size:11px;margin-top:24px}}
</style>
</head>
<body>
<header>
  <div class="hbar">
    <div class="logo disp">求人ウォッチ<span class="dot">.</span>daily</div>
    <div class="tag">動画・SNS制作 専門職 — 週30h / 社会保険 / 副業可</div>
  </div>
</header>
<div class="wrap">

  <div class="panel">
    <h2><span class="kicker">STATUS</span>監視ステータス</h2>
    <p class="sub">最終チェック: {html.escape(run_date)}</p>
    <div class="stats">
      <div class="bcard"><div class="num">{len(new_items)}</div><div class="lbl">今朝の新着</div></div>
      <div class="bcard"><div class="num">{len(history)}</div><div class="lbl">見つけた求人(累計)</div></div>
      <div class="bcard"><div class="num">{len(conf['sources'])}</div><div class="lbl">監視中のフィード</div></div>
    </div>
  </div>

  <div class="panel">
    <h2><span class="kicker">NEW</span>今朝の新着<span class="n">{len(new_items)}件</span></h2>
    <p class="sub">条件に合った新しい求人・求人関連の情報です。タップで元ページを開けます。</p>
    <ul>
{new_rows}
    </ul>
  </div>

  <div class="panel">
    <h2><span class="kicker">SEARCH</span>求人を探す(毎日1回この順で)</h2>
    <p class="sub">「{html.escape(conf['search_keywords'])}」×「{html.escape(conf['search_location'])}」の検索結果を直接開けます。新着ゼロの日もここを回すのが習慣に。</p>
    <div class="board-grid">
{boards}
    </div>
  </div>

  <div class="panel">
    <h2><span class="kicker">RULE</span>応募前の6つの関門</h2>
    <p class="sub">これを満たさない求人には応募しない。迷いを減らすための自分ルールです。</p>
    <div class="musts">
{musts}
    </div>
  </div>

  <div class="panel cond">
    監視条件 — 含むキーワード: <b>{html.escape(kw)}</b> / 除外: <b>{html.escape(ex)}</b><br>
    条件の変更は sources.yaml を編集してコミットしてください。
  </div>

  <footer>毎日7:30(JST)に自動更新 — GitHub Actions / Pages で稼働中</footer>
</div>
</body>
</html>
"""


def main() -> int:
    conf = load_config()
    state = load_state()
    seen = set(state["seen"])
    run_date = jst_now().strftime("%Y-%m-%d(%a) %H:%M")

    found, new_items = [], []
    for src in conf["sources"]:
        try:
            for item in fetch_items(src):
                link = item["link"]
                if not link or link in seen:
                    continue
                item["first_seen"] = run_date
                found.append(item)
                if matches(item["title"], conf):
                    new_items.append(item)
                seen.add(link)  # 条件外でも一度見たら既読(再表示しない)
        except Exception as exc:  # 1つのフィードが壊れても他は回す
            print(f"[warn] {src.get('name', src.get('url'))}: {exc}")

    new_items = new_items[: conf["max_items_per_run"]]
    print(f"新着 {len(new_items)} 件(履歴 {len(state['items'])} 件)")

    # 履歴を更新(新しい順に先頭へ、上限まで保持)
    history = list(reversed(new_items)) + state["items"]
    history = history[:MAX_HISTORY]

    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "index.html").write_text(
        build_html(new_items, history, run_date, conf), encoding="utf-8")

    state["seen"] = list(seen)[-5000:]
    state["items"] = history
    state["last_run"] = run_date
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
