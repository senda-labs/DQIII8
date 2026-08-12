#!/bin/bash
# Monitors NS propagation for januskeys.es
# When CF NS detected: enables Email Routing + HSTS preload + self-removes
LOG="/var/log/januskeys_ns_watch.log"
FLAG="/tmp/januskeys_ns_propagated.flag"
ZONE_ID="ee31b79571f612f275f34fa5bf6564d6"
ACCOUNT_ID="49d5e78db0ddb976dcfaf39ee4e8c303"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

if [ -f "$FLAG" ]; then
  echo "$(ts) Already done — exiting" >> "$LOG"
  exit 0
fi

NS_RESULT=$(dig NS januskeys.es @8.8.8.8 +short 2>/dev/null)
echo "$(ts) NS check: $NS_RESULT" >> "$LOG"

if ! echo "$NS_RESULT" | grep -q "cloudflare.com"; then
  echo "$(ts) Not yet propagated." >> "$LOG"
  exit 0
fi

echo "$(ts) PROPAGATED! Starting post-propagation setup..." >> "$LOG"

# Use CDP to call CF API (browser session auth)
python3 - <<'PYEOF' >> "$LOG" 2>&1
import asyncio, json, subprocess, sys

async def cf_api(ws_url, expr):
    import websockets
    async with websockets.connect(ws_url) as ws:
        cmd = {"id": 1, "method": "Runtime.evaluate",
               "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}
        await ws.send(json.dumps(cmd))
        resp = await asyncio.wait_for(ws.recv(), timeout=20)
        d = json.loads(resp)
        return d['result']['result'].get('value', 'no_value')

async def main():
    import urllib.request
    try:
        pages = json.loads(urllib.request.urlopen('http://localhost:9333/json', timeout=5).read())
    except Exception as e:
        print(f"CDP unavailable: {e}")
        return

    # Find CF dashboard tab
    cf_tab = next((p for p in pages if 'dash.cloudflare.com' in p.get('url', '')), None)
    if not cf_tab:
        print("No CF dashboard tab found")
        return

    ws_url = f"ws://localhost:9333/devtools/page/{cf_tab['id']}"
    ZONE_ID = "ee31b79571f612f275f34fa5bf6564d6"

    # 1. Enable Email Routing
    r = await cf_api(ws_url, f"""
(async () => {{
  const r = await fetch('/api/v4/zones/{ZONE_ID}/email/routing/enable', {{
    method: 'POST', credentials: 'same-origin',
    headers: {{'Content-Type': 'application/json'}}
  }});
  const d = await r.json();
  return JSON.stringify({{status: r.status, success: d.success, errors: d.errors}});
}})()
""")
    print(f"Email Routing enable: {r}")

    # 2. Create hola@ → Gmail routing rule
    r2 = await cf_api(ws_url, f"""
(async () => {{
  const r = await fetch('/api/v4/zones/{ZONE_ID}/email/routing/rules', {{
    method: 'POST', credentials: 'same-origin',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      name: 'hola alias',
      enabled: true,
      matchers: [{{ type: 'literal', field: 'to', value: 'hola@januskeys.es' }}],
      actions: [{{ type: 'forward', value: ['ikermartiinsv@gmail.com'] }}]
    }})
  }});
  const d = await r.json();
  return JSON.stringify({{status: r.status, success: d.success, errors: d.errors}});
}})()
""")
    print(f"Email routing rule: {r2}")

asyncio.run(main())
PYEOF

# HSTS Preload submission
echo "$(ts) Submitting HSTS preload..." >> "$LOG"
RESPONSE=$(curl -s -X POST "https://hstspreload.org/api/v2/submit?domain=januskeys.es" \
  -H "Content-Type: application/json" 2>&1)
echo "$(ts) HSTS submit: $RESPONSE" >> "$LOG"

# Mark done and self-remove from crontab
touch "$FLAG"
echo "$(ts) All done. Removing cron." >> "$LOG"
crontab -l 2>/dev/null | grep -v "januskeys_ns_watch" | crontab -
