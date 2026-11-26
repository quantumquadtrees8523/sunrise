"""ha_ws.py - send Home Assistant websocket commands from INSIDE the HA container.

The token is read from stdin (first line), never from argv, env or a file:

  box-secret get ha-token | ssh <box> "docker exec -i <ha-container> python3 /tmp/ha_ws.py '<json list>' [filter]"

<json list> is a list of command dicts without "id", e.g.
  '[{"type":"hacs/repositories/add","repository":"owner/repo","category":"integration"}]'
[filter] (optional): when a result is a list, keep only items whose JSON contains this
lowercase substring, trimmed to the HACS repository fields that matter.

Uses aiohttp, which the official HA image already has. max_msg_size=0 because
hacs/repositories/list is ~4.9 MB, over aiohttp's 4 MB default.
"""
import asyncio, json, sys
import aiohttp

KEYS = ("id", "full_name", "category", "installed", "available_version",
        "installed_version", "custom", "new")

async def main():
    token = sys.stdin.readline().strip()
    cmds = json.loads(sys.argv[1])
    flt = sys.argv[2].lower() if len(sys.argv) > 2 else None
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("http://127.0.0.1:8123/api/websocket", max_msg_size=0) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            r = await ws.receive_json()
            if r.get("type") != "auth_ok":
                print("AUTH FAILED", r.get("type")); sys.exit(1)
            for i, c in enumerate(cmds, 1):
                await ws.send_json({"id": i, **c})
                while True:
                    m = await ws.receive_json()
                    if m.get("id") == i and m.get("type") == "result":
                        break
                res = m.get("result") if m.get("success") else m.get("error")
                if flt and isinstance(res, list):
                    res = [{k: x.get(k) for k in KEYS} for x in res if flt in json.dumps(x).lower()]
                print(c["type"], "OK" if m.get("success") else "FAIL", json.dumps(res)[:2000])

asyncio.run(main())
