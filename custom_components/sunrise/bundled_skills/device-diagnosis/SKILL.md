---
name: device-diagnosis
description: Finds out why a device is unavailable, flaky, slow or doing the wrong thing, and fixes it in order - what is off on purpose, read Home Assistant's records, find the failing layer (power, network, the maker's service, the device, Home Assistant's own setup), fix what software can, give the owner exact steps for the rest, verify by reading back, then save what was learned to memory. Looks at the hardware itself when the owner allows a camera or sends a photo. Use when a device can't be reached, responds late, shows the wrong state, or someone asks "why isn't this working?".
---

# Device diagnosis

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the device works and stays working, or the owner knows exactly what it needs; they
know the cause, with its evidence, and what is still unproven; memory holds what was learned.

**Stance:** you are the implementation specialist. Check before you ask. Bring a cause, its
evidence and one recommended action. Ask the owner only for hands, eyes and sign-ins.

## Hard rules

- A device that is off on purpose is not a failure. Ask before you count it.
- One change, then the same check again. Date every observation; re-read anything that could have changed.
- `backup` before changing Home Assistant's own setup (registry, an integration, an address).
- Never reset a device to factory settings, remove it, or pair it again yourself: those are the
  owner's steps, and only after the cheaper rungs failed.
- Locks, alarms, garage doors and heat: diagnose by reading only. No test action without a yes in the moment.
- Never type, read out or store a password or sign-in. The owner signs in to the maker's app or page.
- Cameras and photos: only with the owner's yes for this check. Say what you looked at. Never
  store an image, and never describe people.

## Memory

Start: `memory_read` `house.md`, `owner.md`, `log.md` and any `playbooks/` file for this brand or
connection type. Skip what is known; re-check what could have changed. End: update them (phase 7).

## Phase 0: ground truth (ask once)

1. Is it off, unplugged or removed on purpose? Is its wall switch on?
2. What exactly is wrong: can't be reached, drops now and then, slow, wrong state, wrong action?
3. Since when, and what changed around then (power cut, router, an update, a new device, a moved device)?

Exit: the device(s) in question, the symptom in one sentence, and the test device if a different
one is needed (from `house.md`, else ask once).

## Phase 1: read the records

1. `house_map`: the device's state, room, how it connects, its integration.
2. `diagnose_device` with the device as target: last seen, the integration's state, its maker,
   model and how it connects, its address, recent errors in the log, and whether it answers on the
   network. A `tailor` line means Sunrise has no helper for this kind: the steps you give come
   from this maker and model's own pages (phase 3), not from a general guess.
3. `audit`: is it disabled, renamed, duplicated, without a room, or one of many dead things?
4. `network_check`: is the house's own link and router fine?
5. Others like it: are devices of the same brand, connection type, room or switch failing too?

Exit: you know whether it is one device or a group, and what Home Assistant last heard from it.

## Phase 2: look at the hardware (when you can)

If the owner allows a camera that sees it, sends a photo, or you can otherwise see the room, use
it as evidence and say how sure you are:

- power and status lights: on, off, colour, steady or blinking (count the pattern)
- a bulb: lit, dark, or pulsing slowly (often pairing mode)
- cables seated, the wall switch position, a tripped outlet, a dead battery cover
- the label: maker, model, version. Use it for the research in phase 3.

Without sight, ask the same things, one precise question at a time ("Is the small light on the
plug on, off or blinking?").

## Phase 3: find the failing layer

Hold several until evidence rules them out. Look up this model's status lights and known faults
on the maker's own pages; offline, say you can't and go on with what you measured.

| Layer | Evidence for | Evidence against |
|---|---|---|
| Power or physical | no lights on it; everything on that switch or outlet is out; battery old | it answers on the network |
| Network: Wi-Fi | several Wi-Fi devices failing, weak signal, drops after rejoining | wired, or others beside it on the same band are fine |
| Network: wired | link light off; other devices on that cable or switch out | link light on, router lists it |
| Network: mesh radio (low-power mesh, short-range radio) | the coordinator or a relay device is down; far devices fail first | near devices on the same mesh fail too while the coordinator is fine |
| The maker's service or account | integration says sign-in expired or refused; all of that brand fail at once; maker reports an outage | the device is controlled locally and answers |
| The device itself | powered, in range, others like it fine; error lights; fails after a firmware update | it works from the maker's app |
| Home Assistant's setup | it answers on the network but is disabled, renamed, at an old address, or its integration failed to load | Home Assistant's records are right |

If the evidence says Wi-Fi, stop here and run `wifi-diagnosis`; come back to phase 6 with its result.

## Phase 4: fix what software can

Lowest rung that fits the evidence. After each, run phase 1's check again.

| # | Action | When | Who |
|---|---|---|---|
| 1 | Point Home Assistant at the device's new address | it answers elsewhere | you (`fix_device`) |
| 2 | Reload its integration | integration failed to load, or stale | you (`fix_device`) |
| 3 | Re-enable or correct the entity or device record | disabled, renamed, wrong room | you (`registry_edit`, after `backup`) |
| 4 | Restart Home Assistant | several integrations stale after an update | you, with a yes |

## Phase 5: steps for the owner (at most 3 at a time)

| # | Action | When |
|---|---|---|
| 5 | Switch on; power-cycle once (off 10 s, on, leave on); new battery | no power, or stuck |
| 6 | Sign in again in the integration or the maker's app | sign-in expired |
| 7 | Move it, or its relay, closer; reseat the cable | weak link |
| 8 | Update its firmware in the maker's app | known fault fixed by an update |
| 9 | Pair it again | it forgot the network, after 5 failed |
| 10 | Replace it | evidence of failed hardware only |

A power-cycle is one off and one on. Flicking some devices several times resets them.

## Phase 6: verify, then soak

1. Phase 1's checks again, compared with before.
2. End to end: `act` on the device (off, then on, or its own harmless action); each must be
   `CHECKED`. Put it back as you found it. For guarded devices, read only.
3. A flaky device is not fixed until it has held for a day. Say so, and check again then.

## Phase 7: save what was learned

- `playbooks/<brand or connection type>.md`: what its lights mean, how it behaves after a power
  cycle, how to pair it, known faults, sources.
- `house.md`: what is off on purpose, switches and what they feed (dated).
- `log.md`: date, symptom, evidence, each step and its result, the cause, proven or not, follow-ups.
- `owner.md`: how they want this kind of thing handled.

Then `log_run`.

## Hands off to / called from

Wi-Fi evidence: `wifi-diagnosis`. A change made things worse: `undo`.
Called from `add-a-device`, `routines`, `improve-home`, `learn-the-house` and `welcome`.

## Words for the owner

- Camera: "May I look at it through the <room> camera, just for this check? I won't keep the picture."
- Power cycle: "Turn it off at the switch, wait 10 seconds, turn it on and leave it. Just once."
- Sign-in: "Open <the maker's app> and sign in again. Tell me when it's done; don't send me the password."

## Report

The state now (by name), the cause in one sentence with its evidence, the one next step, and
what is still unproven. No addresses or ids unless asked.
