# 同步体检（SYNC-TEST）

这个文件只负责**验证**各设备是否真的通过 GitHub 互通，不再记录日常操作。

- 日常操作记录分散在 [`sync/`](sync/) 目录，**每台设备一个文件**，互不干扰。
- 基准校验码：**KURI-8BE3-4913**（2026-10-22 首次互通时生成，用来排查「仓库是不是串了」）

## 设备一览

| 设备 | 主机名 | 记录文件 |
| --- | --- | --- |
| 主设备（主场） | `DESKTOP-EMH2SNR`（ROG） | `sync/DESKTOP-EMH2SNR.md`（待建） |
| 同步设备 1 | `DESKTOP-4JAFHLD`（NERV_Note_02） | [`sync/DESKTOP-4JAFHLD.md`](sync/DESKTOP-4JAFHLD.md) |
| 同步设备 2 | 待补充 | 待补充 |

> 这张表只在**接入新设备**时改一次，日常 pull / push 不要动它。

## 怎么判断同步是正常的

```bash
git status -sb                    # 应显示 ## main...origin/main，且没有 ahead / behind
git rev-parse HEAD origin/main    # 两个 SHA 完全相同 = 本地与远端完全一致
git log --format="%ae"            # 邮箱应全部是 noreply 地址
```

三条都符合，就不需要再做别的事——**不需要为了"确认同步"去写任何文件**。

## 校验码怎么用

如果本文件顶部不是 `KURI-8BE3-4913`，说明仓库被换过或拉错了地方，先确认 `git remote -v` 指向 `kuri-72/Kuri_Git`。
