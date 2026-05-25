---
tags: [mobile, cryptocurrency, wallet, btc, eth, trc20, usdt, bip39, keystore, tronscan,
  etherscan, ocr, methodology, mobile_forensics]
tools: [strings, grep, sqlite3, tesseract, hashcat, requests, jq, exiftool, foremost]
category: mobile_forensics
difficulty: medium
source: kb_seed_2026-05-07
verified: false
related: [uninstalled_app_recovery.md, anti_forensics_and_misleading.md, pattern_wechat_db_decrypt.md]
---

# 虚拟货币取证 — 手机无直接信息时的破局

> **核心心法**：虚拟货币痕迹分布在 **链上 / 链下应用层 / 链外辅助层** 三个空间。
> 手机"没直接信息"通常指应用层被清。但**链外辅助层 + 物理残留 + 链上反查**几乎不可能全擦。
> **钱包地址只要被使用过一次，就永远以某种形式留在某处。**

## 0. 先决定要找什么

| 题型 | 真正要的 | 主要特征 |
|---|---|---|
| 钱包地址 | 公钥地址 | Base58 / Bech32 / 0x 前缀 |
| 助记词 | BIP39 12/24 词 | 标准 2048 词表内 |
| 私钥 | 64 hex / WIF | `5/K/L` 开头 |
| 交易哈希 | tx_hash | 64 hex |
| 转账金额/对端 | 链上反查 | 拿到地址后查 |
| 用了哪个交易所 | 域名/包名/流量 | 行为侧写 |

---

## 1. 主流币地址正则速查

```python
PATTERNS = {
  "BTC_legacy":  r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b",
  "BTC_segwit":  r"\bbc1[a-z0-9]{39,59}\b",
  "ETH/ERC20":   r"\b0x[a-fA-F0-9]{40}\b",
  "TRX/TRC20":   r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b",   # USDT-TRC20 主战场
  "Solana":      r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", # 易误报
  "TX_hash":     r"\b(?:0x)?[a-fA-F0-9]{64}\b",
  "BIP39_words": r"(?:\b[a-z]{3,8}\b\s+){11,23}\b[a-z]{3,8}\b",
  "WIF_priv":    r"\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b",
}
```

⚠️ 正则会误报，**必做 checksum 校验**：
- BTC: Base58Check（double SHA256 后 4 字节）
- ETH: EIP-55 大小写校验
- TRX: SHA256d 同 BTC
- BIP39: 候选 12 词必须全在标准 2048 词表

## 2. 三大破局方向

### A. 地址特征反扫（首选）

**扫描位置（按命中率）**：

| ★ | 位置 | 原因 |
|---|---|---|
| ★★★ | 剪贴板历史 | 用户**永远复制粘贴**地址 |
| ★★★ | IM 聊天数据库 | 转账给同伙必发地址 |
| ★★★ | 输入法词库（搜狗/百度） | 联想/记忆过的地址 |
| ★★★ | 浏览器历史/书签/Cookie | 访问交易所/区块链浏览器 |
| ★★ | 相册/截屏 (OCR) | 二维码截图、地址截图 |
| ★★ | 备忘录/便签/Keep | 用户存助记词常见位置 |
| ★★ | 邮件 | 交易所注册/提币确认 |
| ★★ | 通讯录备注 | 地址存联系人备注 |
| ★ | 文件管理器最近浏览 | PDF/截图/txt |
| ★ | 全镜像 strings | 兜底 |

**OCR 大杀器**：用户常用**二维码截图**或**纸条照片**存地址。`tesseract` / `paddleocr` 批扫相册。

### B. 钱包 app 残留（即使卸载也要查）

**主流移动钱包包名**：

| App | Android 包名 | iOS Bundle ID |
|---|---|---|
| imToken | `im.token.app` | `com.token.ethereum` |
| TronLink | `com.tronlink.app` | `com.tronlinkpro.app` |
| MetaMask | `io.metamask` | `io.metamask.MetaMask` |
| Trust Wallet | `com.wallet.crypto.trustapp` | `com.sixdays.trust` |
| Coinbase | `org.toshi` | `com.coinbase.Wallet` |
| OKX | `com.okinc.okex.gp` | 同名 |
| Binance | `com.binance.dev` | 同名 |
| TokenPocket | `vip.mytokenpocket` |  |
| Phantom (Solana) | `app.phantom` |  |
| SafePal | `io.safepal.wallet` |  |
| BitKeep / Bitget | `com.bitkeep.wallet` |  |

**卸载残留**：参考 `uninstalled_app_recovery.md` 九层（packages-backup.xml / usagestats / recent_images / `Android/data/{wallet_pkg}/`）。

