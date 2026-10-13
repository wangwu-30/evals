# ljg-explain 基准

这套脚本扩展现有 `data/evals` 矩阵约定，并参考 `~/prompt-eval/runner_cli.py` 的单次 CLI 调用方式；没有搭建新评测框架。读取锁定的 MIT skill，完整复制保留 LICENSE 和来源。

题库共 20 题：公开的 dev 8 / validation 8，以及仓库之外的 holdout 4。各切分均为两类模型 × 无 skill、完整 skill、7 个 `##` 段逐段删除 × 5 次重复。holdout 的完整矩阵在读取其结果前固定，一次运行存档，删除条件只作确认、不用于挑选或修改skill。每次独立启动 CLI，把 16 道公开题放在一次请求中；holdout 另一次请求。每个问题均只有自然请求，被测模型看不到 oracle、参考输出或 rubric。各题使用稳定知识；题面不要求当前信息或医疗/财务决策。

每个回答 10 个二元检查等权计分：6 项语义由盲裁判判定并给正文引句，4 项规则检查。裁判看题目、正确性 oracle 和回答，看不到模型/条件/skill。最终所有输出统一由 `codex:gpt-6.1-sol` 判定。原计划 GLM/OpenAI 互裁，但 GLM 互裁试跑的单批自报费用推算完整矩阵会超出预算，因此改为共同裁判；已完成的同一 OpenAI 裁判记录复用，其余互裁试跑只留作审计并计费。OpenAI 候选和裁判名义上属于同一厂商，不能声称厂商独立；GLM 候选与裁判名义上不同厂商。GLM 的返回 `modelUsage` 名称记入原始记录，不能把 Claude CLI 名称当成 Anthropic 模型，也不能把模型自称或路由名称当作实际后端身份的独立证明。

开发集和验证集每轮分别把 8 道题的 80 项检查等权平均。每格的 n=5 指五轮整批重复，矩阵主分数去掉一次最高和一次最低后取均值。不可把 40 个回答或 400 项检查当成 40/400 次独立重复。CI 对题目和轮次两个维度做有放回抽样，所有抽样仍使用截尾均值；删除条件与 full 配对使用相同抽样索引。公開 28 个删除比较（7段×2模型×2切分）另给 Bonferroni 同时区间。5 轮和 8 题很少，区间只是这份有限题库下的近似不确定性。

校准样本由本次执行的 Codex 代理逐条预标注，包含12条构造样本和10条跨领域真实输出，模式分别是 `agent-manual-style-seeded` / `agent-manual-style-observed`，**没有声称独立人工复核**。相似样本的初轮批量校准出现串用内容；因此最终校准逐样本隔离，使用原有标注，原失败调用仍保留计费。真实输出的标注未查看裁判标签，逐项理由与时间戳公开。新增题均用预先写的已知合格输出和故意改坏输出过两位裁判，判定结果可审计。

完整正文的封装异常不当成零分：不完整括号、未转义内引号或字面反斜线只按固定任务键边界恢复，保留原响应和解析方式，不改正文。实际漏答的题全10项失败，原漏答保留，不重新采样；这是交付失败分数，报告单列漏答数量。裁判传输/引句不合格时仅对不合格项重新隔离判定，原调用不删除且计费；合法低分不会重判。保留集作答每个请求只尝试一次，启动前冻结 skill、题库、检查脚本哈希与设计，并追加 `USAGE.log`，不据其结果改 skill 或重生成答案。

费用表保留输入、输出、缓存 token 和 CLI 自报 USD。GLM 路由返回 `costBasis=unknown`；这些金额不是核验账单。Codex CLI 不返回 USD，标记未知而非 $0。`--reported-cap-usd` 对可观测的自报费用进行预留和封顶，无法证明含订阅/路由结算的总账单。所有探测、废弃校准、裁判修复调用均计入账本。

## 复现统计（不再次调用模型）

原始公开运行归档见 `data/evals/explain/artifacts/public/`，保留集仍需原执行机的私有目录。将公开归档作为一个 run-dir 下的 `public/` 子目录，执行：

```sh
python3 scripts/explain/replay.py --private-dir ~/codex-jobs/explain-eval/holdout --out-dir /tmp/explain-replay
python3 scripts/explain/test_explain.py
python3 scripts/build_site.py
```

