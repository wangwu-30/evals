#!/usr/bin/env python3
"""data/ → site/（纯静态，可随时重建；site/ 不进 git）。"""
from zoneinfo import ZoneInfo
import json, pathlib, shutil, html, re, statistics as st, datetime
from collections import Counter
import viewer_data as vd
ROOT = pathlib.Path(__file__).resolve().parent.parent
D, OUT = ROOT / "data" / "evals", ROOT / "site"
REPO = "https://github.com/wangwu-30/evals"
esc = html.escape
VIEWERS = {}

def trimmed(xs):
    xs = sorted(xs)
    return st.mean(xs[1:-1]) if len(xs) >= 5 else None

def f2(x): return "–" if x is None else f"{x:.2f}"

CSS = """
:root{--bg:#f7f8fa;--card:#fff;--line:#e3e6ec;--fg:#1b1f27;--mut:#667085;--acc:#3557d4;--good:#1f8a5b;--bad:#c9372c}
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
.btn{display:inline-block;background:var(--acc);color:var(--bg);padding:8px 12px;border-radius:8px;margin:10px 0}
.cell small{display:block;white-space:normal;font-size:11px}.failure{font-size:12px;color:var(--bad)}.inc{background:#fff0bd;color:#805c00;padding:2px 5px;border-radius:4px}.source{color:#6b4fbb;background:#f3efff;padding:2px 4px;font-size:11px}.no-text{color:var(--mut)}th{white-space:normal;overflow-wrap:anywhere}
@media(max-width:599px){main{padding:12px}.scroll table{font-size:12px}td,th{padding:5px 4px}th{font-size:10px}.lead{font-size:14px}}
"""

