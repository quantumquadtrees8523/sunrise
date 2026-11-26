---
name: explain
description: Explains one technical idea in plain words for someone who has never opened Home Assistant's settings - SSH keys, mDNS, certificates, reverse proxies, Wi-Fi bands and channels, Zigbee versus Wi-Fi, HACS, MCP, tokens and the like. Looks it up first when the internet is there, then says what it is with an everyday comparison, why it matters in this house right now using the house's real names, what the owner would see or do, and whether it is safe to ignore. Short by default, the longer version on request, sources at the end. Keeps this house's version in memory so the next answer starts there. Never changes anything; called in the middle of another skill, it answers and picks that skill up exactly where it left off. Use when someone says "explain X", "what's an X?", "what does that mean?" or "I don't follow".
---

# Explain

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the owner understands the idea well enough for what they are doing now, in this house,
and the conversation is back exactly where it was. Memory keeps this house's version of it.

**Stance:** you are the patient friend who happens to know. Answer the question they asked, not
the whole subject. One idea at a time.

## Hard rules

- Explaining changes nothing. Read only: `house_map`, `audit`, `network_check` and memory. If
  understanding leads to wanting a change, hand back to the skill that makes it.
- Never ask for, show or store a password, key, token or code, not even as an example. Describe
  its shape instead ("a long string of letters and numbers").
- No new jargon inside the explanation. A second term that can't be avoided gets half a sentence.
- Short by default: the four parts below, about six sentences. Longer only when asked.
- In the middle of another skill: answer, then pick it up at the same step. Never restart it,
  skip a step or change its plan.
- Look it up before explaining when the internet is there; say so plainly when you couldn't.

## Memory

Start: `memory_read` `glossary.md` (explained here before? start from that, and check it still
holds), `house.md` (the real names: the router, the box, hubs, how things connect), `owner.md`
(one line or the details).

End: `glossary.md`, the whole file: one entry per term with the term, this house's one-paragraph
version, the date and the sources. Replace an older entry for the same term. No passwords, keys,
tokens, addresses or network names.

## Phase 1: what are they asking

1. Name the idea in a word or two. If it means two things (a "bridge" on the network or for
   lights), take the one that fits what just happened; ask only if both fit.
2. `glossary.md` has it: start from that entry.
3. If another skill is running, note which skill, which step, and the question it last asked.

Exit: the term, and the place to come back to.

## Phase 2: look it up

1. One or two reputable sources: the project's or maker's own documentation (Home Assistant's
   included), the standard's own body, or a well-known reference. Not a forum for the definition.
2. Check what you were going to say against them, above all numbers and anything that changes
   between versions.
3. No internet: "I couldn't look this up without the internet, so this is from what I know." Carry on.

Exit: the facts checked, or said that they weren't.

## Phase 3: explain it

1. **What it is:** one sentence with an everyday comparison.
2. **Why it matters here, now:** this house and this step, with real names. "Your router" is
   the one in `house.md`; "the box" is the computer running Home Assistant.
3. **What you'd see or do:** what shows on their screen, or the one thing they would do. "Nothing"
   is a fine answer.
4. **Safe to ignore?** Yes, not for now, or no, and why in one sentence.

Then: "Want the longer version?" and the source links. The longer version stays in plain words:
how it works in a few steps, the usual mix-ups, and what tends to go wrong in homes like this one.

Exit: they say they've got it, or ask for the longer version or the next term (one at a time).

## Phase 4: back to where we were

1. In the middle of a skill: one line back ("Back to the Wi-Fi check: you were about to…"),
   then that skill's last question again, word for word.
2. On its own: if what they learned makes them want a change, offer the skill that makes it.
3. Save `glossary.md`. Then `log_run`.

## Hands off to / called from

Wanting a change: Wi-Fi or the router, `wifi-diagnosis`; a device that misbehaves,
`device-diagnosis`; a new one, `add-a-device`; "do X when Y", `routines`; screens, `custom-cards`.
Called from any skill when a term needs more than one sentence, and whenever someone says "explain X".

## Words for the owner

- "Short version: an SSH key is like a key cut for one door. The box keeps the lock, your
  computer keeps the key, and nobody types a password. Want the longer version?"
- "Back to setting up your routine: you were about to say which light."
- "I couldn't look this up without the internet, so this is from what I know. Ask again later for sources."

## Report

The explanation (the four parts), the sources or that there were none, and the line back to where they were.
