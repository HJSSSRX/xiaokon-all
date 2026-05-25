---
tags: [reverse_engineering, aes, xor, password, pe, radare2, s_box, crypto]
tools: [radare2, python, openssl, strings]
category: stego_crypto
difficulty: hard
source: fic2026
date: 2026-05-05
verified: true
---

# Title: AES + XOR Mask 密码校验逆向

## Problem
Windows PE 程序要求输入密码，密码经 AES S-box 查表 + XOR 变换后与固定字节序列比较。

## Solution Steps

1. 定位密码比较点
   ```bash
   r2 -A exe
   afl | grep -i dialog    # 找 UI 处理函数
   pdf @fcn.xxx            # 找 strncmp / memcmp 调用
   ```
   → 关键特征: `strncmp(s1, s2, 16)` 其中 s1 是固定 16 字节

2. 提取固定比较值
   ```
   # 从反汇编中读 mov dword [s1], 0xXXXXXXXX 序列
   # 拼出 16 字节 ciphertext
   ```

3. 识别 AES S-box
   ```bash
   # 搜索 AES S-box 特征值 (0x63, 0x7c, 0x77, 0x7b 开头的 256 字节表)
   px 256 @addr
   ```

4. 分析 XOR mask
   ```python
   # 常见 mask 生成模式
   mask = bytes([((0x7f + 3*i) & 0xff) for i in range(16)])
   ```

5. 反向解密
   ```python
   import subprocess
   ct = bytes.fromhex('afb977ac242ad60cf42461ad72ca5149')
   open('/tmp/ct.bin','wb').write(ct)
   for key_hex in ['0123456789abcdef0123456789abcdef']:
       p = subprocess.run(['openssl','enc','-aes-128-ecb','-d','-nopad',
                          '-K',key_hex,'-in','/tmp/ct.bin'],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
       pt = p.stdout
       result = bytes([b ^ ((0x7f + 3*i) & 0xff) for i,b in enumerate(pt)])
       if all(32 <= c < 127 for c in result):
           print(f"PASSWORD: {result.decode()}")
   ```

## FIC2026 实战数据
- **固定比较值**: `afb977ac242ad60cf42461ad72ca5149`
- **AES key**: `0123456789abcdef` (重复，标准递增序列)
- **XOR mask**: `bytes([((0x7f + 3*i) & 0xff) for i in range(16)])`
- **明文密码**: `PleaseRunAsAdmin`

## Key Takeaways
- 密码校验逆向: 找 `strncmp`/`memcmp` → 回溯固定比较值 → 识别加密算法
- AES S-box 特征: 256 字节表以 `0x63, 0x7c, 0x77, 0x7b` 开头
- XOR mask 通常是简单的线性递增模式
- openssl 命令行可快速尝试 AES-ECB 解密
