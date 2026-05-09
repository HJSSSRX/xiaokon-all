# -*- coding: utf-8 -*-
"""Pass 5: Extract rev.txt payload, find weevely upload, get all remaining answers"""
import dpkt, socket, collections, re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PCAP = r"A:\检材 网络流量包\流量分析.pcapng"
VICTIM = "192.168.75.131"
ATTACKER = "192.168.75.132"

def ip_str(p): return socket.inet_ntoa(p)
def safe(s): return ''.join(c if (c.isprintable() or c in '\n\r\t') else '.' for c in s)

def read_pcap(path):
    with open(path,'rb') as f:
        try: r = dpkt.pcapng.Reader(f)
        except: f.seek(0); r = dpkt.pcap.Reader(f)
        for ts,buf in r: yield ts,buf

def main():
    # Reassemble TCP streams from attacker:2000 -> victim (HTTP server responses)
    atk_server_stream = bytearray()
    
    # ALL TCP data from attacker to victim on ANY port except 80
    atk_nonhttp = collections.defaultdict(bytearray)
    
    # ALL HTTP requests from attacker to victim on ALL ports
    all_atk_requests = []
    
    # ALL victim GET /help.php or /demo.php responses
    victim_php_gets = []
    
    # Second reverse shell? Check all victim->attacker TCP
    shell_candidates = collections.defaultdict(bytearray)
    
    # Weevely: any POST on any port to any .php path
    all_posts_any_port = []
    
    print("[*] Pass 5 reading...")
    
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
        
        # Attacker port 2000 -> victim (reassemble full stream for rev.txt/help.php)
        if src == ATTACKER and dst == VICTIM and tcp.sport == 2000:
            atk_server_stream.extend(raw)
        
        # Any HTTP request from attacker to victim
        if src == ATTACKER and dst == VICTIM:
            try:
                req = dpkt.http.Request(raw)
                body_str = req.body.decode('utf-8', errors='replace') if req.body else ''
                cookies = req.headers.get('cookie', '')
                ua = req.headers.get('user-agent', '')
                all_atk_requests.append((ts, req.method, req.uri, body_str, cookies, ua, tcp.dport))
                
                if req.method == 'POST':
                    all_posts_any_port.append((ts, req.uri, body_str, cookies, tcp.dport))
            except: pass
        
        # Any victim response to attacker with help.php or demo.php content
        if src == VICTIM and dst == ATTACKER:
            try:
                resp = dpkt.http.Response(raw)
                if resp.body:
                    body = resp.body.decode('utf-8', errors='replace')
                    if 'phpinfo' in body[:200] or 'PHP Version' in body[:500]:
                        victim_php_gets.append((ts, 'phpinfo', body[:500], tcp.sport))
                    if 'weevely' in body.lower() or 'eval' in body[:200]:
                        victim_php_gets.append((ts, 'weevely?', body[:500], tcp.sport))
            except: pass
        
        # Track all non-80, non-SSH, non-2000 connections for second shell
        if src == ATTACKER and dst == VICTIM:
            if tcp.dport not in (80, 22, 2000) and tcp.sport not in (80, 22, 2000):
                shell_candidates[('a2v', tcp.dport)].extend(raw[:500])
        if src == VICTIM and dst == ATTACKER:
            if tcp.sport not in (80, 22, 2000) and tcp.dport not in (80, 22, 2000, 30127):
                shell_candidates[('v2a', tcp.dport)].extend(raw[:500])
    
    # ============================================================
    print("\n" + "="*60)
    print("攻击者HTTP服务器(:2000)完整响应流:")
    # Parse multiple HTTP responses from the stream
    stream_text = bytes(atk_server_stream).decode('latin-1', errors='replace')
    # Split by HTTP response boundaries
    responses = re.split(r'(HTTP/\d\.\d \d+ \w+)', stream_text)
    
    print(f"  Total stream size: {len(atk_server_stream)} bytes")
    
    # Find rev.txt content (first response, text/plain)
    idx = stream_text.find('text/plain')
    if idx >= 0:
        # Find the body after double CRLF
        body_start = stream_text.find('\r\n\r\n', idx)
        if body_start > 0:
            body_start += 4
            # Find next HTTP response
            next_http = stream_text.find('HTTP/', body_start)
            if next_http > 0:
                rev_content = stream_text[body_start:next_http]
            else:
                rev_content = stream_text[body_start:body_start+3000]
            print("\n--- rev.txt content ---")
            print(safe(rev_content[:3000]))
            # Extract IP:port from PHP reverse shell
            m = re.search(r"['\"](\d+\.\d+\.\d+\.\d+)['\"].*?['\"](\d+)['\"]", rev_content)
            if m:
                print(f"\n  >>> Reverse shell connects to: {m.group(1)}:{m.group(2)}")
            m2 = re.findall(r'(\d+\.\d+\.\d+\.\d+)', rev_content)
            m3 = re.findall(r'(\d{2,5})', rev_content)
            if m2:
                print(f"  IPs in rev.txt: {m2}")
            # Check for port
            port_matches = re.findall(r'port["\s=:]+(\d+)', rev_content, re.I)
            if port_matches:
                print(f"  Ports in rev.txt: {port_matches}")
    
    # Find help.php content (application/octet-stream)
    idx = stream_text.find('application/octet-stream')
    if idx >= 0:
        body_start = stream_text.find('\r\n\r\n', idx)
        if body_start > 0:
            body_start += 4
            next_http = stream_text.find('HTTP/', body_start)
            if next_http > 0:
                help_content = stream_text[body_start:next_http]
            else:
                help_content = stream_text[body_start:body_start+2000]
            print("\n--- help.php content (weevely backdoor) ---")
            print(safe(help_content[:2000]))
    
    # ============================================================
    print("\n" + "="*60)
    print("ALL POST requests (any port):")
    for ts, uri, body, cookies, dport in all_posts_any_port:
        if 'dbadmin' not in uri:
            print(f"  POST {uri} port={dport} body_len={len(body)} cookie_len={len(cookies)}")
            if body:
                print(f"    body: {safe(body[:300])}")
    
    # ============================================================
    print("\n" + "="*60)
    print("攻击者GET help.php / demo.php on victim:")
    for ts, method, uri, body, cookies, ua, dport in all_atk_requests:
        if method == 'GET' and ('help' in uri.lower() or 'demo' in uri.lower()):
            print(f"  GET {uri} port={dport}")
    
    # Also check for any access to /usr/databases/ paths
    for ts, method, uri, body, cookies, ua, dport in all_atk_requests:
        if 'databases' in uri.lower() and 'dbadmin' not in uri:
            print(f"  [{method}] {uri} port={dport}")
    
    # ============================================================
    print("\n" + "="*60)
    print("非标准端口shell候选 (attacker->victim, 非80/22/2000):")
    for key, data in sorted(shell_candidates.items(), key=lambda x: -len(x[1]))[:10]:
        direction, port = key
        text = bytes(data).decode('latin-1', errors='replace')
        is_interesting = any(x in text.lower() for x in ['root', 'bash', 'shell', 'python', 'import', 'uid=', 'linux'])
        if is_interesting or len(data) > 200:
            print(f"  {direction} port={port}: {len(data)} bytes {'*** INTERESTING ***' if is_interesting else ''}")
            print(f"    {safe(text[:300])}")
    
    # ============================================================
    print("\n" + "="*60)
    print("PHP-related victim responses:")
    for ts, label, body, sport in victim_php_gets:
        print(f"  [{label}] port={sport}")
        print(f"    {safe(body[:200])}")
    
    print("\n[*] Pass 5 Done.")

if __name__ == '__main__':
    main()
