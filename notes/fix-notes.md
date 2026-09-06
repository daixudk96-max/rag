# W7 冲突修复记录 (step 3 fix)

## 修复动作 (merge worktree E:\github\rag\.tdd-graph-merge\run-ysup1dx3)
1. llamaindex_runtime/__init__.py → git checkout --theirs (candidate 版 = 主仓真身)。
2. pytest.ini → Copy-Item 主仓 E:\github\rag\pytest.ini 覆写 (pythonpath + markers 4 行真身)。
3. .claude/tdd-guard/data/test.json → git checkout --ours (base 快照版, candidate 运行时残留不流入)。
4. git add 三文件; **未 commit** (硬规则遵守, CHERRY_PICK_HEAD 保留)。

## 修复后验证 (全部亲算)
- git diff --diff-filter=U --name-only → 空 (未合并归零)。
- git status 头: "You are currently cherry-picking commit d8c9fdb. (all conflicts fixed: run git cherry-pick --continue)"; CHERRY_PICK_HEAD 存在于真实 worktree gitdir E:\github\rag\.git\worktrees\run-ysup1dx3\CHERRY_PICK_HEAD (worktree .git 是文件指针, 首查 $wt\.git 路径为误)。
- index blob 复核: git cat-file -p :0:llamaindex_runtime/__init__.py sha256 = DA3559BCFAC9ECD6B2E488684DC221454D890C741F1B2CBA17F56049D0C7C39A = candidate blob = 主仓真身 (autocrlf 使 worktree 磁盘文件 CRLF 化致 Get-FileHash 表面不等, 但 add 时 clean filter 归一 LF, **commit blob 才是权威**, 已证相等)。
- pytest.ini index blob = [pytest]/pythonpath = ./markers/integration (主仓语义内容, LF 归一)。
- 附注: stage3 比对报错 "path ... not at stage 3" 属预期 (add 后仅剩 stage0), 空文件 sha E3B0C442 假警报已排除。

## 教训 (新增, 记 wave-plan)
- git worktree 的 CHERRY_PICK_HEAD 在 <main>\.git\worktrees\<name>\ 下, 不在 $wt\.git\ (那里是指针文件)。
- autocrlf 环境下冲突解析验证必须看 index blob (cat-file :0:), 不能只看磁盘文件哈希 (smudge CRLF 化会假阳性)。
