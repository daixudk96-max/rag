# Compatibility Real-Validation Program — FILE-DRIVEN GOAL Prompt

```text
你现在在项目 E:\github\rag 中工作。

目标：执行 `changes/compatibility-real-validation-program/` 这套已冻结控制包，完成一次真实 credentialed donor validation；不要把验证工作扩展成新的功能开发。

【先调用 skills】
1. autod
2. compatibility-adapter-long-run-control
3. gitnexus-exploring
4. tdd-workflow

【强制读取顺序】
1. changes/compatibility-real-validation-program/00-MASTER.md
2. changes/compatibility-real-validation-program/01-ROADMAP.md
3. changes/compatibility-real-validation-program/02-INTERFACES.md
4. changes/compatibility-real-validation-program/03-CURRENT-PHASE.md

如果控制包引用父控制包约束，再读取被引用的父文件进行交叉确认。

【执行规则】
- 当前 phase 只能从 `03-CURRENT-PHASE.md` 读取，不要靠记忆假设
- 先验证 credential status；绝不打印 secret 本身
- 使用真实文档和真实 query；不要只跑默认 sample stub
- 如果发现代码 bug，先做 GitNexus impact analysis，再用 TDD 做最小修复
- 每刀结束后跑相关测试，并执行 `gitnexus analyze --embeddings --skills --verbose`
- 不允许重开 graph / multimodal 支线
- 不允许改变 donor priority 或 frozen provenance contracts

【停止条件】
- credentials missing
- 需要修改 frozen contracts
- 需要改变 donor priority
- 需要重开 paused branches
- GitNexus 风险 HIGH / CRITICAL
- 当前 phase exit criteria 已满足
- 信心 < 0.7

不要先做新功能。先读取控制包，再按当前 active phase 做真实验证。
```
