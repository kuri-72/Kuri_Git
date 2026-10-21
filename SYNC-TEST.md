# 同步测试（SYNC-TEST）

用来验证三台设备能否通过 GitHub 仓库互通。

- 发起设备：DESKTOP-EMH2SNR（ROG，主设备）
- 发起时间：2026-10-22 04:12:54（Asia/Shanghai）
- 校验码：**KURI-8BE3-4913**

## 在另一台设备上验证

1. 打开仓库目录；如果这台设备还没有仓库，先克隆：

   ```bash
   git clone https://github.com/kuri-72/Kuri_Git.git
   ```

2. 更新到最新：

   ```bash
   git pull
   ```

3. 打开本文件，确认上面的「校验码」是 `KURI-8BE3-4913`。

## 反向验证（可选，用来确认那台设备也能推）

把下面这行改成你的设备名，然后提交并推送，让主设备再 pull 一次：

- 已读设备：（在这里填设备名）

```bash
git add -A
git commit -m "test: 另一台设备已读到同步测试"
git push
```

## 测试完可以删

确认双向都能同步后，本文件可以删掉，提交说明写 `chore: 删除同步测试文件`。
