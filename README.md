# evals — 评测看板

站点：https://wangwu-30.github.io/evals/ （noindex）

**唯一来源是 `data/` 里的原始记录**；`site/` 由 `scripts/build_site.py` 生成，不进 git。push 到 main 后 GitHub Action 自动重建并发布。

## 目录
```
data/evals/<eval-id>/
  eval.json                 评测集定义（kind: matrix | metrics | summary）
  task.md / summary.md      题面（matrix）或脱敏汇总（summary）
  batches/<batch>.jsonl     一批运行的原始记录，每行一条（只追加，不改旧文件）
  batches/<batch>.meta.json 批次元数据：日期、环境、模型、花费、耗时、备注
```

## 加一批结果（最常用）
```bash
python3 scripts/ingest.py --eval daily-skill --batch 2026-10-12-macmini-final \
  --format prompt-eval --src <结果目录，结构 model/cond/rep.json> \
  --date 2026-10-12 --env "Mac mini · Codex/Claude CLI" --notes "一句话说明" [--wall-min 95] [--strip-output]
python3 scripts/build_site.py            # 本地预览 site/index.html
git add data && git commit -m "batch: ..." && git push
```
- 批次名已存在会报错：数据只追加；重跑就起新批次名。矩阵里每个模型自动取它最近一批。
- 打分口径：分数 = 通过检查数 / 检查数；每格 n≥5 时取截尾均值（去掉一个最高、一个最低），n<5 显示原始均值并标 *。
- 其他格式：`--format jsonl`（每行已有 model/cond/rep/score）、`--format teamrecall-score`（`--src a/score.json,b/score.json`）。

## 加一个评测集
新建 `data/evals/<id>/eval.json`：`id`、`title`、`kind`、`description`、`order`；matrix 另加 `checks`、`cond_labels`、`baseline`（默认 full）、`task_file`。
可选 `conclusion` 手写首页结论（不写则从数据自动生成）。summary 类加 `summary.md`、`date`、`badge`。

## 红线
- 不放保留题（holdout）、凭据、任何 hpo/公司材料。公司侧只放 summary 类脱敏汇总数字，`badge` 写“公司侧，脱敏汇总”。
- 提交前扫一遍：`rg -i -e 'gh[op]_' -e 'sk-' -e 'Bearer ' -e byted data`。
- 不编数字：花费只写记录自报的，并注明未核实。
