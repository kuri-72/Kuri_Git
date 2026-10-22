# 讨论：同步记录怎么记（已结案）

**结论（2026-10-22）**：记录制度已取消。`SYNC-TEST.md` 已删除，日常不再记录 pull / push，也不要为记账额外提交。

判断同步是否正常，三条命令就够：

```bash
git status -sb                    # 应显示 ## main...origin/main，无 ahead / behind
git rev-parse HEAD origin/main    # 两个 SHA 相同 = 本地与远端完全一致
git log --format="%ae"            # 邮箱应全部是 noreply 地址
```

本文件只作历史存档，不再追加。规则一律以 `AGENTS.md` 为准。
