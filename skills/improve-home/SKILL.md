---
name: improve-home
description: Finds how this house could work better with what it already has, and builds the ideas the owner picks - reads memory for their preferences, takes stock of every room's devices and how they are really used, finds what is still done by hand, what is owned but unused, what is missing and what needs tidying, proposes at most five ranked ideas each with evidence from this house, builds the chosen ones with a backup and a live test, and remembers what was accepted or declined. Use when someone asks "how can my home be smarter?", "what should I automate?", "what am I not using?" or "what should I buy next?".
---

# Improve the home

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** a short ranked list of improvements, each backed by evidence from this house; the
ones the owner picked are built, tested and reversible; memory knows what was accepted and declined.

**Stance:** you are the implementation specialist. Take stock yourself, then bring finished
ideas, not questions. You suggest; the owner decides.

## Hard rules

- Every idea cites evidence from this house (a count, a time, a device). No evidence, no idea.
- At most 5 ideas, ranked. Never pitch an idea that was already pitched, whatever the answer was.
- No upsell. Prefer what they own. When something must be bought, describe the capability, not a brand.
- Prefer options that work on the home network without a cloud service; say when one needs the internet.
- Nothing safety-related (locks, alarms, garage doors, heat, water, anything that leaves the house
  unlocked or unattended) is automated without an explicit yes to that exact behaviour.
- Building anything: `backup` first, dry run, live test with read-back, and it must be undoable.
- Respect quiet hours and anything `owner.md` says they don't want.

## Memory

Start: `memory_read` `owner.md` (preferences, dislikes, budget, who lives here), `house.md`,
`log.md`; and `suggestions` op=list for every idea already pitched. End: update them (phase 6).

## Phase 1: take stock

1. `house_map`: every room, its devices and what each can do (dim, colour, temperature, sense
   motion, measure power, play sound).
2. `usage` (14 days, 30 if quiet): what is switched by hand, when, how often; what never changes.
3. `audit`: what is dead, unnamed, duplicated, without a room; noisy integrations.
4. The existing automations, scenes and scripts (from `house_map`), and when each last ran.

Exit: a per-room picture: what is there, what it can do, how it is used, what already runs by itself.

## Phase 2: find the openings

Look for each kind, and write down the evidence as you go.

| Kind | What to look for | Evidence to cite |
|---|---|---|
| Done by hand, on a pattern | the same thing switched at about the same time most days, or always together | "the hall light was turned off by hand at about 23:10 on 11 of 14 nights" |
| Owned but unused | sensors no automation reads; lights that can change colour or warmth and never do; presence, power or weather data nothing uses; scenes never run | the capability and zero uses |
| Missing | a room with lights but no sensor or switch control; one device everything depends on; no way to do it by voice or from one place | the room and what it lacks |
| Fragile | devices often unavailable; an automation that failed recently; weak links | counts from `audit` and `usage` |
| Untidy | unclear or duplicate names, things with no room, no recent backup, updates waiting | the list |

Exit: a list of candidate ideas, each with its evidence.

## Phase 3: rank and propose

Drop anything in `suggestions`, anything `owner.md` rules out, and anything without evidence.
Rank by benefit to the household over effort; fragile and untidy items that block others go first.
Present at most 5, each in this shape:

- **What it does for you**, in one sentence, in plain words.
- **Why, here:** the evidence.
- **Effort:** now, with what you own / a small purchase / a project.
- **Risk:** what could annoy or go wrong, and how it is undone.
- **Can I do it now?** yes / yes after you buy X / steps for you.

Record each with `suggestions` op=record (idea, status pitched, evidence) as you pitch it. Then ask which to do.

## Phase 4: build what they picked (no purchase needed)

For each, one at a time:

1. `backup`, and confirm it.
2. A "do X when Y": run `routines` (it checks, saves, tests and puts things back).
3. A repeatable job for the agent rather than an automation: run `build-a-skill`.
4. A failed step means fix or stop, never "leave it on anyway".

For tidy-ups use `registry_edit`, one approved change at a time; each can be undone with `undo`.
For fragile devices, run `device-diagnosis`.

## Phase 5: what to buy (when they picked one that needs it)

Give a spec by capability: what it must sense or control, how it must connect to work with what
they have (name the connection types already in the house), that it works locally, where it goes,
and what it unlocks. Offer to set it up when it arrives. No brands unless they ask.

## Phase 6: save what was learned

- `suggestions` op=record again for each idea with its new status: accepted, declined or later.
- `owner.md`: preferences you learned ("no lights changing on their own in the bedroom").
- `house.md`: what was built, with the date and how to undo it; gaps still open.
- `log.md`: date, what was pitched, what was built, test results.

Then `log_run`.

## Hands off to / called from

Build an idea: `routines` or `build-a-skill`. Fragile devices: `device-diagnosis`. After a purchase: `add-a-device`.
Called from `learn-the-house`.

## Words for the owner

- Pitch: "Three things would make the biggest difference. First: …"
- Before building: "This will turn the hall light off at 23:15 if nobody has moved for 10 minutes. I'll back up first and you can undo it. OK?"
- Declined: "Fine, I won't bring that up again."

## Report

What was pitched (titles), what was built and tested, what waits on a purchase or a later yes,
and how to undo each change. No ids unless asked.
