# -*- coding: utf-8 -*-
"""Pass 4: Extract reverse shell stream, rev.txt content, weevely, framework"""
import dpkt, socket, collections, re, sys, io
from urllib.parse import unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PCAP = r"A:\检材 网络流量包\流量分析.pcapng"
VICTIM = "192.168.75.131"
ATTACKER = "192.168.75.132"

def ip_str(p): return socket.inet_ntoa(p)

def read_pcap(path):
    with open(path,'rb') as f:
        try: r = dpkt.pcapng.Reader(f)
        except: f.seek(0); r = dpkt.pcap.Reader(f)
        for ts,buf in r: yield ts,buf

def safe_print(s):
    return ''.join(c if (c.isprintable() or c in '\n\r\t') else '.' for c in s)

def main():
    # Full reverse shell stream reassembly (port 30127)
    shell_v2a = []  # victim->attacker (shell output) on dport 30127
    shell_a2v = []  # attacker->victim (commands) from sport 30127
    
    # rev.txt content from attacker HTTP server
    rev_txt_resp = bytearray()
    help_php_resp = bytearray()
    
    # ALL HTTP responses from victim to extract framework/db info
    victim_200_bodies = []
    
    # ALL non-dbadmin POST requests on port 80 (weevely)
    non_dbadmin_posts = []
    
    # Track all unique destination ports from victim to attacker
    v2a_conn_ports = collections.defaultdict(int)
    
    # Track GET requests to specific files on victim
    get_to_victim = []
    
    print("[*] Pass 4 reading...")
    
    capturing_rev = False
    capturing_help = False
    
    for ts, buf in read_pcap(PCAP):
        try: eth = dpkt.ethernet.Ethernet(buf)
        except: continue
        if not isinstance(eth.data, dpkt.ip.IP): continue
        ip = eth.data
        src, dst = ip_str(ip.src), ip_str(ip.dst)
        if not isinstance(ip.data, dpkt.tcp.TCP): continue
        tcp = ip.data
        if not tcp.data: continue
        raw = tcp.data
        
        # === Reverse shell stream on port 30127 ===
        if src == VICTIM and dst == ATTACKER and tcp.dport == 30127:
            shell_v2a.append((ts, raw))
        if src == ATTACKER and dst == VICTIM and tcp.sport == 30127:
            shell_a2v.append((ts, raw))
        
        # === Track all victim->attacker destination ports ===
        if src == VICTIM and dst == ATTACKER:
            v2a_conn_ports[tcp.dport] += 1
        
        # === Attacker HTTP server responses (port 2000) ===
        if src == ATTACKER and dst == VICTIM and tcp.sport == 2000:
            try:
                text = raw.decode('latin-1')
                if 'text/plain' in text and 'rev.txt' not in str(rev_txt_resp):
                    # This might be rev.txt response
                    try:
                        resp = dpkt.http.Response(raw)
                        if resp.body:
                            if len(rev_txt_resp) == 0:
                                rev_txt_resp.extend(resp.body)
                    except: pass
                elif 'application/octet-stream' in text:
                    try:
                        resp = dpkt.http.Response(raw)
                        if resp.body and len(help_php_resp) == 0:
                            help_php_resp.extend(resp.body)
                    except: pass
            except: pass
        
        # === HTTP GET requests to victim ===
        if src == ATTACKER and dst == VICTIM and tcp.dport == 80:
            try:
                req = dpkt.http.Request(raw)
                if req.method == 'GET':
                    get_to_victim.append((ts, req.uri))
                # ALL POST to port 80 (not just .php)
                if req.method == 'POST' and 'dbadmin' not in req.uri:
                    body_str = req.body.decode('utf-8', errors='replace') if req.body else ''
                    cookies = req.headers.get('cookie', '')
                    non_dbadmin_posts.append((ts, req.uri, body_str, cookies))
            except: pass
        
        # === HTTP responses with 200 from victim ===
        if src == VICTIM and dst == ATTACKER and tcp.sport == 80:
            try:
                resp = dpkt.http.Response(raw)
                if resp.status == '200' and resp.body:
                    body = resp.body.decode('utf-8', errors='replace')
                    if len(body) > 50:
                        victim_200_bodies.append((ts, body, dict(resp.headers)))
            except: pass
    
    # ============================================================
    print("\n" + "="*60)
    print("Q11: 反弹SHELL完整对话 (port 30127)")
    print("-"*40)
    print("攻击者发送的命令:")
    for ts, raw in sorted(shell_a2v, key=lambda x: x[0]):
        text = raw.decode('utf-8', errors='replace')
        print(f"  [{ts:.2f}] {safe_print(text.strip())}")
    
    print("\n" + "-"*40)
    print("受害者shell输出 (前8000字节):")
    total = bytearray()
    for ts, raw in sorted(shell_v2a, key=lambda x: x[0]):
        total.extend(raw)
    text = total.decode('utf-8', errors='replace')
    print(safe_print(text[:8000]))
    
    print(f"\n  >>> Q11 = {ATTACKER}:30127 (reverse shell port)")
    
    # ============================================================
    print("\n" + "="*60)
    print("rev.txt 内容 (reverse shell payload):")
    if rev_txt_resp:
        content = bytes(rev_txt_resp).decode('utf-8', errors='replace')
        print(safe_print(content[:3000]))
        # Extract connect-back IP:port
        m = re.search(r'(\d+\.\d+\.\d+\.\d+).*?(\d{2,5})', content)
        if m:
            print(f"\n  Payload connects back to: {m.group(1)}:{m.group(2)}")
    else:
        print("  (empty)")
    
    # ============================================================
    print("\n" + "="*60)
    print("help.php 内容 (weevely backdoor):")
    if help_php_resp:
        content = bytes(help_php_resp).decode('utf-8', errors='replace')
        print(safe_print(content[:2000]))
    else:
        print("  (empty)")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q13: 网站框架 (从shell output中确认)")
    # The shell commands show 'cd wordpress', 'cat wp-config.php'
    # This confirms WordPress
    print("  Shell shows: cd wordpress / cat wp-config.php")
    print("  >>> Q13 = wordpress")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q14: 数据库密码 (从wp-config.php grep输出)")
    # The password is in the shell output where attacker ran:
    # cat wp-config.php |grep password
    # cat wp-config.php |grep -i pass
    print("  (Check shell output above for DB_PASSWORD)")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q15: weevely上传端口")
    print(f"  help.php downloaded from attacker:2000")
    print(f"  Non-dbadmin POST requests on port 80: {len(non_dbadmin_posts)}")
    for ts, uri, body, cookies in non_dbadmin_posts[:20]:
        print(f"  POST {uri} body_len={len(body)} cookie_len={len(cookies)}")
        if body:
            print(f"    body: {safe_print(body[:200])}")
    
    # ============================================================
    print("\n" + "="*60)
    print("所有victim->attacker目标端口统计:")
    for port, cnt in sorted(v2a_conn_ports.items(), key=lambda x: -x[1])[:20]:
        print(f"  port {port}: {cnt} packets")
    
    # ============================================================
    print("\n" + "="*60)
    print("攻击者访问的URI (GET, 非扫描, 有意义的):")
    interesting_gets = [u for ts, u in get_to_victim if not u.startswith('/%') and not u.startswith('/$') and not u.startswith('/!') and len(u) < 100]
    seen = set()
    for u in interesting_gets:
        if u not in seen:
            seen.add(u)
            print(f"  GET {u}")
    
    print("\n[*] Pass 4 Done.")

if __name__ == '__main__':
    main()
