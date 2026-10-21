# 仓库协作规则（给 AI 助手）

本文件是**唯一的规则来源**：`README.md` 给人看，`SYNC-TEST.md` 只记同步状态，`docs/` 放讨论存档。任何设备上的助手开工前读完本文件，照做。

## 授权：先问再做

- 任务开始前，用两三句话说清：做什么、为什么、动哪些文件，等用户明确同意再执行。
- 用户问「怎么样 / 行不行 / 好不好」时，先给判断和方案，再问是否执行；**提问不等于批准**。
- 只读操作（读文件、`git status` / `log` / `diff`、搜索）不用问。
- 已批准任务的收尾（`add` / `commit` / `push`）直接做，不逐条再问。
- 例外仍需单独确认：`push --force`、删除文件、安装依赖、改系统或全局配置。

## 改规则

- 任何设备都可以改本文件，但必须先得到用户明确同意。
- 改前 `git pull`；只改需要改的那一节，不要整节重写。
- 一次提交只做一类规则变更，提交信息以 `rules:` 开头；改完立刻 push，并在 `SYNC-TEST.md` 记一行。
- 对规则有异议：写进 `docs/sync-log-discussion.md` 或当场问用户，不要用改规则的方式解决争论。
- 规则变更历史用 `git log --grep "^rules:"` 查，不另建变更日志文件。

## 同步流程

- 开工：`git pull`，确保基于最新 `main`。
- 收工：`git add -A` → `git commit` → `git push`；提交信息一句中文，前缀 `docs:` / `feat:` / `fix:` / `chore:` / `rules:`。
- `push` 被拒：先 `git pull` 解决，再推；**禁止 force**。
- 没有改动就不提交，不要制造空提交。
- 提交身份：`user.email` 必须是 `345989840+kuri-72@users.noreply.github.com`。
- 多台可能同时改时，提交前再 `pull` 一次；冲突就地合并，不要覆盖对方改动。

## 记录（已冻结）

统一记在 `SYNC-TEST.md`：设备状态表 + 操作记录（最新在上，最多 30 条）。

- 懒记录：纯 `pull` 不单独提交，本设备下次提交时一起补。
- 每次提交顺手更新自己那台设备的「最近 pull / 最近 push」。
- **除非现有格式出现实际问题且用户同意，不要重新设计记录格式。**

## 禁止

- `git push --force`（任何形式）
- 改写历史：`commit --amend`、交互式 `rebase`、`filter-branch`、`reset --hard` 后强推
- 提交 `.env`、密钥、证书、token、密码；提交信息里不要出现真实邮箱
- 未经用户同意删除或覆盖用户文件

## 设备

| 设备 | 主机名（用户名） | 仓库路径 | 认证方式 |
| --- | --- | --- | --- |
| 主设备 | `DESKTOP-EMH2SNR`（ROG） | `C:\Users\ROG\Desktop\Kuri_Git` | SSH `git@github.com:kuri-72/Kuri_Git.git`，私钥 `~/.ssh/id_ed25519_github` |
| 同步设备 1 | `DESKTOP-4JAFHLD`（NERV_Note_02） | `C:\Users\NERV_Note_02\Desktop\git` | HTTPS + Git Credential Manager（已授权） |
| 同步设备 2 | 待补充 | 待补充 | 待补充 |

新设备加一行，退役设备删掉那一行。**每台只按自己那一行配置，不要照抄别的设备。**

其他环境说明：

- Git 通常在 `C:\Program Files\Git\cmd\git.exe`，可能不在 PATH。
- 受限沙箱下 schannel 报 `SEC_E_NO_CREDENTIALS` 时，设置 `http.sslBackend=openssl`。
- Git Credential Manager 在受限沙箱下会崩溃（`0xE0434352`）；主设备用 SSH 规避。
- 不要配 `http.proxy`；网络偶发 `Connection was reset`，重试即可。

## 交流

- 用中文；结论先行，简短，不重复用户已知的信息。
