"""2024数证杯 网络流量分析 - Pass 2: 深度提取"""
import dpkt
import socket
import collections
import re
import base64
from urllib.parse import unquote

PCAP_PATH = r"A:\检材 网络流量包\流量分析.pcapng"
VICTIM = "192.168.75.131"
ATTACKER = "192.168.75.132"

def ip_str(packed):
    return socket.inet_ntoa(packed)

def read_pcapng(path):
    with open(path, 'rb') as f:
        try:
            reader = dpkt.pcapng.Reader(f)
        except:
            f.seek(0)
            reader = dpkt.pcap.Reader(f)
        for ts, buf in reader:
            yield ts, buf

def main():
    # Collect targeted data
    phpliteadmin_posts = []       # (ts, uri, body, response_after)
    all_post_requests = []        # (ts, src, dst, uri, body, dport)
    http_200_from_victim = []     # (ts, uri_requested, body, sport)
    reverse_shell_streams = {}    # (sport, dport) -> [data_bytes]
    attacker_http_server = []     # responses from attacker as server
    all_tcp_data = []             # (ts, src, dst, sport, dport, data)
    nikto_ua = []
    all_uas = set()
    
    # For Q09: track phpliteadmin database creation
    phpliteadmin_actions = []
    
    # For Q13: framework detection
    framework_evidence = []
    
    # For Q15-16: weevely
    weevely_candidates = []
    
    # Track HTTP request-response pairs
    http_req_list = []   # (ts, src, method, uri, headers_dict, body, dport)
    http_resp_list = []  # (ts, src, status, headers_dict, body, sport)
    
    print("[*] Pass 2: Reading pcapng...")
    
    for ts, buf in read_pcapng(PCAP_PATH):
        try:
            eth = dpkt.ethernet.Ethernet(buf)
        except:
            continue
        if not isinstance(eth.data, dpkt.ip.IP):
            continue
        ip = eth.data
        src = ip_str(ip.src)
        dst = ip_str(ip.dst)
        
        if not isinstance(ip.data, dpkt.tcp.TCP):
            continue
        tcp = ip.data
        if not tcp.data:
            continue
        
        raw = tcp.data
        text = raw.decode('utf-8', errors='replace')
        
        # Collect all TCP data for shell analysis
        if (src == VICTIM and dst == ATTACKER) or (src == ATTACKER and dst == VICTIM):
            all_tcp_data.append((ts, src, dst, tcp.sport, tcp.dport, raw))
        
        # HTTP Request from attacker
        if src == ATTACKER and dst == VICTIM:
            try:
                req = dpkt.http.Request(raw)
                ua = req.headers.get('user-agent', '')
                all_uas.add(ua)
                body_str = req.body.decode('utf-8', errors='replace') if req.body else ''
                http_req_list.append((ts, src, req.method, req.uri, dict(req.headers), body_str, tcp.dport))
                
                # Check for Nikto
                if 'nikto' in ua.lower():
                    nikto_ua.append(ua)
                
                # phpliteadmin actions
                if 'phpliteadmin' in req.uri.lower() or 'test_db' in req.uri.lower() or 'dbadmin' in req.uri.lower():
                    phpliteadmin_actions.append((ts, req.method, req.uri, body_str, tcp.dport))
                
                # All POST
                if req.method == 'POST':
                    all_post_requests.append((ts, src, dst, req.uri, body_str, tcp.dport))
            except:
                pass
        
        # HTTP Response from victim
        if src == VICTIM and dst == ATTACKER:
            try:
                resp = dpkt.http.Response(raw)
                body_str = resp.body.decode('utf-8', errors='replace') if resp.body else ''
                headers_d = dict(resp.headers)
                http_resp_list.append((ts, src, resp.status, headers_d, body_str, tcp.sport))
                
                # Framework clues in Set-Cookie
                cookie = headers_d.get('set-cookie', '')
                if cookie:
                    framework_evidence.append(f"Set-Cookie: {cookie}")
                
                xpb = headers_d.get('x-powered-by', '')
                if xpb:
                    framework_evidence.append(f"X-Powered-By: {xpb}")
            except:
                pass
        
        # HTTP from victim to attacker (reverse connections / downloads)
        if src == VICTIM and dst == ATTACKER:
            try:
                req = dpkt.http.Request(raw)
                body_str = req.body.decode('utf-8', errors='replace') if req.body else ''
                http_req_list.append((ts, src, req.method, req.uri, dict(req.headers), body_str, tcp.dport))
            except:
                pass
        
        # HTTP response from attacker (when attacker acts as server)
        if src == ATTACKER and dst == VICTIM:
            try:
                resp = dpkt.http.Response(raw)
                body_str = resp.body.decode('utf-8', errors='replace') if resp.body else ''
                attacker_http_server.append((ts, resp.status, body_str, tcp.sport))
            except:
                pass
        
        # Reverse shell detection: non-HTTP traffic between victim and attacker
        # Look for shell-like content
        if (src == VICTIM and dst == ATTACKER) or (src == ATTACKER and dst == VICTIM):
            if tcp.dport not in (80, 443) and tcp.sport not in (80, 443):
                # Check for shell indicators
                shell_indicators = [b'/bin/', b'bash', b'sh-', b'root@', b'www-data', b'uid=', b'Linux ', b'python', b'import ']
                for ind in shell_indicators:
                    if ind in raw[:500]:
                        key = (min(tcp.sport, tcp.dport), max(tcp.sport, tcp.dport))
                        if key not in reverse_shell_streams:
                            reverse_shell_streams[key] = []
                        reverse_shell_streams[key].append((ts, src, dst, tcp.sport, tcp.dport, text[:500]))
                        break
    
    # ===== Q04 确认 =====
    print("\n" + "=" * 60)
    print("Q04: 受害者OS")
    print(f"  Server: Apache/2.2.22 (Ubuntu)")
    print(f"  >>> Q04 = ubuntu")
    
    # ===== Q05 确认 =====
    print("\n" + "=" * 60)
    print("Q05: 端口扫描工具")
    print(f"  Nmap Scripting Engine found in UA")
    print(f"  >>> Q05 = nmap")
    
    # ===== Q06: 漏洞检测工具版本 =====
    print("\n" + "=" * 60)
    print("Q06: 漏洞检测工具版本号")
    print("  所有UA:")
    for ua in sorted(all_uas):
        if ua and len(ua) > 5:
            print(f"    {ua}")
    if nikto_ua:
        print(f"  Nikto UA: {nikto_ua}")
    # Wfuzz is a web application fuzzer/vulnerability tool
    print(f"  Wfuzz/3.1.0 found - web fuzzer/vulnerability tool")
    print(f"  >>> Q06 可能 = 3.1.0 (Wfuzz)")
    
    # ===== Q07 确认 =====
    print("\n" + "=" * 60)
    print("Q07: phpliteadmin登录点")
    print("  phpliteadmin相关请求:")
    for ts, method, uri, body, dport in phpliteadmin_actions[:20]:
        print(f"  [{method}] {uri} port={dport}")
        if body and len(body) < 300:
            print(f"    body: {body}")
    print(f"  >>> Q07 = /dbadmin/test_db.php")
    
    # ===== Q08: 成功登录密码 =====
    print("\n" + "=" * 60)
    print("Q08: phpliteadmin成功登录密码")
    # Match POST login requests with subsequent responses
    login_attempts = []
    for ts, method, uri, body, dport in phpliteadmin_actions:
        if method == 'POST' and 'password=' in body and 'login' in body.lower():
            # Extract password
            for param in body.split('&'):
                if param.startswith('password='):
                    pwd = param.split('=', 1)[1]
                    login_attempts.append((ts, pwd))
                    print(f"  Login attempt at {ts:.2f}: password={pwd}")
    
    # Find responses right after login attempts - check for redirect (302) or success indicators
    for ts_req, pwd in login_attempts:
        for ts_resp, src, status, headers, body, sport in http_resp_list:
            if abs(ts_resp - ts_req) < 2 and src == VICTIM:
                if status in ('302', '303') or 'logout' in body.lower() or 'logged in' in body.lower():
                    print(f"  SUCCESS: password={pwd} -> status={status}")
                    break
                elif status == '200' and ('phpliteadmin' in body.lower() or 'table' in body.lower() or len(body) > 1000):
                    print(f"  Possible success: password={pwd} -> status={status} body_len={len(body)}")
    
    # Check which login was followed by further authenticated actions
    print("  登录后的操作序列:")
    for i, (ts, method, uri, body, dport) in enumerate(phpliteadmin_actions):
        if 'action=' in uri:
            print(f"  [{method}] {uri}")
            if body and len(body) < 200:
                print(f"    body: {body}")
            if i >= 15:
                print(f"  ... {len(phpliteadmin_actions)} total actions")
                break
    
    # ===== Q09: phpinfo文件名 =====
    print("\n" + "=" * 60)
    print("Q09: phpinfo页面文件名")
    # phpliteadmin exploit: create a database with .php extension, then create table with PHP code
    # The database file becomes the PHP backdoor
    for ts, method, uri, body, dport in phpliteadmin_actions:
        if 'new_dbname' in body or 'db_name' in body or 'create' in uri.lower():
            print(f"  [{method}] {uri}")
            print(f"    body: {body}")
    
    # Check for GET requests to .php files that return phpinfo output
    print("  GET requests returning phpinfo:")
    for ts, src, status, headers, body, sport in http_resp_list:
        if 'phpinfo()' in body or '<title>phpinfo()</title>' in body or 'PHP Version' in body[:500]:
            print(f"  Response at {ts:.2f}: status={status} body contains phpinfo (len={len(body)})")
            # Find the request that triggered this
            for ts2, src2, method, uri, hdrs, body2, dport in http_req_list:
                if abs(ts2 - ts) < 1 and src2 == ATTACKER:
                    print(f"    Triggered by: [{method}] {uri}")
    
    # Also look for database creation with .php extension
    for ts, method, uri, body, dport in phpliteadmin_actions:
        decoded_body = unquote(body)
        if '.php' in decoded_body or 'phpinfo' in decoded_body:
            print(f"  [{method}] {uri}")
            print(f"    decoded body: {decoded_body}")
    
    # ===== Q10: payload文件名 =====
    print("\n" + "=" * 60)
    print("Q10: 从攻击机下载的payload")
    for ts, src, method, uri, hdrs, body, dport in http_req_list:
        if src == VICTIM and method == 'GET':
            print(f"  {src} GET {uri} -> {ATTACKER}:{dport}")
    print(f"  >>> Q10 = rev.txt (reverse shell payload)")
    
    # Check attacker's HTTP server responses
    print("  攻击者HTTP服务器响应:")
    for ts, status, body, sport in attacker_http_server[:10]:
        print(f"  status={status} port={sport} body_len={len(body)}")
        if body and len(body) < 500:
            print(f"    body: {body[:300]}")
    
    # ===== Q11: 反弹shell =====
    print("\n" + "=" * 60)
    print("Q11: 反弹shell")
    print("  Shell-like TCP streams (non-HTTP):")
    for key, data_list in sorted(reverse_shell_streams.items()):
        print(f"\n  Port pair: {key[0]} <-> {key[1]} ({len(data_list)} segments)")
        for ts, src, dst, sport, dport, text in data_list[:5]:
            print(f"    {src}:{sport} -> {dst}:{dport}")
            print(f"    content: {text[:200]}")
    
    # Also look for connections from victim to attacker on unusual ports
    print("\n  All victim->attacker non-HTTP TCP streams:")
    v2a_ports = collections.Counter()
    for ts, src, dst, sport, dport, raw in all_tcp_data:
        if src == VICTIM and dst == ATTACKER and dport not in (80, 443, 2000):
            v2a_ports[dport] += 1
    for port, cnt in v2a_ports.most_common(20):
        print(f"    -> {ATTACKER}:{port} ({cnt} packets)")
    
    # ===== Q12: Python版本 =====
    print("\n" + "=" * 60)
    print("Q12: Python版本")
    python_refs = []
    for ts, src, dst, sport, dport, raw in all_tcp_data:
        text = raw.decode('utf-8', errors='replace')
        # Look for Python version strings
        matches = re.findall(r'[Pp]ython[/ ](\d+\.\d+\.\d+)', text)
        if matches:
            python_refs.append((ts, src, dst, sport, dport, matches))
        # Also check for Python in HTTP server header from attacker
        if 'Python' in text and src == ATTACKER:
            idx = text.find('Python')
            snippet = text[max(0,idx-20):idx+40]
            print(f"  Python ref from attacker: {snippet.strip()}")
    
    for ts, src, dst, sport, dport, matches in python_refs:
        print(f"  {src}:{sport}->{dst}:{dport}: Python versions: {matches}")
    
    # Check attacker's HTTP server for Python SimpleHTTPServer
    for ts, status, body, sport in attacker_http_server:
        # SimpleHTTPServer shows "Server: SimpleHTTP/x.x Python/x.x.x"
        pass  # Already captured in headers
    
    # Search in all raw TCP data from attacker
    print("  Searching all attacker traffic for Python...")
    for ts, src, dst, sport, dport, raw in all_tcp_data:
        if src == ATTACKER:
            text = raw.decode('latin-1', errors='replace')
            if 'ython' in text:
                # Find context
                idx = text.lower().find('ython')
                snippet = text[max(0,idx-30):idx+50].replace('\r\n', ' | ').replace('\n', ' | ')
                print(f"  [{src}:{sport}->{dst}:{dport}] {snippet.strip()}")
    
    # ===== Q13: 网站框架 =====
    print("\n" + "=" * 60)
    print("Q13: 网站框架")
    fw_set = set()
    for ev in framework_evidence:
        fw_set.add(ev)
    for ev in sorted(fw_set)[:20]:
        print(f"  {ev}")
    
    # Search response bodies more carefully
    print("  Searching response bodies for framework indicators...")
    for ts, src, status, headers, body, sport in http_resp_list:
        if src == VICTIM and status == '200':
            body_lower = body.lower()
            # Check for common framework indicators
            if 'thinkphp' in body_lower:
                print(f"  FOUND thinkphp in response body")
            if 'laravel' in body_lower:
                print(f"  FOUND laravel in response body")
            if 'x-powered-by' in str(headers).lower():
                xpb = headers.get('x-powered-by', '')
                if xpb and 'PHP' not in xpb:
                    print(f"  X-Powered-By (non-PHP): {xpb}")
    
    # Check for CMS/framework in HTML content
    cms_patterns = ['wp-content', 'wp-admin', 'joomla', 'drupal', 'thinkphp', 'laravel', 
                    'codeigniter', 'yii', 'symfony', 'cakephp', 'zend']
    for ts, src, status, headers, body, sport in http_resp_list:
        if src == VICTIM and status == '200' and len(body) > 100:
            for pat in cms_patterns:
                if pat in body.lower():
                    idx = body.lower().find(pat)
                    ctx = body[max(0,idx-50):idx+80]
                    print(f"  CMS pattern '{pat}' in response: {ctx[:150]}")
                    break
    
    # ===== Q14: 数据库密码 =====
    print("\n" + "=" * 60)
    print("Q14: 数据库密码")
    # Look in response bodies for config files, database credentials
    db_patterns = [r'db_pass\w*\s*[=:]\s*[\'"]?(\S+)', r'password\s*[=:>]\s*[\'"](\S+?)[\'"]',
                   r'DB_PASSWORD\s*=\s*(\S+)', r'MYSQL_ROOT_PASSWORD\s*=\s*(\S+)',
                   r"'password'\s*=>\s*'([^']+)'"]
    
    for ts, src, status, headers, body, sport in http_resp_list:
        if src == VICTIM:
            for pat in db_patterns:
                matches = re.findall(pat, body, re.IGNORECASE)
                if matches:
                    print(f"  Pattern '{pat}' matched: {matches} in response status={status}")
                    idx = body.lower().find('password')
                    if idx >= 0:
                        print(f"    context: {body[max(0,idx-80):idx+120]}")
    
    # Search TCP streams for database connection strings
    for ts, src, dst, sport, dport, raw in all_tcp_data:
        text = raw.decode('utf-8', errors='replace')
        if ('db_pass' in text.lower() or 'database_password' in text.lower() or 
            'mysql_pwd' in text.lower() or "=> '" in text and 'pass' in text.lower()):
            print(f"  DB cred in stream {src}:{sport}->{dst}:{dport}")
            idx = text.lower().find('pass')
            print(f"    {text[max(0,idx-100):idx+150]}")
    
    # ===== Q15-16: weevely =====
    print("\n" + "=" * 60)
    print("Q15-Q16: weevely木马")
    # weevely communicates via POST with obfuscated PHP in cookies/body
    # Look for POST requests to .php files with base64/obfuscated payloads
    weevely_posts = []
    for ts, src, dst, uri, body, dport in all_post_requests:
        if src == ATTACKER and '.php' in uri:
            # weevely payload characteristics: short body, base64-like content
            if body and len(body) > 20:
                # Check for base64 patterns
                b64_ratio = sum(1 for c in body if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=') / max(len(body), 1)
                if b64_ratio > 0.7 and uri not in ('/sdk',):
                    weevely_posts.append((ts, uri, body, dport))
    
    print(f"  疑似weevely POST (base64 heavy, to .php): {len(weevely_posts)}")
    for ts, uri, body, dport in weevely_posts[:10]:
        print(f"  POST {uri} port={dport} body_len={len(body)}")
        print(f"    body: {body[:200]}")
        # Try to decode
        try:
            decoded = base64.b64decode(body).decode('utf-8', errors='replace')
            print(f"    decoded: {decoded[:200]}")
        except:
            pass
    
    # Also check help.php downloads - weevely backdoor might be help.php
    print("\n  help.php相关流量:")
    for ts, src, method, uri, hdrs, body, dport in http_req_list:
        if 'help.php' in uri:
            print(f"  [{method}] {uri} from {src} port={dport}")
    
    # Look for POST to help.php (weevely backdoor)
    for ts, src, dst, uri, body, dport in all_post_requests:
        if 'help.php' in uri:
            print(f"  POST {uri} from {src} port={dport} body_len={len(body)}")
            print(f"    body: {body[:300]}")
    
    # Check responses to help.php POST (first execution)
    print("\n  help.php POST responses:")
    for ts_req, src_req, dst_req, uri, body_req, dport in all_post_requests:
        if 'help.php' in uri:
            for ts_resp, src_resp, status, headers, body_resp, sport in http_resp_list:
                if abs(ts_resp - ts_req) < 2 and src_resp == VICTIM:
                    print(f"  Response status={status} body_len={len(body_resp)}")
                    if body_resp:
                        print(f"    body: {body_resp[:300]}")
                    break
    
    # ===== Summary =====
    print("\n" + "=" * 60)
    print("=== 已确认答案汇总 ===")
    print(f"Q01 = 3504 (已知)")
    print(f"Q02 = 23F79 (已知)")
    print(f"Q03 = 192.168.75.131")
    print(f"Q04 = ubuntu")
    print(f"Q05 = nmap")
    print(f"Q06 = 待确认 (Wfuzz/3.1.0 or Nikto?)")
    print(f"Q07 = /dbadmin/test_db.php")
    print(f"Q08 = 待确认 (尝试了123456, password, admin)")
    print(f"Q09 = 待确认 (phpinfo通过phpliteadmin创建)")
    print(f"Q10 = rev.txt")
    print(f"Q11 = 待确认")
    print(f"Q12 = 待确认")
    print(f"Q13 = 待确认")
    print(f"Q14 = 待确认")
    print(f"Q15 = 待确认")
    print(f"Q16 = 待确认")

if __name__ == '__main__':
    main()
