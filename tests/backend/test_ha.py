"""Test Home Assistant connectivity: REST API + WebSocket."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import aiohttp
import websockets
import config


async def test_rest_api():
    print("=" * 60)
    print("1. Testing HA REST API")
    print("=" * 60)
    headers = {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}
    url = f"{config.HA_URL}/api/"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"   GET {url} -> {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"   Response: {data}")
            else:
                print(f"   ERROR: {await resp.text()}")
                return False

    url = f"{config.HA_URL}/api/states"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"\n   GET {url} -> {resp.status}")
            if resp.status == 200:
                states = await resp.json()
                print(f"   Total entities: {len(states)}")
                domains = {}
                for s in states:
                    d = s["entity_id"].split(".")[0]
                    domains[d] = domains.get(d, 0) + 1
                print("   By domain:")
                for d, c in sorted(domains.items()):
                    print(f"     {d}: {c}")

                print("\n   Sample entities:")
                for s in states[:10]:
                    name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
                    print(f"     {s['entity_id']}: {s['state']} ({name})")
            else:
                print(f"   ERROR: {await resp.text()}")
                return False
    return True


async def test_websocket():
    print("\n" + "=" * 60)
    print("2. Testing HA WebSocket")
    print("=" * 60)
    ws_url = config.HA_WS_URL
    print(f"   Connecting to {ws_url}")

    async with websockets.connect(ws_url) as ws:
        auth_required = json.loads(await ws.recv())
        print(f"   Auth required: {auth_required.get('type')}")

        await ws.send(json.dumps({"type": "auth", "access_token": config.HA_TOKEN}))
        auth_result = json.loads(await ws.recv())
        print(f"   Auth result: {auth_result.get('type')}")
        if auth_result.get("type") != "auth_ok":
            print(f"   ERROR: Auth failed: {auth_result}")
            return False

        await ws.send(json.dumps({"id": 1, "type": "get_states"}))
        result = json.loads(await ws.recv())
        entities = result.get("result", [])
        print(f"   get_states returned {len(entities)} entities")

        await ws.send(json.dumps({"id": 2, "type": "subscribe_events", "event_type": "state_changed"}))
        sub_result = json.loads(await ws.recv())
        print(f"   subscribe_events: {sub_result.get('type')} (success={sub_result.get('success')})")

        print("\n   Listening for state changes (5 seconds)...")
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                if msg.get("type") == "event":
                    data = msg["event"]["data"]
                    eid = data.get("entity_id", "?")
                    new = data.get("new_state", {}).get("state", "?")
                    old = data.get("old_state", {}).get("state", "?") if data.get("old_state") else "?"
                    print(f"     {eid}: {old} -> {new}")
        except asyncio.TimeoutError:
            print("   (no more events in 5s window)")

    return True


async def test_call_service_dry():
    print("\n" + "=" * 60)
    print("3. Testing HA service call (dry run - reading a sensor)")
    print("=" * 60)
    headers = {"Authorization": f"Bearer {config.HA_TOKEN}"}
    url = f"{config.HA_URL}/api/states/person.kanak"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"   person.kanak state: {data['state']}")
                print(f"   Attributes: {json.dumps(data.get('attributes', {}), indent=2, default=str)[:500]}")
            elif resp.status == 404:
                print(f"   person.kanak not found (try a different entity)")
                url2 = f"{config.HA_URL}/api/states"
                async with session.get(url2, headers={"Authorization": f"Bearer {config.HA_TOKEN}"}) as r2:
                    states = await r2.json()
                    persons = [s for s in states if s["entity_id"].startswith("person.")]
                    lights = [s for s in states if s["entity_id"].startswith("light.")]
                    if persons:
                        print(f"   Found persons: {[p['entity_id'] for p in persons]}")
                    if lights:
                        print(f"   Found lights: {[l['entity_id'] + '=' + l['state'] for l in lights[:5]]}")
            else:
                print(f"   ERROR: {resp.status} {await resp.text()}")
    return True


async def main():
    print(f"HA_URL:    {config.HA_URL}")
    print(f"HA_WS_URL: {config.HA_WS_URL}")
    print(f"HA_TOKEN:  {config.HA_TOKEN[:20]}...{config.HA_TOKEN[-10:]}")
    print()

    ok = True
    ok = await test_rest_api() and ok
    ok = await test_websocket() and ok
    ok = await test_call_service_dry() and ok

    print("\n" + "=" * 60)
    if ok:
        print("All HA tests passed.")
    else:
        print("Some tests FAILED - check output above.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