**钱包数据关键文件**：
- imToken: `/data/data/im.token.app/files/wallet/*.json`
- MetaMask: `databases/MetaMaskRN-storage` (LevelDB)
- TronLink: `databases/wallet.db` (SQLite)
- Trust Wallet: `databases/Trust.db` 或 `files/wallets/*.json`
- 助记词通常**不存明文**，但 keystore JSON / 加密二进制在

**密码爆破**（找到 keystore 后）：
```bash
# Ethereum scrypt keystore
hashcat -m 15700 keystore.json wordlist.txt

# Bitcoin Core wallet.dat
hashcat -m 11300 wallet.dat wordlist.txt

# KeePass / 密码本
hashcat -m 28200 keepass.kdbx wordlist.txt
```

字典优先用：嫌疑人**其他密码**（聊天里、便签里、密码管理器导出、生日 + 名字常见组合）。

### C. 链外辅助 / 行为侧写

即使地址全擦，行为暴露目标币种和大致场景：

| 痕迹 | 推断 |
|---|---|
| 浏览过 `tronscan.org` | 用过 TRX |
| 浏览过 `etherscan.io` | 用过 ETH |
| 浏览过 `mempool.space` | 用过 BTC |
| 浏览过 `solscan.io` | 用过 SOL |
| 装过 `binance.com` / `okx.com` | 中心化交易所 |
| 微信/支付宝转账"虚拟币"备注 | 场外 OTC |
| 电费突然涨高 | 矿机 |
| 蚂蚁矿机说明书图片 | 挖矿 |
| GPU 持续高占用日志 (PC) | 挖矿/破解 |
| Tor / V2Ray / Clash 配置 | 访问交易所或暗网 |
| Google Authenticator / 2FA app | 交易所登录 2FA |

虚构币（如美亚杯 IDFC）无真实链上 API，只能从**钱包文件 + 聊天记录人工还原**。

---

## 3. 链上反查（拿到地址后）

| 链 | 浏览器 | 重点 |
|---|---|---|
| BTC | mempool.space, blockchain.com | 输入/输出地址、聚类 |
| ETH/ERC20 | etherscan.io | Internal Txns、ERC20 Token Txns |
| TRX/TRC20 | tronscan.org | TRC20 Transfers (USDT 主战场) |
| BSC | bscscan.com | 同 ETH |
| Solana | solscan.io | SPL Token transfers |
| Polygon | polygonscan.com |  |
| Arbitrum | arbiscan.io |  |

**关键技巧**：
- 一个地址 → 暴露**对端地址** → 对端再追 → 形成图谱
- **首次入金来源**：常是某个 CEX 提币地址（CEX 已知 = KYC 突破口）
- **最后流向**：汇入 Tornado Cash / Wasabi / ChipMixer → 注定追不下去，**重点抓混币前**
- **聚类启发式**：同一交易的多输入地址 = 大概率同一钱包
- 工具：Chainalysis / TRM Labs（付费）/ BitQuery / Etherscan API（免费）/ Breadcrumbs.app

**API 调用骨架**：
```python
import requests

# Tron USDT 转账历史
addr = "TXY..."
url  = f"https://apilist.tronscanapi.com/api/transfer?address={addr}&limit=50&token=USDT"
for tx in requests.get(url).json().get("data", []):
    print(tx["transaction_id"], tx["block_ts"], tx["from_address"], "->",
          tx["to_address"], tx["amount_str"])

# Etherscan ETH 交易
url = f"https://api.etherscan.io/api?module=account&action=txlist&address={addr}&apikey=YOUR_KEY"
```

---

## 4. 决策树

```
"嫌疑人有虚拟货币犯罪嫌疑，但手机里没直接信息"
   │
   ├─ Step 1: 主流币地址正则全盘 strings 扫
   │     └ 命中 → 链上查 → 完
   │
   ├─ Step 2: 钱包 app 残留（含已删除）
   │     ├ packages-backup.xml 看历史
   │     ├ /data/data/{wallet_pkg}/ 找 keystore
   │     ├ recent_images/ 看 UI 截图
   │     └ 命中 → 抓 keystore → 字典爆破 → 拿地址
   │
   ├─ Step 3: 链外辅助层
   │     ├ 剪贴板/输入法词库（必扫）
   │     ├ 聊天数据库 grep 地址正则
   │     ├ 相册 OCR 扫二维码/截图
   │     └ 浏览器历史/书签
   │
   ├─ Step 4: 行为侧写
   │     ├ 用过哪些链（浏览器域名）
   │     ├ 用过哪些交易所
   │     └ 缩小币种和场景
   │
   └─ Step 5: 跨设备 / 流量包
         ├ PC（Chrome 历史 + 桌面钱包）
         ├ 路由器 pcap（DNS 查询）
         ├ NAS / U 盘 → keystore 备份常在此
         └ 邮箱（提币通知 = 地址 + 金额 + 时间齐全）
```

