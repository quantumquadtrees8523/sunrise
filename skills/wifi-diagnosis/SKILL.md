---
name: wifi-diagnosis
description: Finds out why Wi-Fi devices in this house keep dropping or won't come back, and fixes it in order - what is off on purpose, measure from the home network, find what the failing devices share, read the router with the owner signed in, research this router and device pair, one change at a time from a fresh scan, verify the same way, then save what was learned to memory. Use when several devices are unavailable, lights or speakers keep going offline, things drop after a router or Wi-Fi change, or someone asks "why does my Wi-Fi keep dropping these?".
---

# Wi-Fi diagnosis

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the devices that should be online are online and stay online; the owner knows the
cause, with its evidence, and what is still unproven; the house's memory holds what was learned.

**Stance:** you are the implementation specialist. Measure first. Bring a cause, its evidence and
one recommended action. Ask the owner only for hands, eyes and sign-ins. When `device-diagnosis`
sent you here, start from what it already measured and hand the result back to it.

## Hard rules

- The router: only as the rubric's S1 allows. The owner signs in themselves and says yes to each
  change. Write down the old value before every change. Never type, read out or store a password.
- One change, then the same measurement again. Several changes at once hide which one worked.
- Date every observation. Scans, channel scores and device lists go stale: take a fresh one
  before you act on it.
- Every Wi-Fi change drops devices for a while. Say so first, then wait 3 to 10 minutes before judging.
- Never reset a router or a device to factory settings. Pairing a device again is the owner's job, in its app.
- Count only devices that are meant to be on. A device unplugged on purpose is not a failure.

## Memory

Start: `memory_read` `house.md`, `owner.md`, `log.md` and any `playbooks/` file for this router
or these device brands. Use them to skip what is already known, and re-check what could have changed.
End: update all of them (phase 8).

## Phase 0: ground truth (ask once, up front)

1. Which devices are off, unplugged or removed on purpose?
2. Which wall switches feed which lights, and are they on now?
3. What changed lately: router, provider visit, Wi-Fi name or password, new devices, a setting?
4. What do they notice dropping, and since when?

Exit: a list of devices that should be online, and the test device (from `house.md`, else ask).

## Phase 1: measure from the home network

1. `network_check`: does the router answer, is the internet up, how many Wi-Fi devices are
   unreachable, signal where devices report it. If the house's own link is bad, fix that first.
2. `diagnose_device` with no target: each unreachable device gets a cause (moved to a new address,
   answering but not loaded, off the network, weak signal).
3. Fix what software can fix now (`fix_device`), then diagnose again.
4. If you have a shell on the home network, measure loss per device: about 40 small requests each,
   a quarter second apart; record how many answered. This is the baseline you compare against later.
5. Trust a direct answer from the device over Home Assistant's "unavailable", which lags.

Exit: every expected device is one of: fine, flaky (answers sometimes), off the network, or wrong address.

## Phase 2: find what the failing devices share

Sort failing against healthy by: Wi-Fi band (many small devices use only 2.4 GHz), brand, room or
distance from the router, wall switch or circuit, and when they dropped (together, or one by one).
The attribute that cleanly separates bad from good is the lead. If nothing separates them, say so.

## Phase 3: read the router

The owner opens the router's page or app and signs in; you read. If you have no browser, ask for
what follows in at most 3 steps at a time. Collect, with the time you read it:

- model, firmware and how long since it restarted
- the device list, with each device's band and whether it is connected
- how the bands are named (one shared name with steering, or separate), and the security mode
- the 2.4 GHz channel, its width, whether it is automatic, and a neighbour scan with its date
- any log of devices joining and leaving, and of address requests

Learn what each number on this router means before you rely on it (a "health" figure is often
how crowded the channel is, not whether the hardware works). Save the page paths, quirks and
meanings to `playbooks/<router>.md` as you go.

## Phase 4: research this pair

Search for this router model with these device brands and the symptom. Prefer the makers' own
pages; in forums look for a fix that recurs, not a single post. Keep each source in one line with
what it supports. Offline: say you can't look it up and go on with what you measured.

## Phase 5: hypotheses

Hold several until evidence rules them out. Say which evidence you have for the one you pick.

| Cause | Evidence for | Evidence against |
|---|---|---|
| No power | whole switch or circuit out; the router has never seen them since | some on that switch are fine |
| Wrong address in Home Assistant | device answers elsewhere on the network | it answers nowhere |
| Wi-Fi settings changed (name, password, security, band steering) | devices never rejoin, even beside the router; a recent change | they join, then drop |
| Crowded band | fresh scan shows many neighbours and low scores; partial loss; devices join after a power cycle, then fall away over minutes | a clean scan; nothing joins at all |
| Weak signal | only the far devices; low signal reported | near devices fail too |
| Router radio or firmware fault | nothing on that band joins, even close; very long uptime; a restart helps briefly | other devices on that band are fine |
| The phone, not the house | one phone can't join or pair while the house's own checks pass | several clients fail |

## Phase 6: act, lowest rung that fits the evidence

| # | Action | When | Cost | Who |
|---|---|---|---|---|
| 1 | Switch on; power-cycle once (off 10 s, on, leave on); wait | always first | none | owner |
| 2 | Point Home Assistant at the device's new address | wrong address | none | you (`fix_device`) |
| 3 | Restart the router | long uptime, or after a big change | internet out for minutes | owner, or you with a yes |
| 4 | Channel from a fresh scan (automatic, or the least crowded), narrow width | crowded band | every device drops briefly | owner, or you with a yes |
| 5 | Fixed addresses for smart devices | addresses keep moving | low | owner, or you with a yes |
| 6 | Move devices that can use another band off the crowded one | they share it | set up again in their app | owner |
| 7 | A separate network for smart devices | main Wi-Fi settings keep changing | pair every device again | owner |
| 8 | An access point near the devices, wired back | crowding or range persists | hardware | owner |
| 9 | Replace the router | evidence of a fault only | slow | owner |

A power-cycle is one off and one on. Flicking a smart bulb several times can put it in pairing mode.

## Phase 7: verify, then soak

1. The same measurements as phase 1, compared with the baseline.
2. The router's device list again.
3. End to end: the test device off, then on, with `act`; each must be `CHECKED`. Put it back.
4. Check again after a day and after three days before calling the cause proven.

## Phase 8: save what was learned

- `house.md`: what is off on purpose, switches and what they feed, the test device, baselines (dated).
- `playbooks/<router>.md`: model, firmware, page paths, what its numbers mean, quirks, settings before and after.
- `playbooks/<brand>.md`: band, how it pairs, how it behaves after a power cycle, how to ask it directly.
- `log.md`: date, symptoms, evidence, each change and its result, the cause, proven or not, follow-ups.
- `owner.md`: anything they told you about how they want this handled.

Then `log_run`.

## Words for the owner

- Sign in: "Open your router's page or app and sign in. I'll read and change nothing until you say yes."
- Power cycle: "Turn the switch off, wait 10 seconds, turn it on and leave it. Just once."
- Before a change: "This drops your smart devices for a few minutes. It was X, I'd set it to Y. OK?"

## Report

The state (which are back, by name), the cause in one sentence with its evidence, the one next
step, and what is still unproven. No addresses or ids unless asked.
