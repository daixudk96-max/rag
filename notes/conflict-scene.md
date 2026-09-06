# W7 merge 冲突现场确认 (step 1 inspect)

## run / 等待点
- runId: run-ysup1dx3; 节点 merge = WAITING_SIGNAL; waitId wait-5rh5hqsy; kind merge-conflict; generation 0; signalKey sig-ea6c60cb-ffdc-44c5-9350-92d4061a6b45。
- 冲突会话: conflict-a0d1e477fa0e (status MERGE_CONFLICT)。

## 会话与 worktree
- merge worktree: E:\github\rag\.tdd-graph-merge\run-ysup1dx3 (含 CHERRY_PICK_HEAD)。
- baseSha = oursRef = integrationExpectedOld = a4b08ab5b2cff1621c674f3ee1bd131bd5d431e9。
- theirsRef = refs/tdd-graph/run-ysup1dx3/candidate-w1-lazy-heavy-imports-g0。
- appliedCandidates=[] remainingCandidates=[] (仅此一个 candidate)。
- integration ref 未被污染 (CAS fail-closed); 主仓 git status 无 cherry-pick 现场 (冲突只在 merge worktree)。

## 未合并文件 (git diff --diff-filter=U, 全部 AA = 双方新增)
1. .claude/tdd-guard/data/test.json — ours=base 快照版 (writeback proposal 测试状态), theirs=candidate worktree 运行时状态 (test_hotspot 收集错误报告)。决议依据: reviewer 警告 candidate 残留勿入仓。
2. llamaindex_runtime/__init__.py — ours=base 内的 worktree stub 标记文件 (5 行 "TDD worktree copy" marker); theirs=真懒加载 facade (89 行, importlib __getattr__ + TYPE_CHECKING)。**theirs 与主仓真身字节一致** (sha256 DA3559BCFAC9ECD6B2E488684DC221454D890C741F1B2CBA17F56049D0C7C39A, 对 .tmp/init_theirs.py 与主仓文件 Get-FileHash 比对 match=True)。
3. pytest.ini — ours=base 7 行版 (testpaths/python_files/classes/functions + markers, 比主仓多 3 行); theirs=candidate 版 (addopts = -v --tb=short, 丢 markers)。**主仓真身 = 4 行: [pytest]/pythonpath = ./markers/integration** — 两侧都不等于主仓, 决议 = 写主仓真身字节。

## 附带事实
- bundle.py 未冲突: cherry-pick 里 llamaindex_runtime/ingestion/* 均为干净 staged 新增 (A) — base 快照不含 ingestion 模块。
- 主仓 git ls-files: .claude/tdd-guard/data/test.json、pytest.ini、llamaindex_runtime/__init__.py、llamaindex_runtime/ingestion/bundle.py 均 untracked; llamaindex_runtime 下仅 10 个 tracked 文件 (本仓工作树大量 untracked 为常态)。
- 主仓工作树落地状态 (已验证): bundle.py = candidate + 协调器 2 处 mypy 修复; canonical 5/5; 联合探针 okf+entity 同进程 115/0; entity 966/0; 6 域 1287/0; okf full 5 预存/3386/31。