---

## 5. 命令速查

```bash
# 全镜像扫所有币种地址
strings -e l {phone.img} | grep -aoE "(\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b|\bbc1[a-z0-9]{39,59}\b|\b0x[a-fA-F0-9]{40}\b|\bT[1-9A-HJ-NP-Za-km-z]{33}\b)" | sort -u

# USDT-TRC20 专扫（T 开头）
strings -e l {phone.img} | grep -oE "\bT[1-9A-HJ-NP-Za-km-z]{33}\b" | sort -u

# BIP39 12 词候选
strings -e l {phone.img} | grep -oE "([a-z]{3,8} ){11}[a-z]{3,8}" | sort -u

# 解密后微信库扫地址
sqlite3 EnMicroMsg_decrypted.db "SELECT content FROM message
 WHERE content GLOB '*T[1-9A-HJ-NP-Za-km-z][1-9A-HJ-NP-Za-km-z]*'
    OR content GLOB '*0x[0-9a-fA-F]*'
    OR content GLOB '*bc1*'"

# 相册 OCR 扫地址
for f in DCIM/**/*.jpg; do
  tesseract "$f" - 2>/dev/null \
   | grep -oE "(0x[a-fA-F0-9]{40}|T[1-9A-HJ-NP-Za-km-z]{33}|bc1[a-z0-9]{39,59})"
done

# 输入法词库
strings /data/data/com.sohu.inputmethod.sogou/files/usrdict/* | grep -oE "..."
strings /data/data/com.baidu.input/files/usrdict/* | grep -oE "..."

# 剪贴板（部分 ROM 持久化）
sqlite3 /data/system_ce/0/clipboard.db "SELECT * FROM clip"

# 浏览器历史里的链上浏览器/交易所
sqlite3 chrome/History "SELECT url, title, last_visit_time FROM urls
 WHERE url LIKE '%scan%' OR url LIKE '%mempool%' OR url LIKE '%binance%'
    OR url LIKE '%okx%' OR url LIKE '%coinbase%' OR url LIKE '%uniswap%'"

# Tron 链上 USDT 转账
curl -s "https://apilist.tronscanapi.com/api/transfer?address={ADDR}&limit=50&token=USDT" | jq

# Etherscan ETH 转账
curl -s "https://api.etherscan.io/api?module=account&action=tokentx&address={ADDR}&sort=desc&apikey=KEY" | jq

# BTC 浏览器
curl -s "https://mempool.space/api/address/{ADDR}/txs" | jq
```

---

## 6. 常见坑

- **地址正则误报**：Base58 集合和普通字符串重叠 → **必做 checksum 校验**
- **BIP39 词必须在标准 2048 词表**：用 `bip39_validator` 验
- **iOS 钱包数据多在 Keychain**：必须解密 backup（密码爆破或 Keychain 取）
- **混币后追不动**：Tornado Cash / Wasabi / ChipMixer 之后基本失败，**重点是混币前**
- **Tron USDT 是国内案件 90%+**：T 开头地址优先扫
- **场外 OTC 是关键证据**：法币转账（微信/支付宝）+ USDT 链上 = 双向铁证
- **冷钱包**：Ledger/Trezor 物理设备 → 抽屉、保险箱、笔记本电池仓
- **24 词助记词常拆成两半**：家里 12 + 公司 12，要多检材交叉
- **二维码会遮挡**：用户截图地址旁可能有"显示余额"二维码 → 扫 QR 解码可能拿到地址
- **链上时间戳 = UTC**：和手机本地时间对齐时记得加 ±8 小时
- **金额单位陷阱**：ETH/Wei 差 1e18，TRX/SUN 差 1e6，USDT-TRC20 差 1e6（不是 1e8！）
- **代币 vs 主币**：地址同，但要在浏览器切到 ERC20 / TRC20 / SPL 标签查代币转账

---

## 7. 实战证据链

最有说服力的"虚拟货币犯罪"证据组合：

```
1. 链外：剪贴板/聊天记录里有钱包地址 X        （地址出处）
2. 链外：相册截图含 X 的二维码               （视觉对应）
3. 链下：钱包 app keystore 解密后地址 = X    （所有权归属）
4. 链上：地址 X 收到/发出 USDT 与受害人金额一致 （资金流向）
5. 链外：微信里同一时间收到对应的法币转账    （OTC 闭环）
6. 跨设备：PC 端浏览器历史含 tronscan/X      （行为侧写）
```

任意 4 项互相印证 = 强证据链 = 入罪。
