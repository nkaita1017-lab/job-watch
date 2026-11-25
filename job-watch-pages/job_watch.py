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

環境変数:
  なし(通知先がLINEでなくなったため、Secretsは不要です)
"""

import datetime
import html
import json
import pathlib
import sys

import yaml
import feedparser

ROOT = pathlib.Path(__file__).parent
STATE_PATH = ROOT / "state.json"
CONFIG_PATH = ROOT / "sources.yaml"
SITE_DIR = ROOT / "site"
USER_AGENT = "job-watch-pages/1.0"
MAX_HISTORY = 200  # ページに残す過去アイテムの上限


def jst_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        conf = yaml.safe_load(f) or {}
    conf.setdefault("include_keywords", [])
    conf.setdefault("exclude_keywords", [])
    conf.setdefault("max_items_per_run", 20)
    conf.setdefault("sources", [])
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


def build_html(new_items: list, history: list, run_date: str, conf: dict) -> str:
    """新着確認ページ(単一HTML)を組み立てる"""

    def row(it: dict, is_new: bool) -> str:
        badge = '<span class="badge new">NEW</span>' if is_new else ""
        return f"""      <li class="item{' fresh' if is_new else ''}">
        <a href="{html.escape(it['link'])}" target="_blank" rel="noopener">{html.escape(it['title'])}</a>
        <div class="meta"><span class="src">{html.escape(it['source'])}</span>{badge}
          <span class="date">{html.escape(it.get('first_seen', run_date))}</span></div>
      </li>"""

    new_rows = "\n".join(row(it, True) for it in new_items) or \
        '      <li class="item none">新着はありません — 監視は正常に動いています</li>'
    past_rows = "\n".join(
        row(it, it.get("first_seen", "") >= run_date) for it in history)

    sources_list = ", ".join(s.get("name", "") for s in conf["sources"])
    kw = "、".join(conf["include_keywords"]) or "(指定なし)"
    ex = "、".join(conf["exclude_keywords"]) or "(指定なし)"

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>求人ウォッチ — {html.escape(run_date)}</title>
<style>
:root{{--bg:#151A23;--panel:#1F2733;--line:#33404F;--ink:#ECF1F4;--mut:#8A97A8;
--teal:#4FC3B8;--amber:#F2B155}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--ink);
font-family:"Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans JP",sans-serif;
line-height:1.8;font-size:14.5px;padding:32px 18px 80px}}
.wrap{{max-width:760px;margin:0 auto}}
h1{{font-size:22px;letter-spacing:.03em}}
h1 .dot{{color:var(--teal)}}
.sub{{color:var(--mut);font-size:12.5px;margin:4px 0 20px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:18px}}
h2{{font-size:15.5px;margin-bottom:10px}}
h2 .n{{color:var(--teal);font-weight:700;margin-left:6px}}
ul{{list-style:none}}
.item{{padding:10px 4px;border-bottom:1px solid var(--line);font-size:13.5px}}
.item:last-child{{border-bottom:none}}
.item a{{color:var(--ink);text-decoration:none}}
.item a:hover{{color:var(--teal)}}
.item.fresh a{{color:#BDEDE7;font-weight:700}}
.item.none{{color:var(--mut)}}
.meta{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11px;color:var(--mut);margin-top:2px}}
.src{{background:rgba(79,195,184,.12);color:var(--teal);border-radius:999px;padding:0 9px}}
.badge.new{{background:var(--amber);color:#10151D;font-weight:700;border-radius:999px;padding:0 8px}}
.date{{margin-left:auto}}
.cond{{font-size:12px;color:var(--mut)}}
.cond b{{color:var(--ink);font-weight:600}}
footer{{text-align:center;color:var(--mut);font-size:11px;margin-top:24px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>求人ウォッチ<span class="dot">.</span>daily</h1>
  <p class="sub">最終チェック: {html.escape(run_date)} / 監視中: {html.escape(sources_list)}</p>

  <div class="panel">
    <h2>今朝の新着<span class="n">{len(new_items)}件</span></h2>
    <ul>
{new_rows}
    </ul>
  </div>

  <div class="panel">
    <h2>これまでに見つけた求人<span class="n">{len(history)}件</span></h2>
    <ul>
{past_rows}
    </ul>
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
                seen.add(link)  # 条件外でも一度見たら既読(再通知しない)
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
