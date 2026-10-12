# daily-skill 评测公正性审计（2026-10-12）

对象：dev 题 `t1_coldstart`（Kenji）与 `checks.py`，数据为共享电脑上 3 档 MiniMax × 11 条件 × 5 次（165 条）。所有数字都来自 `data/evals/*/batches/` 里的记录，截尾均值 = 每格 5 次去掉一个最高、一个最低。

## 结论
1. **打分程序有 bug，已修正**：`checks.py` 在 09:41 被改成相对路径找 schema，共享电脑上该目录不存在，之后判分的 61/165 条记录的 B3/B5 一律因 `FileNotFoundError` 判失败（full 和 none 都受影响）。已改成可回退到 `/workspace/daily-skill-release/schema/`，用原输出重判分，新批次 `2026-10-12-box-rescored`（未重新调用模型）。修正后完整 skill 截尾均值：M2.5 0.56→0.61，Text-01 0.61（不变），abab6.5s 0.33（不变）；删 §2 的 M2.5 0.33→0.39、Text-01 0.17→0.22。Mac mini 批次里没有这个错误。
2. **题目是 skill 自己的作业**：6 项检查是 ACCEPTANCE.md 的 A2/A3/A4/A7s/B3/B5 原文；校准用的“合格输出”是 skill-coldstart-4（同一套 skill 的冷启动产物），人设 Kenji 也出自那次运行。
3. **“不加 skill = 0”主要是格式没给**：题面只说要 5 个文件，没给字段、枚举和 schema。15 条 none 记录的失败原因全是格式：`interests` 写成列表、`type: rss`（不在枚举里）、缺 `scheduler`、`schema_version` 写成 1.0/v1、index 缺必填字段。所以 0 分说明的是“不知道私有格式”，不是“不会做日报”。验证集 v1 加了“只给 JSON schema、不给 skill”的对照：M2.5 截尾 0.33（B3/B5 能过），Text-01 和 abab6.5s 仍为 0。
4. **只有一个人设、一个分支**：Kenji（东京、日语、安全）+ 本地仓库 + agent 模式。Actions 定时、API 模式、GitHub 托管这些分支完全没测到。
5. **部分检查可刷分、彼此相关**：
   - A7s 只查 4 个键存在、`next_run` 能解析且未过期，不查是否和时区一致；full 条件下三档都是 5/5。
   - A4 在 agent 模式下等价于 `llm.mode==agent` 且 A7s 通过，和 A7s 重复计分。
   - A2 只数个数（兴趣≥3、可信源≥5），不查兴趣与人设是否相符。
   - B5 只查 index 的 schema，不查和 data.json 一致。
   - 没有任何检查看内容：选了哪些条目、排序、去重、日文摘要质量都不计分。
6. **对厂商/模型的偏向**：判分全是程序，没有模型裁判，因此没有“裁判偏向自家模型”的问题。但有三处结构性偏向：①只测了 MiniMax 一家（box 上只有这个 key）；②skill 约 2.8 万 token 放进 system prompt、`max_tokens=20000`，长上下文、长输出的模型占便宜；③输出格式要求 `=== FILE ===` 分隔，解析只额外剥了 `<think>` 和代码块——格式小错会让 5 个文件全判失败（Text-01 none 有 2 次就是整份解析不了）。
7. **裁判不独立**：skill、题目、检查、校准输出都出自同一条智能体流水线，没有第二人复核。验证集答案键这次至少做了独立核对（见下），复核时发现我自己写错了一处 key（见“验证集”）。

## 已做
- **数据划分**：dev = Kenji 两版（单次作答、真实搭站），可随意调；validation = 下面两题；holdout = 1 题，只放在 `/workspace/prompt-eval/holdout/`，不进本仓库，使用记账在 `USAGE.log`。
- **验证集 v1（Amara）**：拉各斯、英文、金融科技/气候/开源硬件；来源含 github_releases、hf_papers、json_api；走 GitHub Actions + API 模式。用手写的合格输出校准 6/6。
- **验证集 v2（Lucía）**：输出格式是题面定义的 CSV，skill 里没有；考 skill 的规则：规范化 URL、事件 key、去重、mute 整词匹配、抓取窗口、同仓库只留最新 release。答案键用独立实现的 `canonical()` 核对，该实现复现了 SKILL §4.4 的 11 条非 IDNA 测试向量。故意改坏两行的输出会让对应检查失败。不加 skill 也能靠常识拿到格式、窗口、mute、去重分，比 dev 题公平。
- 首跑时发现答案键第 11 行的 key 没按 §2.3 把 `?`、`=` 替换成 `-`（正确值 `url:news.ycombinator.com/item-id-45100002`），修正后全部重判；holdout 同样修正。修正后没有任何模型通过 KEY。

## 首跑结果（截尾均值，n=5/格）
| 题 | 条件 | M2.5 | Text-01 | abab6.5s |
|---|---|---|---|---|
| dev Kenji（重判后） | 完整 skill | 0.61 | 0.61 | 0.33 |
| dev Kenji | 不加 skill | 0.00 | 0.00 | 0.00 |
| val v1 Amara | 完整 skill | 0.56 | 0.28 | 0.17 |
| val v1 Amara | 只给 schema | 0.33 | 0.00 | 0.00 |
| val v1 Amara | 不加 skill | 0.00 | 0.00 | 0.00 |
| val v2 Lucía | 完整 skill | 0.67 | 0.52 | 0.14 |
| val v2 Lucía | 不加 skill | 0.62 | 0.05 | 0.05 |

读法：
- 换人设、换分支后，Text-01 和 abab6.5s 的完整 skill 分数比 dev 掉了不少（0.61→0.28，0.33→0.17），M2.5 基本稳住。说明 dev 分数对 Kenji 有一部分过拟合。
- v2 里 M2.5 不加 skill 已有 0.62，skill 只多 0.05，而且范围很大（0.14–0.86），这个差距在波动之内。skill 带来的是 URL 规范化（CAN 0/5→4/5），代价是格式分和 mute 偶尔变差。
- Text-01 加 skill 后 mute 全错：把 Cryptography 也当 crypto 屏蔽了（整词匹配规则没执行），reason 还写成 `crypto`。
- v1 完整 skill 下 B3 15 次全失败：主要是 tags 没写成 slug（`african fintech`）、key 里留了 `?`/`=`、id 不是十六进制。

## 下一步
1. dev 题检查补内容维度（选条目、去重、mute），A4 和 A7s 去重计分。
2. 再加一家非 MiniMax 模型进 box 侧（Mac mini 那批已有 OpenAI/智谱，但条件不同，不能直接比）。
3. skill 里 §2.3 key 字符替换、tags slug、§2.4 整词匹配这三条，验证集上反复失败；如果为此改 skill，按规则必须在新题上复验，不能只看 v1/v2 回升。
4. 找第二个人复核 v1/v2 的答案键和检查。
