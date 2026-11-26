---
name: add-a-device
description: Brings a new device or service into the house - identifies it from its label, a photo or what Home Assistant discovered, finds the right integration, adds a discovered one that needs only a yes or gives the owner the exact pairing or sign-in steps, names it the way people say it, puts it in its room, makes it available to voice and assistants if wanted, tests it with read-back, and records it in memory. Use when someone says "I bought a new light", "add this plug", "connect my speaker" or "set up this account".
---

# Add a device

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the device shows up under the name people use, in the right room, does what it is
asked with the change read back, and memory knows how this kind of device is added.

**Stance:** you are the implementation specialist. Work out what it is and what it needs before
asking. Give the owner only the steps that need their hands or their sign-in.

## Hard rules

- Never type, read out or store a password, code or key. The owner enters them in Home Assistant
  or the maker's app.
- Checkpoint (`backup`) before adding an integration to a house that already works.
- One device at a time: add, name, place, test, then the next.
- Locks, alarms, garage doors and heating: add and name them, but test by reading only unless
  the owner says yes to one action.
- Use a camera or photo only with the owner's yes for this; never keep the image.

## Memory

Start: `memory_read` `house.md` (rooms, naming habits, how things connect), `owner.md`, and
`playbooks/` for this brand or connection type. End: update them (phase 6).

## Phase 1: identify it

1. Ask what it is and which room it is for, unless they said.
2. Get the maker and model: from the label (a photo, or what you can see, with their yes), or ask.
3. Find how it connects (home Wi-Fi, a low-power mesh through a hub, short-range radio, cable, or
   a maker's account) and what it needs: a hub the house has or lacks, a band, an app.
4. Look up the integration for it in Home Assistant's own documentation. Offline: say so and
   use what Home Assistant discovers.

Exit: maker, model, connection type, the integration, and anything missing (say it plainly and stop).

## Phase 2: get it on

1. Power it and put it in pairing mode: give the maker's steps, at most 3 at a time.
2. If it joins the home network through the maker's app, the owner does that first.
3. Check whether Home Assistant discovered it: `discovered` op=list (its Discovered list), and
   `house_map` everything=true in case it was already added.
4. Discovered, and its `needs` is confirm (just a yes): say which device it is ("BulbCo found
   Porch Bulb, model A19. Add it?"), and on the owner's yes, `discovered` op=accept with
   confirmed=true. A lock, alarm, door, gate, heating or valve needs that yes for this device by
   name. It returns change_id: "undo that" removes it.
5. Anything else (fields to fill, a sign-in, a code, a choice, or not discovered at all): the
   owner adds it in Home Assistant (Settings → Devices & services → Discovered, or Add
   integration) and signs in there if it asks. Give the steps for that integration, at most 3.

Exit: Home Assistant lists the device. If it never appears: `device-diagnosis`; if the evidence
says Wi-Fi (won't join, joins then drops): `wifi-diagnosis`.

## Phase 3: name and place

1. Name it as people will say it, following the house's habit ("Den Reading Lamp").
   `registry_edit` op=rename.
2. Put it in its room: `registry_edit` op=set_area (op=create_area first if the room is new).
3. If they want it by voice or from an assistant, tell them where to turn that on for this device.

## Phase 4: test

`act` a harmless action (off, then on), each `CHECKED`; put it back. For a sensor, read its value
and ask if it looks right. For guarded devices, read only.

## Phase 5: next (offer once)

"Want it to do something by itself?" If yes: `routines`.

## Phase 6: save what was learned

- `house.md`: the device, its room, how it connects, the date.
- `playbooks/<brand or connection type>.md`: how it pairs, what it needs, quirks, the integration.
- `log.md`: date, what was added, the test result.

Then `log_run`.

## Hands off to / called from

Won't appear or misbehaves: `device-diagnosis`. Wi-Fi evidence: `wifi-diagnosis`. Automate it: `routines`.
Called from `improve-home` after a purchase. Called from `welcome` (stage 2), once per waiting
device, with the name and room the owner already agreed: don't ask them again.

## Words for the owner

- Pairing: "Plug it in near where it will live. Then <the maker's steps>. Tell me what its light does."
- Sign-in: "Home Assistant will ask you to sign in to <maker>. Do that there; don't send me the password."

## Report

What was added, its name and room, the test result, and anything it still needs. No ids unless asked.
