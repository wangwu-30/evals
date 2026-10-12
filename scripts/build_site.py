#!/usr/bin/env python3
"""data/ → site/（纯静态，可随时重建；site/ 不进 git）。"""
import json, pathlib, shutil, html, re, statistics as st, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
D, OUT = ROOT / "data" / "evals", ROOT / "site"
REPO = "https://github.com/wangwu-30/evals"
esc = html.escape

def trimmed(xs):
    xs = sorted(xs)
    return st.mean(xs[1:-1]) if len(xs) >= 5 else None

def f2(x): return "–" if x is None else f"{x:.2f}"

CSS = """
:root{--bg:#0b0d12;--card:#141821;--line:#232a36;--fg:#e6e9ef;--mut:#8b94a7;--acc:#7aa2ff;--good:#3fb97f;--bad:#e5534b}
@media (prefers-color-scheme: light){:root{--bg:#f7f8fa;--card:#fff;--line:#e3e6ec;--fg:#1b1f27;--mut:#667085;--acc:#3557d4}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,"PingFang SC","Noto Sans SC",system-ui,sans-serif}
main{max-width:1080px;margin:0 auto;padding:20px 16px 60px}a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header{display:flex;align-items:baseline;gap:12px;margin-bottom:14px}header h1{font-size:18px;margin:0}header .mut{font-size:12px}
.mut{color:var(--mut)}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.row{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:10px 14px;border-bottom:1px solid var(--line)}.row:last-child{border:0}
.row .t{font-weight:600}.row .c{grid-column:1/3;color:var(--fg);opacity:.9}.row .d{color:var(--mut);font-size:12px}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:99px;border:1px solid var(--line);color:var(--mut);margin-left:6px;font-weight:400}
.badge.co{border-color:#b7791f;color:#d69e2e}
h2{font-size:15px;margin:22px 0 6px}.lead{font-size:15px;font-weight:600;margin:6px 0 2px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--mut);font-weight:500;font-size:12px}
.scroll{overflow-x:auto}.cell small{display:none;color:var(--mut);font-size:11px}#raw:checked~.card .cell small{display:block}
.lt5{opacity:.75}.lt5::after{content:"*";color:var(--mut)}
details>summary{cursor:pointer;color:var(--mut);font-size:13px}details[open]>summary{margin-bottom:6px}
.bar{display:inline-block;height:8px;border-radius:4px;background:var(--bad);vertical-align:middle}.bar.pos{background:var(--good)}
pre{white-space:pre-wrap;font-size:12px;background:var(--bg);padding:10px;border-radius:8px;max-height:420px;overflow:auto}
label.tog{font-size:12px;color:var(--mut);cursor:pointer;user-select:none}
"""

