# 仓库协作规则（给 AI 助手）

本文件由仓库维护者指定。任何在本仓库里工作的 AI 助手，开工前先读完，并照做。

## 操作授权（重要）

用户授予了很高权限，但要求「先问再做」：

- 每个任务开始前，先用一两句话说明打算做什么、会动哪些文件，征得用户明确同意后再连续执行。
- 只读操作（读文件、`git status` / `log` / `diff`、搜索、查询）不需要询问。
- 用户已经明确提出的操作视为同意；同一任务内已获同意的步骤不必逐条重复确认。
- 任务获同意后，收尾的 `add` / `commit` / `push` 属于该任务的一部分，直接执行。
- 例外：`push --force`、删除文件、安装依赖、修改系统或全局配置等高危操作，即使任务已同意也要单独确认。

## 规则变更

- `AGENTS.md` 和协作规则**只由主设备修改**，且修改前必须征得用户明确同意。
- 同步设备只执行规则；有不同意见时，写进 `docs/sync-log-discussion.md` 或在会话里向用户提出，不要自行改规则。
- 主设备改完规则后，其他设备下次 `pull` 自动生效。

## 开始前

1. 先 `git pull`，确保基于远端最新的 `main` 工作。
2. 若本地有未提交的改动，先 `git commit`（或 `git stash`）再 pull，不要带着脏工作区硬拉。
3. 校验提交身份：`git config user.email` 必须是 `345989840+kuri-72@users.noreply.github.com`；不对就先改好再提交。

## 结束后

```bash
git add -A
git commit -m "这次改了什么"
git push
```

- 提交信息用一句中文概括这次改动，沿用仓库现有风格（`docs:` / `chore:` / `feat:` 前缀可选）。
- `push` 被拒（远端已有新提交）时：先 `git pull` 解决，再 `git push`。
- 没有改动：`git status` 干净就直接结束，不要制造空提交。
- 完成后在回复里给出本次提交的短 SHA 和 push 结果。

## 同步记录

统一记录在 `SYNC-TEST.md`，**不要按设备拆分文件**：

- **懒记录**：纯 `pull` 不单独提交；本设备下次真正提交时，把期间的 `pull` 和这次 `push` 一起写进去。
- 操作记录只保留最近 **30 条**，超出删最旧的；这是硬上限，不要突破。
- 每次提交顺手更新自己那台设备的「设备状态」行；接入新设备时在表里加一行。
- `sync/` 目录已废弃，不要再用。

## 禁止

- `git push --force`（任何形式，包括 `--force-with-lease`）
- 改写已有历史：`commit --amend`、交互式 `rebase`、`filter-branch`、`reset --hard` 后强推
- 提交 `.env`、密钥、证书、token、密码；提交信息里不要出现真实邮箱
- 未经用户同意删除或覆盖用户的文件

## 环境

各设备的路径与认证方式不同，**照下表对应本机，不要套用其他设备的配置**：

| 设备 | 主机名（用户名） | 仓库路径 | 认证方式 |
| --- | --- | --- | --- |
| 主设备 | `DESKTOP-EMH2SNR`（ROG） | `C:\Users\ROG\Desktop\Kuri_Git` | SSH `git@github.com:kuri-72/Kuri_Git.git`，私钥 `~/.ssh/id_ed25519_github`，push 无需登录 |
| 同步设备 1 | `DESKTOP-4JAFHLD`（NERV_Note_02） | `C:\Users\NERV_Note_02\Desktop\git` | HTTPS `https://github.com/kuri-72/Kuri_Git.git` + Git Credential Manager（已授权，无需重复登录） |
| 同步设备 2 | 待补充 | 待补充 | 待补充 |

其他通用说明：

- Git 可执行文件通常在 `C:\Program Files\Git\cmd\git.exe`，可能不在 PATH。
- 沙箱受限时 Git 的 schannel TLS 后端会报 `SEC_E_NO_CREDENTIALS`，改用 `git config http.sslBackend openssl`。
- Git Credential Manager 在受限沙箱下会崩溃（`0xE0434352`），HTTPS 认证环节需要完整权限；主设备改用 SSH 规避了这个问题。
- 不要给 Git 配置 `http.proxy`；网络偶发失败（`Connection was reset`）时重试即可。

## 交流

- 用中文回复。
