# -*- coding: utf-8 -*-
"""Decode all weevely traffic"""
import dpkt, socket, sys, io, base64, zlib, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PCAP = r"A:\检材 网络流量包\流量分析.pcapng"
KH = "cbbf9691e009"
KF = "85a89e92c410"
k = b"c6ae1e70"

def ip_str(p): return socket.inet_ntoa(p)
def xor_d(data, key):
    return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])
def safe(s):
    return ''.join(c if c.isprintable() or c in '\n\r\t' else '.' for c in s)

with open(PCAP, 'rb') as f:
    r = dpkt.pcapng.Reader(f)
    idx = 0
    first_resp = None
    for ts, buf in r:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
        except:
            continue
        if not isinstance(eth.data, dpkt.ip.IP):
            continue
        ip = eth.data
        src, dst = ip_str(ip.src), ip_str(ip.dst)
        if not isinstance(ip.data, dpkt.tcp.TCP):
            continue
        tcp = ip.data
        if not tcp.data:
            continue
        text = tcp.data.decode('latin-1', 'replace')
        
        if KH in text and KF in text:
            idx += 1
            direction = 'REQ' if src == '192.168.75.132' else 'RESP'
            
            m = re.search(KH + '(.+?)' + KF, text)
            if m:
                b64 = m.group(1)
                try:
                    raw = base64.b64decode(b64)
                    dec = xor_d(raw, k)
                    result = zlib.decompress(dec)
                    decoded = result.decode('utf-8', 'replace')
                    print(f"#{idx} [{direction}] {src}:{tcp.sport}->{dst}:{tcp.dport} port={tcp.dport}")
                    print(f"  DECODED: {safe(decoded[:500])}")
                    if direction == 'RESP' and first_resp is None:
                        first_resp = decoded
                except Exception as e:
                    print(f"#{idx} [{direction}] {src}:{tcp.sport}->{dst}:{tcp.dport}")
                    print(f"  b64: {b64[:100]}")
                    print(f"  err: {e}")
            else:
                print(f"#{idx} [{direction}] {src}:{tcp.sport}->{dst}:{tcp.dport} (no b64 match)")

    print(f"\n=== TOTAL: {idx} weevely packets ===")
    if first_resp:
        print(f"=== FIRST RESPONSE BUFFER: {safe(first_resp)} ===")
