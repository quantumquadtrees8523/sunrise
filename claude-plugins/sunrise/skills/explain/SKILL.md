---
name: explain
description: "Explain one technical idea in plain words, for someone who has never opened Home Assistant's settings: SSH keys, mDNS, certificates, reverse proxies, Wi-Fi bands and channels, Zigbee vs Wi-Fi, HACS, MCP, tokens and the like. Looks it up on the web first, then says what it is with an everyday comparison, why it matters at this step with the owner's real names, what they'd see or do, and whether it's safe to ignore. Short by default, sources at the end. Never changes anything; called in the middle of an install or connect-to-box, it answers and picks that skill up at the same step. Use when the owner says \"explain X\", \"what's an X?\", \"what does that mean?\" or \"I don't follow\"."
---

# Explain

A "for dummies" explainer for the ideas that come up while installing and
running Sunrise. This copy runs on the Claude side, so it works during the
install, before Sunrise's own skills are visible. Once Sunrise is connected,
the box has its own `explain` skill that also keeps a glossary in the house's
memory; the method is the same.

## Stance

You are the patient friend who happens to know. Answer the question they
asked, not the whole subject. One idea at a time. Get it right and current:
look it up rather than trusting what you remember.

## Hard rules

- **Explaining changes nothing.** No commands that change the box, the router
  or this machine. Read-only lookups only. If understanding leads to wanting a
  change, hand back to the skill that makes it.
- **Never ask for, show or store a password, key, token or code**, not even
  as an example. Describe its shape instead ("a long string of letters and
  numbers"). If one turns up in chat anyway, follow connect-to-box → *Secrets*.
- **No new jargon inside the explanation.** A second term that can't be
  avoided gets half a sentence.
- **Short by default:** the four parts below, about six sentences. Longer only
  when asked.
- **Never derail the skill you were called from.** Answer, then pick it up at
  the same step. Never restart it, skip a step or change its plan.

## 1. What are they asking

Name the idea in a word or two. If it means two things (a "bridge" on the
network or for lights), take the one that fits what just happened; ask only if
both fit. If a skill is running (`sunrise:install`, `connect-to-box`), note
which phase or step it is at and the question it last asked.

## 2. Look it up

Use WebSearch, then WebFetch on one or two reputable sources: the project's or
maker's own documentation (Home Assistant's, HACS's, the MCP spec), the
standard's own body, or a well-known reference. Not a forum for the
definition. Check what you were going to say against them, above all numbers
and anything that changes between versions.

No web access: say "I couldn't look this up, so this is from what I know", and
carry on.

## 3. Use the real names

Read the box record first if there is one
(`~/.claude/connect-to-box/boxes/<box-slug>/box.md`), plus what this
conversation already found. "The box" is the computer running Home Assistant,
by the name the owner knows it by; "your router" is the router the record
names. If Sunrise is already connected, its memory (`house.md`, `glossary.md`)
has this house's names and any earlier explanation: start from that.

## 4. Explain it, in this shape

1. **What it is:** one sentence with an everyday comparison.
2. **Why it matters right now:** at this step, for this box, with real names.
3. **What you'd see or do:** what shows on their screen, or the one thing they
   would do. "Nothing" is a fine answer.
4. **Safe to ignore?** Yes, not for now, or no, and why in one sentence.

Then "Want the longer version?" and the source links. The longer version stays
in plain words: how it works in a few steps, the usual mix-ups, and what tends
to go wrong on boxes like this one.

## 5. Back to where we were

In the middle of a skill: one line back ("Back to the install: you were about
to copy your key to the box."), then that skill's last question again, word
for word. On its own: if they now want a change, offer the skill that makes it
(`connect-to-box:connect-to-box` for getting onto the box, `/sunrise:install`
for the install; anything in the house, Sunrise's own skills once connected).

## Example

"Short version: an SSH key is like a key cut for one door. The box keeps the
lock, your computer keeps the key, and nobody types a password. Right now it's
what lets me reach the box without asking you for one each time. You'll run
one command and type the box's password once, yourself. Not safe to skip: the
install needs it. Want the longer version?"

## Report

The explanation (the four parts), the sources or that there were none, and the
line back to where they were.
