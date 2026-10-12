#!/usr/bin/env python3
"""把一批运行结果追加进 data/（只追加，不改旧批次）。
用法:
  python3 scripts/ingest.py --eval daily-skill --batch 2026-10-12-macmini-final \
      --format prompt-eval --src ~/prompt-eval/results/single --date 2026-10-12 \
      --env "Mac mini" --notes "最终报告"
格式:
  prompt-eval      目录 <model>/<cond>/<rep>.json（runner.py / runner_cli.py 产物）
  jsonl            已是标准记录的 jsonl（每行至少 model, cond, rep, score）
  teamrecall-score 一个或多个 score.json（--src 可用逗号分隔），每个记一条 metrics 记录
"""
import argparse, json, os, sys, glob, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent

def score_of(checks):
    if not checks: return None
    return round(sum(1 for v in checks.values() if str(v).startswith("PASS")) / len(checks), 4)

def tokens(u):
    u = u or {}
    if "usage" in u and isinstance(u["usage"], dict): u = u["usage"]
    tin = u.get("input_tokens", u.get("prompt_tokens"))
    tout = u.get("output_tokens", u.get("completion_tokens"))
    return tin, tout

def from_prompt_eval(src, eval_id, batch):
    out = []
    for f in sorted(glob.glob(os.path.join(src, "*", "*", "*.json"))):
        p = pathlib.Path(f)
        try: d = json.load(open(f))
        except Exception as e:
            print("跳过（解析失败）", f, e, file=sys.stderr); continue
        model = d.get("agent") or d.get("model") or p.parent.parent.name
        tin, tout = tokens(d.get("usage"))
        cost = (d.get("usage") or {}).get("cost_usd") if isinstance(d.get("usage"), dict) else None
        out.append({"eval": eval_id, "batch": batch, "model": model, "cond": d.get("cond", p.parent.name),
                    "rep": d.get("rep", int(p.stem) if p.stem.isdigit() else p.stem), "mode": d.get("mode", "single"),
                    "score": score_of(d.get("checks")), "checks": d.get("checks"), "latency_s": d.get("latency_s"),
                    "tokens_in": tin, "tokens_out": tout, "cost_usd": cost, "rc": d.get("rc"),
                    "source_file": str(p.relative_to(src)), "raw": d})
    return out

def from_teamrecall(srcs, eval_id, batch):
    out = []
    for s in srcs:
        d = json.load(open(s))["summary"]
        m = d["memories"]; f = m.get("first_occurrence_new", {})
        out.append({"eval": eval_id, "batch": batch, "model": "teamrecall@" + d.get("teamrecall_commit", "?")[:7],
                    "cond": d["mode"], "rep": 0, "score": f.get("precision_judged"),
                    "metrics": {"首次即晋升·严格准确率": f.get("precision_judged"), "首次即晋升·宽松准确率": f.get("provisional_precision"),
                                "记忆总数": m.get("total"), "判为噪声": m.get("judged_noise"),
                                "agent_task MRR": d["agent_task"].get("mrr"), "agent_task recall@5": d["agent_task"]["recall_at"].get("5"),
                                "agent_task 阻止重复": d["agent_task"].get("prevented"), "review_time MRR": d["review_time"].get("mrr"),
                                "LLM 调用": d["counts"].get("llm_calls"), "事件": d["counts"].get("events")},
                    "window": d.get("window"), "raw": d})
    return out

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--eval", required=True); a.add_argument("--batch", required=True)
    a.add_argument("--format", required=True, choices=["prompt-eval", "jsonl", "teamrecall-score"])
    a.add_argument("--src", required=True); a.add_argument("--date", required=True)
    a.add_argument("--env", default=""); a.add_argument("--notes", default="")
    a.add_argument("--wall-min", type=float, default=None, help="墙钟耗时（分钟），不填则不显示")
    a.add_argument("--strip-output", action="store_true", help="丢掉 raw.output 以减小体积")
    x = a.parse_args()
    ed = ROOT / "data" / "evals" / x.eval
    if not (ed / "eval.json").exists(): sys.exit(f"先建 {ed}/eval.json（见 README）")
    bd = ed / "batches"; bd.mkdir(exist_ok=True)
    if (bd / f"{x.batch}.jsonl").exists(): sys.exit("批次已存在：数据只追加，换一个 --batch 名")
    src = os.path.expanduser(x.src)
    if x.format == "prompt-eval": recs = from_prompt_eval(src, x.eval, x.batch)
    elif x.format == "teamrecall-score": recs = from_teamrecall([os.path.expanduser(s) for s in src.split(",")], x.eval, x.batch)
    else: recs = [json.loads(l) | {"eval": x.eval, "batch": x.batch} for l in open(src) if l.strip()]
    if x.strip_output:
        for r in recs: (r.get("raw") or {}).pop("output", None)
    if not recs: sys.exit("没有找到记录")
    with open(bd / f"{x.batch}.jsonl", "w") as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    costs = [r["cost_usd"] for r in recs if r.get("cost_usd") is not None]
    meta = {"id": x.batch, "date": x.date, "env": x.env, "notes": x.notes, "format": x.format,
            "models": sorted({r["model"] for r in recs}), "n_records": len(recs),
            "cost_usd_reported": round(sum(costs), 2) if costs else None, "cost_records": len(costs),
            "sum_latency_min": round(sum(r.get("latency_s") or 0 for r in recs) / 60, 1) or None,
            "wall_min": x.wall_min}
    json.dump(meta, open(bd / f"{x.batch}.meta.json", "w"), ensure_ascii=False, indent=1)
    print(f"写入 {len(recs)} 条 → {bd}/{x.batch}.jsonl；接着运行 python3 scripts/build_site.py")
main()
