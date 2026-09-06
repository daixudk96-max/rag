# W7 冲突处理者决策 (step 2 decide)

## 决定: 主会话直接修复 (不派 sub agent)

## 依据 (对照分层决策表)
- 文件数 3, 略超表中 "≤2 个文件" 档, 但三个冲突全部是 **字节级明确选择**, 无语义歧义、无需要重写的合并、无两版本意图冲突:
  1. llamaindex_runtime/__init__.py → 取 theirs: 已用 Get-FileHash 证明 candidate 版与主仓真身字节一致 (sha256 DA3559BCFAC9ECD6B2E488684DC221454D890C741F1B2CBA17F56049D0C7C39A); ours 只是 engine 注入 worktree 的 stub 标记。等价于 "保留主仓版"。
  2. pytest.ini → 写主仓真身 4 行 ([pytest]/pythonpath = ./markers/integration): ours (base 7 行) 与 theirs (candidate addopts 版丢 markers) 都不是主仓内容; reviewer 警告明确要求保 markers。等价于 "保留主仓版"。
  3. .claude/tdd-guard/data/test.json → 取 ours (base 快照版): reviewer 警告 candidate 运行时残留勿入仓; ours 决议使该文件相对 base 零变化。
- 主会话上下文最全: 本会话亲历 wave spec (bundle.py 懒加载 5 编辑)、candidate sha d8c9fdbd、落地后 mypy 修复轮、reviewer 三警告 — sub agent 无任何信息优势, 反而要重建上下文。
- 核心原则 "解决冲突的人必须继承上下文, 优先主会话直接修复" 直接适用。

## 修复指令 (给 step 3 的自己, 也满足 sub-agent bundle 的等价纪律)
- 只改 3 个冲突文件; git add 不 git commit (cherry-pick 续行由 runMergeContinue 执行);
- 修完主会话自查 git diff --diff-filter=U 归零 + 与主仓真身哈希复核, 再进 resume 步。