若未获得私有目录，公开 dev/validation 统计仍可完整复现；holdout 只记题数，不提交题面/答案/判分输出。`replay.py` 会提示本次是否包含保留集。

私有调用仅导出不含题目/答案/分数的usage/费用数字收据；没有私有目录时仍可复现全批次的自报费用小计。统计使用Python标准库。可选效果图使用Matplotlib：安装后运行`python3 scripts/explain/plot.py --summary /tmp/explain-replay/summary.json --output /tmp/explain-effects.png`，图中只包含公开切分。

## 补做交互与分词器分析（无模型调用）

`followup.py` 从公开原始生成/裁判记录重算，不依赖已发布分数。模型内差值使用原配对题目/轮次重抽样；交互共享题目抽样、两模型独立抽轮次，同一模型的删除/full 配对。以零假设为中心的双侧 bootstrap 检验分别对公开 28 个模型内检验、14 个交互检验做 Holm 校正。dev/validation 分开报告；私有 holdout 只参考，不进入公开文件或相关分析。

实际路由分词器版本未知。GPT 精确请求名无法被 `tiktoken 0.12.0` 解析，使用显式 `o200k_base` 探索代理；GLM 使用官方公开仓库的锁定分词器参考。两列均不证明路由实际编码。数值只计 skill 原始正文，不含聊天模板/系统提示。完整、各删段变体和各独立段落分别计数；相关分析使用 full−变体的有效减少量，另归一化到全文比例。7 段 × 2 切分、Pearson/Spearman、两个解释变量共 8 个探索检验做 Holm 校正，双侧精确排列 5,040 次；Spearman 对 12 位小数相等的效果视作并列，避免浮点误差制造次序。

安装环境、下载锁定分词器并重算公开报告：

```sh
python3 -m venv /tmp/explain-followup-env
/tmp/explain-followup-env/bin/python -m pip install -r scripts/explain/requirements-followup.txt
mkdir -p /tmp/explain-followup
curl -fL https://huggingface.co/zai-org/GLM-5.3-Flash/resolve/91b69215804f2d2036a8867f6ce44848e278dcda/tokenizer.json -o /tmp/explain-followup/tokenizer.json
/tmp/explain-followup-env/bin/python scripts/explain/followup.py --glm-tokenizer /tmp/explain-followup/tokenizer.json --output /tmp/explain-followup/public.json
/tmp/explain-followup-env/bin/python scripts/explain/test_followup.py
python3 scripts/explain/replay.py --private-dir /tmp/explain-no-holdout --out-dir /tmp/explain-replay
python3 scripts/explain/write_report.py --summary /tmp/explain-replay/summary.json --run-dir data/evals/explain/artifacts --private-dir /tmp/explain-no-holdout --followup /tmp/explain-followup/public.json --output /tmp/explain-followup/REPORT-public.md --pr https://github.com/wangwu-30/evals/pull/1
```

首次计数会下载 OpenAI 公开编码；GLM 文件及 OpenAI 合并表均由 `tokenizer-provenance.json` 的 SHA256 校验，后续可离线复算。此文件保留官方依据、精确版本和未知项。新公开统计追加在 `data/evals/explain/batches/2026-10-13-explain-followup-v1.json`，不覆盖原运行数据。重算输出到临时目录，勿覆盖归档批次。

原执行机如需保留集参考，在 `followup.py` 追加 `--private-dir ~/codex-jobs/explain-eval/holdout --private-output ~/codex-jobs/explain-eval/followup-holdout.json`，在 `write_report.py` 追加 `--include-holdout --followup-private ~/codex-jobs/explain-eval/followup-holdout.json` 并将报告输出到仓库外。保留集输出路径若位于仓库内，脚本拒绝写入。本轮无新增生成/裁判调用，新增评测调用费用 $0；执行代理会话费用未获账单。

## 新鲜复跑（会调用模型且计费）

不要对已经使用的保留集再执行。原批次的命令与冻结哈希见 protocol.json / 私有 freeze.json。

```sh
python3 scripts/explain/run.py calibrate --run-dir /tmp/explain-new
python3 scripts/explain/run.py references --run-dir /tmp/explain-new
python3 scripts/explain/run.py generate --run-dir /tmp/explain-new --workers 8
python3 scripts/explain/run.py judge --run-dir /tmp/explain-new --workers 8
```

原始数据追加到现有 dashboard 的命令见报告；批次文件不可覆盖，重判应生成新批次。
