---
tags: [stego, png, base64, hex, tEXt_chunk, trailing_data, stego_crypto]
tools: [strings, python3, base64]
category: stego
difficulty: easy
source: pipeline_test_2026
date: 2026-05-05
verified: true
---

# PNG Steganography — Hidden Data in tEXt Chunk and Trailing Bytes

## Problem
Given a PNG image, find a hidden flag. No visible anomaly in the image itself.

## Solution Steps
1. Check file type
   ```
   file evidence.png
   ```
   → PNG image data

2. Extract strings from the file
   ```
   strings evidence.png
   ```
   → Found `Check this: ZmxhZ3t4aWFva29uZ19waXBlbGluZV93b3Jrc18yMDI2fQ==` in tEXt chunk
   → Found hex string `666c6167...` after IEND marker

3. Decode Base64
   ```
   echo "ZmxhZ3t4aWFva29uZ19waXBlbGluZV93b3Jrc18yMDI2fQ==" | base64 -d
   ```
   → flag{xiaokong_pipeline_works_2026}

4. Decode trailing hex (alternative path)
   ```
   python3 -c "print(bytes.fromhex('666c61677b7869616f6b6f6e675f706970656c696e655f776f726b735f323032367d').decode())"
   ```
   → flag{xiaokong_pipeline_works_2026}

## Key Takeaways
- Always run `strings` first — it catches metadata, comments, and appended data
- PNG tEXt chunks can contain arbitrary text (often overlooked)
- Data after IEND marker is ignored by image viewers but still exists in the file
- Base64 strings (ending with = or ==) are a strong indicator of encoded data
- Hex strings (only 0-9a-f characters) should be tried as hex decode

## Answer
flag{xiaokong_pipeline_works_2026}