def page(title, body, depth=0):
    up = "../" * depth
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{esc(title)} · 评测看板</title><style>{CSS}</style></head>
<body><main><header><h1><a href="{up}index.html">评测看板</a></h1><span class="mut">{esc(title) if depth else "评测集与结果 · 原始记录为唯一来源，页面可随时重建"}</span></header>{body}
<p class="mut" style="margin-top:40px;font-size:12px">站点是公开的，noindex 挡不住直接访问。<br>生成于 {datetime.datetime.now(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d %H:%M PT')} · <a href="{REPO}">源码与数据</a></p></main></body></html>"""

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
    ev = json.loads((ed / 'eval.json').read_text()); batches = []
    # Existing data files are append-only. Optional presentation metadata is new.
    if (ed / 'viewer.json').exists(): ev.update(json.loads((ed / 'viewer.json').read_text()))
    ev.setdefault('model_labels', {})
    for m in sorted((ed / "batches").glob("*.meta.json")) if (ed / "batches").exists() else []:
        meta = json.loads(m.read_text()); recs = [json.loads(l) for l in m.with_name(meta['id'] + '.jsonl').read_text().splitlines() if l.strip()]
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
            latest[r["model"]] = meta["id"]
    cells = {}
    for meta, recs in batches:
        for r in recs:
            if latest.get(r["model"]) != meta["id"]: continue
            xs = cells.setdefault((r["cond"], r["model"]), [])
            if r.get('score') is not None: xs.append(r['score'])
    models = sorted({m for _, m in cells}); conds = sorted({c for c, _ in cells}, key=cond_order)
    return models, conds, cells, latest

def val(xs):
    return (st.mean(xs), True)

def ablation(ev, models, conds, cells):
    base, rows = ev.get("baseline", "full"), []
    for c in conds:
        if not c.startswith("-"): continue
        ds = []
        for m in models:
            if cells.get((base, m)) and cells.get((c, m)): ds.append(val(cells[(base, m)])[0] - val(cells[(c, m)])[0])
        if ds: rows.append((c, st.mean(ds), ds))
    return sorted(rows, key=lambda r: -r[1])

def conclusion(ev, batches):
    if ev.get("conclusion"): return ev["conclusion"]
    if ev["kind"] == "matrix":
        models, conds, cells, _ = matrix(ev, batches)
        L = ev.get("cond_labels", {})
        fulls = [val(cells[("full", m)])[0] for m in models if cells.get(("full", m))]
        nones = [val(cells[("none", m)])[0] for m in models if cells.get(("none", m))]
        ab = ablation(ev, models, conds, cells)[:2]
        s = f"{len(models)} 个模型：完整 skill 均 {f2(st.mean(fulls)) if fulls else '–'}，不加 skill 均 {f2(st.mean(nones)) if nones else '–'}"
        if ab: s += "；几段之间分不出高下：" + "、".join(f"{L.get(c,c).replace('删 ','')}（删掉后平均变化 −{d:.2f}）" for c, d, _ in ab)
        return s
    if ev["kind"] == "metrics":
        meta, recs = batches[-1]; p = ev.get("primary")
        return "；".join(f"{r['cond']} 模式 {p} {r['metrics'].get(p)}" for r in recs) + "（待第二人复核）"
    return ""

def conclusion_html(ev, batches, prefix):
    text = esc(conclusion(ev, batches))
    if ev.get('conclusion') or not VIEWERS.get(ev['id'], {}).get('has_current_text'):
        return text
    names = {}
    for cond, name in ev.get('cond_labels', {}).items():
        names[esc(name)] = cond
        names[esc(name.replace('删 ', ''))] = cond
    if not names: return text
    pattern = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.sub(pattern, lambda m: f'<a href="{prefix}{esc(vd.url(ev,cond=names[m[0]]))}">{m[0]}</a>', text)

def eval_page(ev, batches):
    eid, L = ev["id"], ev.get("cond_labels", {}); b = []
    badge = f'<span class="badge co">{esc(ev["badge"])}</span>' if ev.get("badge") else ""
    if ev.get("split"): badge += f'<span class="badge">{esc(SPLIT_LABEL.get(ev["split"], ev["split"]))}</span>'
    b.append(f'<p class="lead">{conclusion_html(ev, batches, "../c/")}</p>{badge}')
    vi = VIEWERS.get(eid)
    if vi and not vi['has_current_text']: vi = None
    if vi:
        base = ev.get('baseline', 'full')
        other = ev.get('null_cond') or next((c for p in ev.get('presets', []) for c in p['conds'] if c != base), base)
        b.append(f'<a class="btn" href="../c/{esc(vd.url(ev))}">看回答原文：{esc(L.get(base, base))} 和 {esc(L.get(other, other))} 并排 →</a>')
        for preset in ev.get('presets', []):
            from urllib.parse import urlencode
            conds = list(dict.fromkeys([base] + preset['conds'][:2]))
            query = {'c': ','.join(conds)}
            if preset.get('item'): query['q'] = preset['item']
            b.append(f' <a href="../c/{eid}.html?{esc(urlencode(query))}">{esc(preset["label"])}</a>')
            if len(preset['conds']) > 2: b.append(f' 这组有 {len(preset["conds"])} 个条件，一次最多比 3 个，先带你看前 2 个')
    if ev["kind"] == "summary":
        b.append(f'<div class="card">{md(open(D/eid/"summary.md").read())}</div>')
        b.append('<p class="mut">只收录脱敏后的汇总数字；题目、运行记录和输出都只留在原机器上。</p>')
        return page(ev["title"], "".join(b), 1)
    if ev["kind"] == "matrix":
        models, conds, cells, latest = matrix(ev, batches)
        all_runs = [r['_viewer'] for meta, rs in batches for r in rs if latest.get(r['model']) == meta['id']]
        head = ''.join(f'<th>{esc(ev.get("model_labels", {}).get(m,m))}' + ('<br><span class="source">原文是补上的</span>' if any(r['text_source'] for r in all_runs if r['model'] == m) else '') + '</th>' for m in models)
        rows = []
        for c in conds:
            tds = []
            for m in models:
                xs = cells.get((c, m))
                if xs is None: tds.append('<td class="mut">–</td>'); continue
                v, ok = val(xs) if xs else (None, True)
                rs = [r for r in all_runs if r['model'] == m and r['cond'] == c]
                summary = vd.summarize(rs)
                available = vi and any(r['text'] for r in rs)
                number = f'<a title="看原文：{esc(L.get(c,c))} 和对照（{esc(L.get(ev.get("baseline","full"),"对照"))}）并排" href="../c/{esc(vd.url(ev,m,c))}">{f2(v)}</a>' if available else f'<span class="no-text" title="这批记录没有保存回答原文">{f2(v)}</span>'
                extra = f'<small>去掉最高最低 {f2(summary["trimmed_score"])}（参考）</small>'
                if summary['n_fail_model']: extra += f'<small class="failure">失败 {summary["n_fail_model"]} · ' + '、'.join(vd.FAIL_LABELS[k] for k in summary['failures'] if k.startswith('model_')) + '</small>'
                if summary['n_fail_infra']: extra += f'<small>基础设施失败 {summary["n_fail_infra"]}，不算进平均</small>'
                if summary['incomplete']: extra += '<span class="inc">数据不全</span>'
                tds.append(f'<td class="cell">{number}{extra}</td>')
            rows.append(f'<tr><td>{esc(L.get(c, c))}</td>{"".join(tds)}</tr>')
        b.append('<h2>条件 × 模型</h2><p class="mut">点任一格，看这一格的回答原文，和对照并排比。灰色的格子这批没存原文，点不进去。</p>')
        b.append(f'<div class="card scroll"><table><tr><th>条件</th>{head}</tr>{"".join(rows)}</table>'
                 f'<p class="failure">{esc(vd.failure_copy(vd.summarize(all_runs)))}</p><p class="mut" style="font-size:12px;margin:6px 0 0">分数 = 全部次数的平均：模型自己的失败算 0 分并入平均；基础设施失败不算进平均，单独写。每个模型取它最近一批的数据。</p></div>')
        ab = ablation(ev, models, conds, cells)
        if ab:
            mx = max(abs(d) for _, d, _ in ab) or 1
            ar = "".join(f'<tr><td>{esc(L.get(c,c))}</td><td>{"0.00" if abs(d)<0.005 else ("−" if d>0 else "+")+f"{abs(d):.2f}"}</td><td style="text-align:left;width:40%"><span class="bar {"" if d>=0 else "pos"}" style="width:{abs(d)/mx*100:.0f}%"></span></td>'
                         f'<td class="mut">{" / ".join(f"{x:+.2f}" for x in ds)}</td></tr>' for c, d, ds in ab)
            b.append(f'<h2>逐段删除：哪些段在起作用</h2><div class="card scroll"><table><tr><th>删掉的段</th><th>平均掉分</th><th></th><th>各模型（完整 − 删后）</th></tr>{ar}</table></div>')
        if ev.get("checks"):
            ck = "".join(f"<tr><td>{esc(ev.get('check_labels',{}).get(k,'检查'))}</td><td style='text-align:left;white-space:normal'>{esc(v)}</td></tr>" for k, v in ev["checks"].items())
            b.append(f'<h2>任务定义</h2><div class="card"><p>{esc(ev["description"])}</p><details><summary>{len(ev["checks"])} 项检查</summary><table>{ck}</table></details>')
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
    if recs and "cond" in recs[0]:
        rows = "".join(f'<tr><td>{esc(r["model"])}</td><td>{esc(ev.get("cond_labels",{}).get(r["cond"],"条件"))}</td><td>{int(r.get("rep",0))+1}</td><td>{f2(r["score"])}</td><td>{r.get("latency_s") or "–"}</td>'
                       f'<td style="text-align:left">{esc("、".join(ev.get("check_labels",{}).get(k,"检查没过") for k,v in (r.get("checks") or {}).items() if not str(v).startswith("PASS")))}</td><td>' + (f'<a href="../../c/{esc(vd.url(ev,r["model"],r["cond"],r["rep"],meta["id"]))}&amp;q={esc(r["_viewer"]["item"])}">原文</a>' if ev['id'] in VIEWERS and r['_viewer']['text'] else '这批记录没有保存回答原文') + '</td></tr>'
                       for r in sorted(recs, key=lambda r: (r["model"], cond_order(r["cond"]), str(r["rep"]))))
        b.append(f'<details class="card"><summary>逐条记录（{len(recs)}）</summary><div class="scroll"><table><tr><th>模型</th><th>条件</th><th>次</th><th>分</th><th>秒</th><th style="text-align:left">未过检查</th></tr>{rows}</table></div></details>')
    return page(meta["id"], "".join(b), 2)

SPLIT_LABEL = {"dev": "开发集", "validation": "验证集", "holdout": "保留集"}
def main():
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "e").mkdir(parents=True)
    (OUT / 'c').mkdir()
    shutil.copytree(ROOT / 'scripts' / 'viewer', OUT / 'assets', ignore=shutil.ignore_patterns('test_*', 'shell.html'))
    audit = dict(scanned=0, dropped_records=0, dropped=Counter(), backfills=[])
    split_path = ROOT / 'data/splits.json'
    splits = json.loads(split_path.read_text()) if split_path.exists() else {}
    holdout_ids = {x for sk in splits.get('skills', []) for x in sk.get('holdout', [])}
    evs = []
    for ed in sorted(p for p in D.iterdir() if (p / "eval.json").exists()):
        ev, batches = load(ed)
        if ev.get('split') == 'holdout': continue
        if vd.restricted_eval(ev):
            ev = dict(ev, kind='summary')
            batches = []
        else:
            batches, prompts = vd.prepare(ev, batches, ed, audit, holdout_ids)
            vi = vd.emit(ev, batches, ed, OUT, prompts, holdout_ids)
            if vi:
                VIEWERS[ev['id']] = vi
                shell = (ROOT / 'scripts/viewer/shell.html').read_text().replace('__TITLE__', esc(ev['title'])).replace('__ID__', esc(ev['id']))
                (OUT / 'c' / (ev['id']+'.html')).write_text(shell)
            # Only filtered normalized records are downloadable. Source artifacts,
            # prompts, split lists, and private receipts are never copied wholesale.
            for meta, records in batches:
                path = OUT / 'data/evals' / ev['id'] / 'batches' / (meta['id']+'.jsonl')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(''.join(json.dumps(r['_viewer'], ensure_ascii=False)+'\n' for r in records))
        evs.append((ev, batches))
        (OUT / "e" / f"{ev['id']}.html").write_text(eval_page(ev, batches))
        (OUT / "b" / ev["id"]).mkdir(parents=True, exist_ok=True)
        for meta, recs in batches: (OUT / "b" / ev["id"] / f"{meta['id']}.html").write_text(batch_page(ev, meta, recs))
    evs.sort(key=lambda e: e[0].get("order", 99))
    rows = []
    for ev, batches in evs:
        date = batches[-1][0]["date"] if batches else ev.get("date", "")
        badge = f'<span class="badge co">{esc(ev["badge"])}</span>' if ev.get("badge") else ""
        if ev.get("split"): badge += f'<span class="badge">{esc(SPLIT_LABEL.get(ev["split"], ev["split"]))}</span>'
        nb = f" · {len(batches)} 批" if batches else ""
        link = f' <a href="c/{esc(vd.url(ev))}">看原文</a>' if VIEWERS.get(ev['id'],{}).get('has_current_text') else ''
        rows.append(f'<div class="row"><a class="t" href="e/{ev["id"]}.html">{esc(ev["title"])}{badge}</a><span class="d">{date}{nb}</span><div class="c">{conclusion_html(ev, batches, "c/")}{link}</div></div>')
    extra = ""
    sp = ROOT / "data" / "splits.json"
    if sp.exists():
        S = json.load(open(sp)); li = []
        for sk in S["skills"]:
            parts = [f'<b>{esc(sk["skill"])}</b>']
            for k in ("dev", "validation", "holdout"):
                v = sk.get(k, [])
                parts.append(f'{SPLIT_LABEL[k]}：' + ("、".join(esc(x) for x in v) if k != "holdout" else f"{len(v)} 题（不公开）"))
            li.append("<li>" + " · ".join(parts) + "</li>")
        aud = "".join(f"<li>{esc(x)}</li>" for x in S.get("audit_summary", []))
        rules = "".join(f"<li>{esc(x)}</li>" for x in S.get("rules", []))
        extra = (f'<div class="card"><b>评测集划分</b><ul>{"".join(li)}</ul><b>优化规则</b><ul>{rules}</ul>'
                 f'<b>公正性审计（{esc(S.get("audit_date",""))}）</b><ul>{aud}</ul>'
                 f'<p class="mut">全文：<a href="{esc(S.get("audit_url",""))}">docs/fairness-audit</a></p></div>')
    (OUT / "index.html").write_text(page("首页", f'<div class="card" style="padding:0">{"".join(rows)}</div>' + extra))
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n"); (OUT / ".nojekyll").write_text("")
    print("built", len(evs), "evals →", OUT)
    vd.dump(OUT / 'build-audit.json', audit)
    print('secret_scan', json.dumps({k: v for k, v in audit.items() if k != 'backfills'}))
if __name__ == '__main__':
    main()
