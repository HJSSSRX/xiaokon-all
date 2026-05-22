"""Quick peek finding details to see if backfill source data is rich enough."""
import urllib.request, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

for role in ["mobile_analyst", "server_analyst"]:
    f = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8765/findings?from={role}").read())
    print(f"\n{'=' * 70}\n{role}: {len(f)} findings\n{'=' * 70}")
    for x in f:
        print(f"\n[{x.get('id')}] type={x.get('type','')} conf={x.get('confidence','')}")
        print(f"  summary: {x.get('summary','')}")
        details = x.get("details") or ""
        if details:
            print(f"  details: {details[:300]}{'...' if len(details) > 300 else ''}")
        else:
            print("  details: (empty)")
        if x.get("source"):
            print(f"  source: {x.get('source')}")
        if x.get("related_to"):
            print(f"  related_to: {x.get('related_to')}")
