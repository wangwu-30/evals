# luna max eval：8 个合成批处理任务

| 字段 | 内容 |
|---|---|
| 来源 | Mac mini `~/codex-jobs/luna-max-eval/`。8 个任务（rename、rewrite、extract、inventory、convert、refactor、contracts、copywriting）全部用合成数据，从技能候选清单改编；检查器经过正反例自测 |
| 切分 | 没有切分；固定输入，3 个说明等级（L1 只给目标 / L2 加验收条件 / L3 再加步骤要求） |
| 版本 | 第一版，480 次运行 |
| 哪些结论依赖它 | [retros/2026-10-14-luna-max-eval.md](../retros/2026-10-14-luna-max-eval.md) |
