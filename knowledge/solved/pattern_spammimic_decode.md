---
tags: [email_forensics, spammimic, encoding, steganography, deepin, stego_crypto]
tools: [python, requests, grep]
category: stego_crypto
difficulty: medium
source: fic2026
date: 2026-05-05
verified: true
---

# Title: Spammimic 邮件隐写解码

## Problem
邮件正文包含 spammimic.com 加密的隐藏信息，需提取并解码。

## Solution Steps

1. 识别特征 — 邮件正文包含看似正常但措辞奇怪的英文垃圾邮件模板
   ```bash
   # spammimic 编码后的邮件看起来像正常垃圾邮件
   # 关键特征：措辞固定、段落结构重复
   ```

2. 在线解码
   ```python
   import requests
   def decode_spammimic(ciphertext):
       url = "http://www.spammimic.com/decode.cgi"
       data = {"cyphertext": ciphertext}
       response = requests.post(url, data=data)
       return response.text
   ```

3. 提取解码结果
   ```python
   import re, html
   def extract_decoded_text(html_response):
       match = re.search(r'<textarea[^>]*name="plaintext"[^>]*>(.*?)</textarea>',
                        html_response, re.DOTALL)
       if match:
           return html.unescape(match.group(1))
       return None
   ```

4. 处理编码 — 结果可能需要 UTF-8 / GBK 二次解码
   ```python
   try:
       print(decoded.encode('latin1').decode('utf-8'))
   except:
       print(decoded.encode('latin1').decode('gbk'))
   ```

## Key Takeaways
- spammimic 将信息编码为看似正常的垃圾邮件文本
- 网站可能有访问限制，需重试机制
- 解码结果可能需要二次编码处理
- 备用方案：可本地实现 spammimic 解码算法
