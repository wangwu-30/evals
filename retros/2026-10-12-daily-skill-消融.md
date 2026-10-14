# daily-skill 逐节删除 复盘（2026-10-12）

数据集：[dev Kenji](../datasets/daily-skill-dev-kenji.md)、[validation](../datasets/daily-skill-validation.md)。原报告：`prompt-eval/REPORT-macmini.md`、[公正性审计](../docs/fairness-audit-2026-10-12.md)。

- **假设**：SKILL.md 每一节都有贡献，可以用逐节删除找出起作用的节。
- **结果**：MiniMax 3 档 × 11 条件 × 5 次，codex/claude 只跑部分条件。删 §2、§4 下降最大。“不加 skill”三档都是 0。换人设到验证集后，Text-01 完整 skill 从 0.61 掉到 0.28。v2 里 M2.5 不加 skill 0.62、加 skill 0.67，差距在波动内。
- **哪些做法被证明不靠谱**：
  - 只用 1 道 dev 题，又拿同一题的重复次数当样本。
  - 截尾均值把 0 分藏掉：claude default full 截尾 0.44，单次范围 0.00–1.00。
  - 结论随 n 翻转：M2.5 删 §7 在 n=3 时 0.94，n=5 截尾 0.78。
  - 检查照抄 ACCEPTANCE，人设来自同一条流水线。
  - “不加 skill=0”其实是题面没给格式。
  - 判分 bug 让 61/165 条被误判失败。
  - 只测了 MiniMax，box 和 Mac mini 的条件不一样，结果不可比。
- **对方法论的修改**：主指标改为全部 run 均值，失败单列；按任务簇做配对比较并给区间；判分程序改动要有回归测试；题面要写清楚输出格式，测的才是 skill 而不是格式猜测；新题必须与 skill 不同源。
