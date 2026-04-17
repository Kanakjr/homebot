---
name: network-admin
description: Administer the TP-Link Deco mesh router directly -- list connected clients by MAC/vendor, inspect mesh nodes, and reboot nodes. Also use when the user asks to "pin", "reserve", "give a fixed IP" to a device -- the tool returns the correct mobile-app workflow. Use when the user asks "which devices are on wifi", "where is my <device>", "reboot the mesh".
tags: [network, deco, dhcp, reservation, mac, wifi, admin]
---

# Deco Network Admin

Direct control of the TP-Link Deco mesh via its admin RPC (separate from the read-only HA entities in `network-diagnostics`). Credentials are pre-configured on the server -- never ask the user for them.

## Available tools

- `deco_list_clients(deco_mac="default")` -- every connected client with name, MAC, IP, online flag, and which mesh node it's on.
- `deco_list_mesh_nodes()` -- the Deco nodes themselves (router + satellites) with role (master/slave), nickname, uplink.
- `deco_reboot_nodes(macs)` -- reboot one or more mesh nodes. Roughly 60s downtime; always confirm first via `offer_choices`.
- `deco_reservation_help(requested_ip, mac, name)` -- returns the mobile-app workflow for pinning an IP (see limitation below).

## Hard limitation: DHCP reservations are mobile-app only

The Deco web admin deliberately hides DHCP address reservations -- the feature is exposed only through the Deco mobile app and TP-Link cloud. We probed 165+ local endpoint combinations and none are available. This is a firmware restriction, not a bug.

When the user asks to pin / reserve / fix an IP:

1. Use `deco_list_clients()` first to grab the device's current MAC and IP.
2. Call `deco_reservation_help(requested_ip, mac, name)` and relay its `instructions` verbatim to the user (they'll see the exact steps for the Deco app).
3. Offer the alternative: configure a static IP inside the device's own app (WiZ app, Smart Life / Tuya app, etc.).

Do NOT claim the reservation was made -- be honest that the user has to tap through the Deco app.

## Core workflows

### Find a newly added smart-home device

1. Ask the user for a hint (name/brand/colour/type) if it isn't obvious.
2. Call `deco_list_clients()` and match on MAC OUI or hostname (e.g. `98-77-D5-*` is Signify/WiZ; `FC-67-1F-*` is Tuya).
3. Report `name | mac | ip | online` in a compact line.

### Reboot a mesh node

1. Call `deco_list_mesh_nodes()` to show the user which nodes are live.
2. Use `offer_choices` to confirm which node (or all).
3. Call `deco_reboot_nodes(macs)`; warn about ~60s downtime.

### Known devices worth pinning (manual, via Deco app)

| Device | MAC | Current IP | Why pin it |
| --- | --- | --- | --- |
| WiZ Table Lamp | `98:77:D5:D7:9A:7A` | 192.168.68.111 | HA WiZ integration stability |
| Homemate RGB Strip (Tuya) | `FC:67:1F:F1:EA:90` | 192.168.68.114 | LocalTuya / HA auto-discovery |

## Response style

- Telegram: 2-6 lines. No raw JSON dumps.
- For client lists, summarise: "18 clients online. 2 are Decos, 5 phones/laptops, 11 smart-home gadgets. Target found: <name> @ <ip>."
- For reservations, keep instructions to 3 lines max; offer follow-up help after the user confirms the app steps.
- For failures, surface the tool response's `detail` -- usually pinpoints auth / IP / collision.
