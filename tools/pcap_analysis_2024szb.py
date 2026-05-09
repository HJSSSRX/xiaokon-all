"""2024数证杯初赛 - 网络流量分析 Q03-Q16 批量提取"""
import dpkt
import socket
import collections
import sys
import re

PCAP_PATH = r"A:\检材 网络流量包\流量分析.pcapng"

def read_pcapng(path):
    """Read pcapng and yield (ts, buf) tuples"""
    with open(path, 'rb') as f:
        try:
            reader = dpkt.pcapng.Reader(f)
        except Exception:
            f.seek(0)
            reader = dpkt.pcap.Reader(f)
        for ts, buf in reader:
            yield ts, buf

def ip_str(packed):
    return socket.inet_ntoa(packed)

def main():
    print("=" * 60)
    print("2024数证杯 网络流量分析")
    print("=" * 60)

    syn_dst_count = collections.Counter()
    syn_src_count = collections.Counter()
    http_user_agents = set()
    http_servers = set()
    http_requests = []      # (src_ip, dst_ip, method, uri, host, body, dst_port)
    http_responses = []     # (src_ip, dst_ip, status, headers_str, body, src_port)
    tcp_streams = collections.defaultdict(list)  # (src,dst,sport,dport) -> [(ts, data)]
    
    pkt_count = 0
    first_ts = None
    last_ts = None
    
    print("[*] Reading pcapng... (this may take a minute for 169MB)")
    
    for ts, buf in read_pcapng(PCAP_PATH):
        pkt_count += 1
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        
        try:
            eth = dpkt.ethernet.Ethernet(buf)
        except:
            continue
        
        if not isinstance(eth.data, dpkt.ip.IP):
            continue
        ip = eth.data
        
        src_ip = ip_str(ip.src)
        dst_ip = ip_str(ip.dst)
        
        if isinstance(ip.data, dpkt.tcp.TCP):
            tcp = ip.data
            
            # SYN scan detection (Q03, Q05)
            if (tcp.flags & dpkt.tcp.TH_SYN) and not (tcp.flags & dpkt.tcp.TH_ACK):
                syn_dst_count[dst_ip] += 1
                syn_src_count[src_ip] += 1
            
            # Collect TCP data for stream reassembly
            if tcp.data:
                key = (src_ip, dst_ip, tcp.sport, tcp.dport)
                tcp_streams[key].append((ts, tcp.data))
                
                # Try HTTP request parsing
                try:
                    http_req = dpkt.http.Request(tcp.data)
                    ua = http_req.headers.get('user-agent', '')
                    host = http_req.headers.get('host', '')
                    body = http_req.body.decode('utf-8', errors='replace') if http_req.body else ''
                    uri = http_req.uri
                    method = http_req.method
                    if ua:
                        http_user_agents.add(ua)
                    http_requests.append((src_ip, dst_ip, method, uri, host, body, tcp.dport))
                except:
                    pass
                
                # Try HTTP response parsing
                try:
                    http_resp = dpkt.http.Response(tcp.data)
                    server = http_resp.headers.get('server', '')
                    if server:
                        http_servers.add(server)
                    body = http_resp.body.decode('utf-8', errors='replace') if http_resp.body else ''
                    headers_str = str(http_resp.headers)
                    http_responses.append((src_ip, dst_ip, http_resp.status, headers_str, body, tcp.sport))
                except:
                    pass
    
    duration = last_ts - first_ts if first_ts and last_ts else 0
    print(f"\n[*] Total packets: {pkt_count}")
    print(f"[*] Duration: {duration:.0f} seconds")
    
    # ===== Q03: 受害者IP (被SYN扫描最多的目标) =====
    print("\n" + "=" * 60)
    print("Q03: 受害者IP (SYN扫描目标 top5)")
    for ip_addr, cnt in syn_dst_count.most_common(5):
        print(f"  {ip_addr} <- {cnt} SYN packets")
    
    print("\nQ03: 攻击者IP (SYN发起方 top5)")
    for ip_addr, cnt in syn_src_count.most_common(5):
        print(f"  {ip_addr} -> {cnt} SYN packets")
    
    victim_ip = syn_dst_count.most_common(1)[0][0] if syn_dst_count else "unknown"
    attacker_ip = syn_src_count.most_common(1)[0][0] if syn_src_count else "unknown"
    print(f"\n  >>> Q03 受害者IP = {victim_ip}")
    print(f"  >>> 攻击者IP = {attacker_ip}")
    
    # ===== Q04: 受害者OS (from Server header) =====
    print("\n" + "=" * 60)
    print("Q04: 受害者操作系统 (HTTP Server headers)")
    for s in http_servers:
        print(f"  Server: {s}")
    
    # Also check responses from victim
    victim_responses_servers = set()
    for src_ip, dst_ip, status, headers, body, sport in http_responses:
        if src_ip == victim_ip:
            # Look for OS hints in headers
            if 'server' in headers.lower():
                victim_responses_servers.add(headers)
    
    # ===== Q05-Q06: 攻击工具 (User-Agent) =====
    print("\n" + "=" * 60)
    print("Q05-Q06: HTTP User-Agent (所有)")
    for ua in sorted(http_user_agents):
        print(f"  UA: {ua}")
    
    # ===== Q07: phpliteadmin登录点 =====
    print("\n" + "=" * 60)
    print("Q07: phpliteadmin相关请求")
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if 'phpliteadmin' in uri.lower() or 'phpliteadmin' in body.lower():
            print(f"  [{method}] {uri} (from {src_ip} -> {dst_ip}:{dport})")
            if body and len(body) < 500:
                print(f"    body: {body}")
    
    # ===== Q08: phpliteadmin密码 (POST body) =====
    print("\n" + "=" * 60)
    print("Q08: 含password的POST请求")
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if method == 'POST' and ('password' in body.lower() or 'passwd' in body.lower() or 'login' in uri.lower()):
            print(f"  POST {uri} from {src_ip}")
            if len(body) < 1000:
                print(f"    body: {body}")
    
    # ===== Q09: phpinfo文件名 =====
    print("\n" + "=" * 60)
    print("Q09: phpinfo相关")
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if 'phpinfo' in uri.lower() or 'phpinfo' in body.lower():
            print(f"  [{method}] {uri} from {src_ip}")
            if body and len(body) < 500:
                print(f"    body: {body}")
    # Also check responses containing phpinfo
    for src_ip, dst_ip, status, headers, body, sport in http_responses:
        if 'phpinfo' in body.lower()[:2000]:
            print(f"  Response from {src_ip}:{sport} status={status} contains phpinfo (body len={len(body)})")
    
    # ===== Q10: payload下载文件名 =====
    print("\n" + "=" * 60)
    print("Q10: 从攻击机下载的文件 (攻击者作为HTTP server的请求)")
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if dst_ip == attacker_ip and method == 'GET':
            print(f"  GET {uri} -> {dst_ip}:{dport} from {src_ip}")
    # Also: wget/curl in any TCP stream
    print("\n  从受害者发起到攻击者的HTTP请求:")
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if src_ip == victim_ip and dst_ip == attacker_ip:
            print(f"  [{method}] {uri} -> {dst_ip}:{dport}")
    
    # ===== Q11: 反弹shell =====
    print("\n" + "=" * 60)
    print("Q11: 反弹shell (受害者→攻击者 的TCP连接)")
    reverse_conns = collections.Counter()
    for (src_ip, dst_ip, sport, dport), data_list in tcp_streams.items():
        if src_ip == victim_ip and dst_ip == attacker_ip:
            reverse_conns[(dst_ip, dport)] += len(data_list)
    for (ip_addr, port), cnt in reverse_conns.most_common(10):
        print(f"  {victim_ip} -> {ip_addr}:{port}  ({cnt} data segments)")
    
    # Also check attacker→victim non-HTTP connections
    print("\n  攻击者→受害者 非标准端口连接:")
    atk_conns = collections.Counter()
    for (src_ip, dst_ip, sport, dport), data_list in tcp_streams.items():
        if src_ip == attacker_ip and dst_ip == victim_ip and dport not in (80, 443, 8080):
            atk_conns[(dport)] += len(data_list)
    for port, cnt in atk_conns.most_common(10):
        print(f"  {attacker_ip} -> {victim_ip}:{port}  ({cnt} segments)")
    
    # ===== Q12: Python版本 =====
    print("\n" + "=" * 60)
    print("Q12: Python版本 (从UA/Server/流量中提取)")
    for ua in http_user_agents:
        if 'python' in ua.lower():
            print(f"  UA含Python: {ua}")
    # Check TCP streams for Python version strings
    for (src_ip, dst_ip, sport, dport), data_list in tcp_streams.items():
        if src_ip == attacker_ip or dst_ip == attacker_ip:
            for ts, data in data_list:
                text = data.decode('utf-8', errors='replace')
                if 'python' in text.lower() and 'version' in text.lower():
                    snippet = text[:300]
                    print(f"  Stream {src_ip}:{sport}->{dst_ip}:{dport}: {snippet}")
    
    # ===== Q13: 网站框架 =====
    print("\n" + "=" * 60)
    print("Q13: 网站框架")
    framework_hints = set()
    for src_ip, dst_ip, status, headers, body, sport in http_responses:
        if src_ip == victim_ip:
            if 'x-powered-by' in headers.lower():
                framework_hints.add(f"X-Powered-By in headers: {headers}")
            # Check for framework hints in body
            for fw in ['thinkphp', 'laravel', 'django', 'flask', 'wordpress', 'drupal']:
                if fw in body.lower()[:3000]:
                    framework_hints.add(f"Framework hint: {fw} in response body")
            for fw in ['thinkphp', 'laravel', 'django', 'flask']:
                if fw in headers.lower():
                    framework_hints.add(f"Framework hint: {fw} in headers")
    for hint in framework_hints:
        print(f"  {hint}")
    
    # Check cookies for framework
    print("  Cookie/header框架线索:")
    for src_ip, dst_ip, status, headers, body, sport in http_responses:
        if 'think' in headers.lower() or 'laravel' in headers.lower():
            print(f"    {headers[:200]}")
    
    # ===== Q14: 数据库密码 =====
    print("\n" + "=" * 60)
    print("Q14: 数据库密码 (在流量中搜索)")
    db_keywords = ['db_pass', 'db_password', 'database_password', 'mysql_password', 
                   'DB_PWD', 'root_password', "'password'", '"password"', 'passwd']
    for src_ip, dst_ip, status, headers, body, sport in http_responses:
        for kw in db_keywords:
            if kw.lower() in body.lower():
                # Find context around the keyword
                idx = body.lower().find(kw.lower())
                context = body[max(0, idx-50):idx+100]
                print(f"  Found '{kw}' in response from {src_ip}:{sport}")
                print(f"    context: {context}")
    # Also search in request bodies
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        for kw in db_keywords:
            if kw.lower() in body.lower():
                idx = body.lower().find(kw.lower())
                context = body[max(0, idx-50):idx+100]
                print(f"  Found '{kw}' in {method} {uri}")
                print(f"    context: {context}")
    
    # ===== Q15: weevely上传端口 =====
    print("\n" + "=" * 60)
    print("Q15-Q16: weevely相关")
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if 'weevely' in uri.lower() or 'weevely' in body.lower():
            print(f"  [{method}] {uri} port={dport} from {src_ip}")
            if body and len(body) < 500:
                print(f"    body: {body}")
    
    # Look for weevely-style traffic (base64 encoded PHP eval)
    print("\n  疑似weevely通信 (含eval/base64的HTTP):")
    weevely_count = 0
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if src_ip == attacker_ip and ('eval' in body or 'base64' in body or 'assert' in body):
            weevely_count += 1
            if weevely_count <= 5:
                print(f"  [{method}] {uri} port={dport}")
                print(f"    body (first 300): {body[:300]}")
    if weevely_count > 5:
        print(f"  ... and {weevely_count - 5} more")
    
    # Look for weevely POST with cookie-based payload
    print("\n  疑似weevely (cookie载荷 POST):")
    wv_count = 0
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if method == 'POST' and src_ip == attacker_ip:
            # weevely sends data in cookies and short POST body
            if len(body) > 10 and len(body) < 5000:
                # Check for weevely patterns
                if re.search(r'[A-Za-z0-9+/=]{20,}', body):
                    wv_count += 1
                    if wv_count <= 3:
                        print(f"  POST {uri} port={dport} body_len={len(body)}")
                        print(f"    body: {body[:200]}")
    
    # ===== Summary of all unique HTTP request URIs =====
    print("\n" + "=" * 60)
    print("附录: 所有HTTP请求URI (去重, 前100)")
    uri_set = set()
    for src_ip, dst_ip, method, uri, host, body, dport in http_requests:
        if src_ip == attacker_ip:
            uri_set.add(f"[{method}] {uri} :{dport}")
    for i, u in enumerate(sorted(uri_set)):
        if i >= 100:
            print(f"  ... total {len(uri_set)} unique URIs")
            break
        print(f"  {u}")
    
    # HTTP responses with status 200 containing interesting content
    print("\n" + "=" * 60)
    print("附录: 受害者HTTP 200响应中含关键词的")
    keywords_check = ['phpinfo', 'password', 'passwd', 'root', 'database', 'shell', 
                      'weevely', 'eval', 'base64_decode', 'system(', 'exec(']
    for src_ip, dst_ip, status, headers, body, sport in http_responses:
        if src_ip == victim_ip and status == '200':
            for kw in keywords_check:
                if kw in body.lower()[:5000]:
                    print(f"  Response :{sport} contains '{kw}' (body_len={len(body)})")
                    idx = body.lower().find(kw)
                    print(f"    snippet: {body[max(0,idx-30):idx+80]}")
                    break

    print("\n" + "=" * 60)
    print("分析完成！")

if __name__ == '__main__':
    main()
