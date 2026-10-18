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
  --date 2026-10-12 --env "Mac mini · Codex/Claude CLI" --notes "一句话说明" [--wall-min 95]
python3 scripts/build_site.py            # 本地预览 site/index.html
git add data && git commit -m "batch: ..." && git push
```
- 批次名已存在会报错：数据只追加；重跑就起新批次名。矩阵里每个模型自动取它最近一批。
- 打分口径：主数字是全部运行的平均；模型失败按 0 分并入，基础设施失败不计入任何平均，两类失败单列。去掉最高最低的平均只作参考。新批次保留回答原文并写 `fail_type`，不再支持 `--strip-output`。
- 其他格式：`--format jsonl`（每行已有 model/cond/rep/score）、`--format teamrecall-score`（`--src a/score.json,b/score.json`）。

## 加一个评测集
新建 `data/evals/<id>/eval.json`：`id`、`title`、`kind`、`description`、`order`；matrix 另加 `checks`、`cond_labels`、`baseline`（默认 full）、`task_file`。
可选 `conclusion` 手写首页结论（不写则从数据自动生成）。summary 类加 `summary.md`、`date`、`badge`。

## 红线
- 不放保留题（holdout）、凭据、任何 hpo/公司材料。公司侧只放 summary 类脱敏汇总数字，`badge` 写“公司侧，脱敏汇总”。
- 提交前扫一遍：`rg -i -e 'gh[op]_' -e 'sk-' -e 'Bearer ' -e byted data`。
- 不编数字：花费只写记录自报的，并注明未核实。

## 评测集划分（dev / validation / holdout）
| 划分 | 用途 | 位置 |
|---|---|---|
| 开发集 dev | 随便调，看逐段删除、改 skill | 本仓库，`split: dev`（如 daily-skill 的 Kenji 题） |
| 验证集 validation | 每次优化都要在这里过一遍 | 本仓库，`split: validation` |
| 保留集 holdout | 每个大版本只用一次 | **不进本仓库**，只在共享电脑 `/workspace/prompt-eval/holdout/`；这里只显示题数 |

划分清单在 `data/splits.json`，首页据此显示。

## 优化规则（硬性）
1. **一次优化只有同时满足两条才算数：dev 分数上升，且 validation 不下降。** 比较用全部运行的平均（模型失败算 0 分；基础设施失败排除），同模型、同条件；去掉最高最低的平均只作参考。差值小于该格的单次波动范围时记为“持平”，不算上升。
2. **holdout 每次使用都要记账**：在 `/workspace/prompt-eval/holdout/USAGE.log` 追加一行（时间、skill 版本或提交、模型、谁、为什么）。每个大版本最多用一次；看到 holdout 结果后改了 skill，就不能再拿同一份 holdout 验证，得出新题。
3. **看过 validation 失败后再改的 skill，必须在新题上复验**：那批 validation 题对这次改动已经“泄题”，要么新增一道 validation 题，要么在 holdout 上（记账）确认，才算通过。
4. 新题入库前要用一份已知合格的输出校准（检查全过），再用一份故意改坏的输出确认检查会失败。
5. 打分程序改动后，旧批次一律重判分、起新批次（不改旧文件），并在批次备注写明原因。

## 原文对比

详情页的「看回答原文」按钮、得分格子、首页「看原文」和批次页「原文」链接进入同一模型、同一道题的比较页。最多三个条件；手机合并成一列。使用说明、数据边界和当前验收缺口见 [docs/viewer.md](docs/viewer.md)。站点是公开的，noindex 挡不住直接访问。首次发布原文须由负责人确认。
