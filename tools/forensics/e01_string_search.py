# -*- coding: utf-8 -*-
"""Targeted string searches in E01 for mobile forensics questions"""
import sys, io, struct, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pyewf

E01 = r"A:\检材 手机\24CS_Phone.E01"

def open_e01():
    filenames = pyewf.glob(E01)
    h = pyewf.handle()
    h.open(filenames)
    return h

def read_at(h, offset, size):
    h.seek(offset)
    return h.read(size)

def search_bytes(h, total, pattern, max_hits=20, context=200):
    """Search for bytes pattern with context"""
    CHUNK = 64 * 1024 * 1024
    hits = []
    offset = 0
    while offset < total and len(hits) < max_hits:
        data = read_at(h, offset, CHUNK)
        if not data:
            break
        pos = 0
        while pos < len(data):
            idx = data.find(pattern, pos)
            if idx < 0:
                break
            abs_off = offset + idx
            # Get context
            start = max(0, idx - context)
            end = min(len(data), idx + len(pattern) + context)
            ctx = data[start:end]
            hits.append((abs_off, ctx))
            pos = idx + len(pattern)
        offset += CHUNK - len(pattern) - context
    return hits

def safe_str(data, encoding='utf-8'):
    text = data.decode(encoding, 'replace')
    return ''.join(c if c.isprintable() or c in '\n\r\t' else '.' for c in text)

def main():
    h = open_e01()
    total = h.get_media_size()
    print(f"Image: {total/(1024**3):.2f} GB")
    
    # Q01: WeChat ID - search for WeChat userinfo/config patterns
    print("\n" + "="*60)
    print("Q01: WeChat ID (微信ID)")
    # WeChat stores the user's wxid in various places
    # Search for 'wxid_' pattern (common WeChat ID prefix)
    hits = search_bytes(h, total, b'wxid_', max_hits=30, context=100)
    seen = set()
    for off, ctx in hits:
        text = safe_str(ctx)
        # Extract wxid
        m = re.search(r'(wxid_[a-zA-Z0-9_]+)', text)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            print(f"  @0x{off:x}: {m.group(1)}")
    
    # Also search for wechat alias (custom WeChat ID)
    # WeChat userinfo table has key-value pairs
    for pattern in [b'"alias"', b'<alias>', b'alias\x00']:
        hits = search_bytes(h, total, pattern, max_hits=5, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            if 'wechat' in text.lower() or 'weixin' in text.lower() or 'wx' in text.lower():
                print(f"  alias@0x{off:x}: {text[:100]}")
    
    # Q02: 宝塔面板验证码 (BaoTa panel verification code in SMS)
    print("\n" + "="*60)
    print("Q02: 宝塔面板验证码 (SMS)")
    for pattern in [b'\xe5\xae\x9d\xe5\xa1\x94', b'bt.cn', b'BaoTa', b'baota']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=300)
        for off, ctx in hits:
            text = safe_str(ctx)
            print(f"  @0x{off:x}: {text[:200]}")
    
    # Q03: 鸽哒 app last update time
    print("\n" + "="*60)
    print("Q03: 鸽哒 (GeDa) app update time")
    for pattern in [b'com.geda', b'\xe9\xb8\xbd\xe5\x93\x92', b'gedatalk', b'com.talkmessenger']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            if len(text.strip('.')) > 10:
                print(f"  @0x{off:x}: {text[:150]}")
    
    # Q04: Last boot time - search for system boot records
    print("\n" + "="*60)
    print("Q04: Last boot time")
    for pattern in [b'sys.boot.completed', b'boot_completed', b'BOOT_COMPLETED']:
        hits = search_bytes(h, total, pattern, max_hits=5, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            print(f"  @0x{off:x}: {text[:150]}")
    
    # Q05: 高德地图 login ID
    print("\n" + "="*60)
    print("Q05: 高德地图 (AMap) login ID")
    for pattern in [b'com.autonavi', b'amap_core', b'autonavi']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            if 'uid' in text.lower() or 'user' in text.lower() or 'login' in text.lower() or 'account' in text.lower():
                print(f"  @0x{off:x}: {text[:200]}")
    
    # Q07: WeChat bill zip password
    print("\n" + "="*60)
    print("Q07: WeChat bill zip password")
    for pattern in [b'20220207', b'20230206', b'\xe5\xbe\xae\xe4\xbf\xa1\xe8\xb4\xa6\xe5\x8d\x95']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=300)
        for off, ctx in hits:
            text = safe_str(ctx)
            print(f"  @0x{off:x}: {text[:200]}")
    
    # Q13: 小众即时通讯 server IP (GeDa/鸽哒)
    print("\n" + "="*60)
    print("Q13: 即时通讯 server IP")
    for pattern in [b'server_ip', b'server_host', b'server_address',
                    b'msg_server', b'im_server']:
        hits = search_bytes(h, total, pattern, max_hits=5, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            print(f"  @0x{off:x}: {text[:150]}")
    
    # Q14: 传奇游戏币平台 package name
    print("\n" + "="*60)
    print("Q14: 传奇游戏币平台 package name")
    for pattern in [b'\xe4\xbc\xa0\xe5\xa5\x87', b'legend', b'mir2', b'\xe6\xb8\xb8\xe6\x88\x8f\xe5\xb8\x81']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            if 'com.' in text:
                print(f"  @0x{off:x}: {text[:200]}")
    
    # Q15: 双色球三等奖奖金
    print("\n" + "="*60)
    print("Q15: 双色球三等奖")
    for pattern in [b'\xe5\x8f\x8c\xe8\x89\xb2\xe7\x90\x83', b'ssq', b'\xe4\xb8\x89\xe7\xad\x89\xe5\xa5\x96']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=500)
        for off, ctx in hits:
            text = safe_str(ctx)
            print(f"  @0x{off:x}: {text[:300]}")
    
    # Q16-17: 米家摄像头
    print("\n" + "="*60)
    print("Q16-17: 米家摄像头")
    for pattern in [b'com.xiaomi.smarthome', b'mijia', b'miot', b'chuangmi']:
        hits = search_bytes(h, total, pattern, max_hits=10, context=200)
        for off, ctx in hits:
            text = safe_str(ctx)
            if any(x in text.lower() for x in ['camera', 'ip', 'user', 'device', 'did']):
                print(f"  @0x{off:x}: {text[:200]}")
    
    h.close()
    print("\n[*] Done.")

if __name__ == '__main__':
    main()