def page(title, body, depth=0):
    up = "../" * depth
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{esc(title)} · 评测看板</title><style>{CSS}</style></head>
<body><main><header><h1><a href="{up}index.html">评测看板</a></h1><span class="mut">{esc(title) if depth else "评测集与结果 · 原始记录为唯一来源，页面可随时重建"}</span></header>{body}
<p class="mut" style="margin-top:40px;font-size:12px">生成于 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · <a href="{REPO}">源码与数据</a></p></main></body></html>"""

def md(s):
    out, tbl = [], []
    def flush():
        if not tbl: return
        rows = [r for r in tbl if not re.match(r"^\|[-| :]+\|$", r)]
        h = "".join(f"<th>{esc(c.strip())}</th>" for c in rows[0].strip("|").split("|"))
        b = "".join("<tr>" + "".join(f"<td>{esc(c.strip())}</td>" for c in r.strip("|").split("|")) + "</tr>" for r in rows[1:])
        out.append(f'<div class="scroll"><table><tr>{h}</tr>{b}</table></div>'); tbl.clear()
    ul = False
    for line in s.splitlines():
        if line.startswith("|"): tbl.append(line); continue
        flush()
        if line.startswith("- "):
            if not ul: out.append("<ul>"); ul = True
            out.append(f"<li>{esc(line[2:])}</li>"); continue
        if ul: out.append("</ul>"); ul = False
        if line.strip(): out.append(f"<p>{esc(line)}</p>")
    flush()
    if ul: out.append("</ul>")
    return "".join(out)

def load(ed):
    ev = json.load(open(ed / "eval.json")); batches = []
    for m in sorted((ed / "batches").glob("*.meta.json")) if (ed / "batches").exists() else []:
        meta = json.load(open(m)); recs = [json.loads(l) for l in open(m.with_name(meta["id"] + ".jsonl")) if l.strip()]
        batches.append((meta, recs))
    batches.sort(key=lambda b: (b[0]["date"], b[0]["id"]))
    return ev, batches

def cond_order(c):
    if c == "none": return (0, "")
    if c == "full": return (1, "")
    return (2, c.zfill(3) if c[1:].isdigit() else "z" + c)

def matrix(ev, batches):
    latest = {}
    for meta, recs in batches:
        for r in recs:
            if r.get("score") is not None: latest[r["model"]] = meta["id"]
    cells = {}
    for meta, recs in batches:
        for r in recs:
            if r.get("score") is None or latest.get(r["model"]) != meta["id"]: continue
            cells.setdefault((r["cond"], r["model"]), []).append(r["score"])
    models = sorted({m for _, m in cells}); conds = sorted({c for c, _ in cells}, key=cond_order)
    return models, conds, cells, latest

def val(xs):  # 主数字：n≥5 用截尾均值，否则原始均值（标 *）
    t = trimmed(xs); return (t, True) if t is not None else (st.mean(xs), False)

def ablation(ev, models, conds, cells):
    base, rows = ev.get("baseline", "full"), []
    for c in conds:
        if not c.startswith("-"): continue
        ds = []
        for m in models:
            if (base, m) in cells and (c, m) in cells: ds.append(val(cells[(base, m)])[0] - val(cells[(c, m)])[0])
        if ds: rows.append((c, st.mean(ds), ds))
    return sorted(rows, key=lambda r: -r[1])

def conclusion(ev, batches):
    if ev.get("conclusion"): return ev["conclusion"]
    if ev["kind"] == "matrix":
        models, conds, cells, _ = matrix(ev, batches)
        L = ev.get("cond_labels", {})
        fulls = [val(cells[("full", m)])[0] for m in models if ("full", m) in cells]
        nones = [val(cells[("none", m)])[0] for m in models if ("none", m) in cells]
        ab = ablation(ev, models, conds, cells)[:2]
        s = f"{len(models)} 个模型：完整 skill 均 {f2(st.mean(fulls)) if fulls else '–'}，不加 skill 均 {f2(st.mean(nones)) if nones else '–'}"
        if ab: s += "；最关键的段：" + "、".join(f"{L.get(c,c).replace('删 ','')}（删掉 −{d:.2f}）" for c, d, _ in ab)
        return s
    if ev["kind"] == "metrics":
        meta, recs = batches[-1]; p = ev.get("primary")
        return "；".join(f"{r['cond']} 模式 {p} {r['metrics'].get(p)}" for r in recs) + "（待第二人复核）"
    return ""

def eval_page(ev, batches):
    eid, L = ev["id"], ev.get("cond_labels", {}); b = []
    badge = f'<span class="badge co">{esc(ev["badge"])}</span>' if ev.get("badge") else ""
    b.append(f'<p class="lead">{esc(conclusion(ev, batches))}</p>{badge}')
    if ev["kind"] == "summary":
        b.append(f'<div class="card">{md(open(D/eid/"summary.md").read())}</div>')
        b.append('<p class="mut">只收录脱敏后的汇总数字；题目、运行记录和输出都只留在原机器上。</p>')
        return page(ev["title"], "".join(b), 1)
    if ev["kind"] == "matrix":
        models, conds, cells, latest = matrix(ev, batches)
        head = "".join(f"<th>{esc(m)}</th>" for m in models)
        rows = []
        for c in conds:
            tds = []
            for m in models:
                xs = cells.get((c, m))
                if not xs: tds.append('<td class="mut">–</td>'); continue
                v, ok = val(xs)
                tds.append(f'<td class="cell"><span class="{"" if ok else "lt5"}">{v:.2f}</span><small>均 {st.mean(xs):.2f} · n={len(xs)} · {min(xs):.2f}–{max(xs):.2f}</small></td>')
            rows.append(f'<tr><td>{esc(L.get(c, c))}</td>{"".join(tds)}</tr>')
        b.append('<h2>条件 × 模型</h2><input type="checkbox" id="raw" hidden><label class="tog" for="raw">▸ 显示原始均值 / n / 范围</label>')
        b.append(f'<div class="card scroll"><table><tr><th>条件</th>{head}</tr>{"".join(rows)}</table>'
                 f'<p class="mut" style="font-size:12px;margin:6px 0 0">分数 = 去掉一个最高、一个最低后取平均（n≥5）；带 * 为 n&lt;5，显示原始均值。每个模型取它最近一批的数据。</p></div>')
        ab = ablation(ev, models, conds, cells)
        if ab:
            mx = max(abs(d) for _, d, _ in ab) or 1
            ar = "".join(f'<tr><td>{esc(L.get(c,c))}</td><td>{"0.00" if abs(d)<0.005 else ("−" if d>0 else "+")+f"{abs(d):.2f}"}</td><td style="text-align:left;width:40%"><span class="bar {"" if d>=0 else "pos"}" style="width:{abs(d)/mx*100:.0f}%"></span></td>'
                         f'<td class="mut">{" / ".join(f"{x:+.2f}" for x in ds)}</td></tr>' for c, d, ds in ab)
            b.append(f'<h2>逐段删除：哪些段在起作用</h2><div class="card scroll"><table><tr><th>删掉的段</th><th>平均掉分</th><th></th><th>各模型（完整 − 删后）</th></tr>{ar}</table></div>')
        if ev.get("checks"):
            ck = "".join(f"<tr><td>{esc(k)}</td><td style='text-align:left;white-space:normal'>{esc(v)}</td></tr>" for k, v in ev["checks"].items())
            b.append(f'<h2>任务定义</h2><div class="card"><p>{esc(ev["description"])}</p><details><summary>6 项检查</summary><table>{ck}</table></details>')
            tf = ev.get("task_file")
            if tf and (D / eid / tf).exists(): b.append(f'<details><summary>题面</summary><pre>{esc(open(D/eid/tf).read())}</pre></details>')
            b.append("</div>")
    if ev["kind"] == "metrics":
        meta, recs = batches[-1]; keys = list(recs[0]["metrics"])
        tr = "".join(f"<tr><td>{esc(k)}</td>" + "".join(f"<td>{r['metrics'].get(k)}</td>" for r in recs) + "</tr>" for k in keys)
        b.append(f'<h2>最近一批</h2><div class="card scroll"><table><tr><th>指标</th>{"".join(f"<th>{esc(r["cond"])}</th>" for r in recs)}</tr>{tr}</table></div>')
        b.append(f'<h2>任务定义</h2><div class="card"><p>{esc(ev["description"])}</p></div>')
    hist = "".join(f'<tr><td><a href="../b/{eid}/{m["id"]}.html">{esc(m["id"])}</a></td><td>{m["date"]}</td><td style="text-align:left">{esc(", ".join(m["models"]))}</td><td>{m["n_records"]}</td>'
                   f'<td><a href="../data/evals/{eid}/batches/{m["id"]}.jsonl">jsonl</a></td></tr>' for m, _ in reversed(batches))
    b.append(f'<h2>批次历史</h2><div class="card scroll"><table><tr><th>批次</th><th>日期</th><th style="text-align:left">模型</th><th>记录</th><th>原始</th></tr>{hist}</table></div>')
    return page(ev["title"], "".join(b), 1)

def batch_page(ev, meta, recs):
    cost = f'${meta["cost_usd_reported"]}（{meta["cost_records"]} 条记录自报，未核实）' if meta.get("cost_usd_reported") is not None else "未记录"
    t = []
    if meta.get("wall_min"): t.append(f'墙钟 {meta["wall_min"]} 分钟')
    if meta.get("sum_latency_min"): t.append(f'单次耗时合计 {meta["sum_latency_min"]} 分钟')
    info = [("评测", f'<a href="../../e/{ev["id"]}.html">{esc(ev["title"])}</a>'), ("日期", meta["date"]), ("环境", esc(meta.get("env", ""))),
            ("模型", esc(", ".join(meta["models"]))), ("记录数", meta["n_records"]), ("花费", esc(cost)), ("时间", "；".join(t) or "未记录"),
            ("原始记录", f'<a href="../../data/evals/{ev["id"]}/batches/{meta["id"]}.jsonl">{meta["id"]}.jsonl</a>')]
    b = [f'<p class="lead">{esc(meta.get("notes",""))}</p><div class="card"><table>' + "".join(f"<tr><td>{k}</td><td style='text-align:left;white-space:normal'>{v}</td></tr>" for k, v in info) + "</table></div>"]
    if recs and "cond" in recs[0] and "checks" in recs[0]:
        rows = "".join(f'<tr><td>{esc(r["model"])}</td><td>{esc(r["cond"])}</td><td>{r["rep"]}</td><td>{f2(r["score"])}</td><td>{r.get("latency_s") or "–"}</td>'
                       f'<td style="text-align:left">{esc(" ".join(k for k,v in (r.get("checks") or {}).items() if not str(v).startswith("PASS")))}</td></tr>'
                       for r in sorted(recs, key=lambda r: (r["model"], cond_order(r["cond"]), str(r["rep"]))))
        b.append(f'<details class="card"><summary>逐条记录（{len(recs)}）</summary><div class="scroll"><table><tr><th>模型</th><th>条件</th><th>次</th><th>分</th><th>秒</th><th style="text-align:left">未过检查</th></tr>{rows}</table></div></details>')
    return page(meta["id"], "".join(b), 2)

def main():
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "e").mkdir(parents=True); shutil.copytree(ROOT / "data", OUT / "data")
    evs = []
    for ed in sorted(p for p in D.iterdir() if (p / "eval.json").exists()):
        ev, batches = load(ed); evs.append((ev, batches))
        (OUT / "e" / f"{ev['id']}.html").write_text(eval_page(ev, batches))
        (OUT / "b" / ev["id"]).mkdir(parents=True, exist_ok=True)
        for meta, recs in batches: (OUT / "b" / ev["id"] / f"{meta['id']}.html").write_text(batch_page(ev, meta, recs))
    evs.sort(key=lambda e: e[0].get("order", 99))
    rows = []
    for ev, batches in evs:
        date = batches[-1][0]["date"] if batches else ev.get("date", "")
        badge = f'<span class="badge co">{esc(ev["badge"])}</span>' if ev.get("badge") else ""
        nb = f" · {len(batches)} 批" if batches else ""
        rows.append(f'<div class="row"><a class="t" href="e/{ev["id"]}.html">{esc(ev["title"])}{badge}</a><span class="d">{date}{nb}</span><div class="c">{esc(conclusion(ev, batches))}</div></div>')
    (OUT / "index.html").write_text(page("首页", f'<div class="card" style="padding:0">{"".join(rows)}</div>'))
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n"); (OUT / ".nojekyll").write_text("")
    print("built", len(evs), "evals →", OUT)
main()
