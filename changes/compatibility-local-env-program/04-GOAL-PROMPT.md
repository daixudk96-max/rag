# Compatibility Local Env Program — FILE-DRIVEN GOAL Prompt

```text
你现在在项目 E:\github\rag 中工作。

目标：执行 `changes/compatibility-local-env-program/` 这套已冻结控制包，把当前真实验证链路从 session-scoped secret 注入迁移到本地 `.env` 配置方式；不要把这件事扩展成新的 donor 策略讨论。

【先调用 skills】
1. autod
2. compatibility-adapter-long-run-control
3. gitnexus-exploring
4. tdd-workflow

【强制读取顺序】
1. changes/compatibility-local-env-program/00-MASTER.md
2. changes/compatibility-local-env-program/01-ROADMAP.md
3. changes/compatibility-local-env-program/02-INTERFACES.md
4. changes/compatibility-local-env-program/03-CURRENT-PHASE.md

如果控制包引用父控制包约束，再读取被引用的父文件进行交叉确认。

【执行规则】
- 当前 phase 只能从 `03-CURRENT-PHASE.md` 读取，不要靠记忆假设
- 真实 secret 绝不打印、绝不提交
- tracked template 可以更新；真实 `.env` 必须保持本地-only
- GitNexus impact analysis 在任何符号编辑前必做
- TDD：先 RED，再 GREEN，再回归
- 每刀结束后跑相关测试，并执行 `gitnexus analyze --embeddings --skills --verbose`
- 不允许重开 graph / multimodal 支线
- 不允许改变 donor priority 或 frozen provenance contracts

【停止条件】
- 需要修改 frozen contracts
- 需要改变 donor priority
- 需要重开 paused branches
- GitNexus 风险 HIGH / CRITICAL
- 当前 phase exit criteria 已满足
- 信心 < 0.7

不要先跑真实验证。先读取控制包，再按当前 active phase 完成本地 `.env` 迁移工作。
```
