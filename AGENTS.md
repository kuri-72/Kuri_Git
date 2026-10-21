# 仓库协作规则（给 AI 助手）

**本文件已冻结（2026-10-22）。除非用户明确要求，不要修改本文件、不要新增流程文件、不要重新设计记录方式。**

用户的原话：这条规则是为了让 AI 少折腾，而不是让仓库多出一堆关于流程的提交。

## 先问再做

- 任务开始前，用一两句话说清做什么、动哪些文件，等用户同意再执行。
- 只读操作（读文件、`git status` / `log` / `diff`、搜索）不用问。
- 已批准任务的收尾（`add` / `commit` / `push`）直接做。
- 例外仍需单独确认：`push --force`、删除文件、改系统或全局配置。

## 流程

- 开工先 `git pull`。
- 收工 `git add -A` → `git commit -m "..."` → `git push`。
- `push` 被拒：先 `git pull` 再推，**禁止 force**。
- 没有改动就不提交，不要制造空提交。
- 提交信息一句中文，前缀 `docs:` / `feat:` / `fix:` / `chore:` / `rules:`。
- 提交身份：`user.email` 必须是 `345989840+kuri-72@users.noreply.github.com`。

## 禁止

- `git push --force`（任何形式）
- 改写历史：`commit --amend`、交互式 `rebase`、`filter-branch`、`reset --hard` 后强推
- 提交密钥、证书、token、`.env`；提交信息不得出现真实邮箱
- 未经用户同意删除或覆盖用户文件
- **主动提议重构流程、扩充规则、增加记录制度**——用户没问就不要提

## 记录（可选，不强制）

- 想记就记在 `SYNC-TEST.md`，只保留最近 30 条，最新在上。
- **不要为记录单独产生提交**；不记也完全没问题。
- 只读操作不记。

## 设备

| 设备 | 主机名（用户名） | 仓库路径 | 认证方式 |
| --- | --- | --- | --- |
| 主设备 | `DESKTOP-EMH2SNR`（ROG） | `C:\Users\ROG\Desktop\Kuri_Git` | SSH `git@github.com:kuri-72/Kuri_Git.git`，私钥 `~/.ssh/id_ed25519_github` |
| 同步设备 1 | `DESKTOP-4JAFHLD`（NERV_Note_02） | `C:\Users\NERV_Note_02\Desktop\git` | HTTPS + Git Credential Manager（已授权） |
| 同步设备 2 | 待补充 | 待补充 | 待补充 |

新设备加一行，退役设备删掉那一行。**每台只按自己那一行配置。**

环境说明：

- Git 通常在 `C:\Program Files\Git\cmd\git.exe`，可能不在 PATH。
- 受限沙箱下 schannel 报 `SEC_E_NO_CREDENTIALS` 时，设置 `http.sslBackend=openssl`。
- Git Credential Manager 在受限沙箱下会崩溃（`0xE0434352`）；主设备用 SSH 规避。
- 不要配 `http.proxy`；网络偶发 `Connection was reset`，重试即可。

## 交流

- 用中文；结论先行，简短，不重复用户已知的信息。
