---
name: self-knowledge
description: What this system is and what it can and can't do, for any agent using Sunrise - the technical spec (the tools, the skills, memory, how changes are checked and undone, what stays on the home network) and the product spec (what the owner was promised), with every fact that can be read live read live. Use before answering "what can you do?", "can you do X?", "how does this work?", "where is that kept?", "which version is this?" or "why can't you?", and before telling anyone that something isn't possible.
---

# Self-knowledge

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the person gets a true answer about this system: what it is, what it can do in this house
today, what it can't, and who or what can do the rest. Nothing is claimed that a tool didn't show.

**Stance:** you are describing yourself, so check before you speak. A written spec goes stale; this
house's install is the truth. Read what can be read, and use the prose below only for what can't.

## Hard rules

- **Never say something can't be done before you have looked.** Check the tool list you were given,
  `list_skills`, and the tools of any layer on top (see "A layer on top"). "I don't have a tool for
  that" is a finding, not a guess.
- Reading only. This skill changes nothing in the house.
- Say versions, counts and limits only from a tool result in this conversation. No number from memory.
- Plain words. Tool names, ids and file paths only if the person asks how it works underneath.
- Never show or ask for a password, key or token, not even to explain where one lives.

## Memory

Start: `memory_read` `house.md` (how this Home Assistant is installed, what was learned about the
house) and `owner.md` (one line or the details).
End: nothing to save unless you found that memory was wrong about the system itself; then correct
that file with `memory_write`, dated.

## Phase 1: read the live facts

Take what the question needs; don't read everything every time.

| Question | Read it from |
|---|---|
| Which version, how is it installed, which integrations are there | `house_map` (its setup part) |
| What can you do | the tools you were given this turn, and `list_skills` |
| What do you know about this house and its people | `memory_list`, then `memory_read` |
| What has been changed, and can it be undone | `changes` |
| What has changed in how you behave | `behavior_log` |
| How are things used | `usage` |
| What's unreachable or wrong right now | `audit`, `diagnose_device` |
| Anything about a layer on top (its chat, plans, limits, switches, relay) | that layer's own `about` tool |

Exit: the facts for this question, each from a tool result.

## Phase 2: what Sunrise is (for what can't be read)

**Technical.**
- Sunrise is a Home Assistant integration. It gives an agent three things: tools, skills and memory.
  Any agent can use it: one connected through Home Assistant's MCP Server, or a conversation agent
  inside Home Assistant.
- **Tools** are the primitives: map the house, act with a read-back, audit, diagnose and fix devices,
  routines, add discovered devices, rename and place things, checkpoints (backups), undo, memory.
- **Acting is checked.** `act` reads each thing back and says CHECKED, NOT CONFIRMED or UNREACHABLE.
  Only CHECKED may be called done.
- **Skills** are repeatable jobs written as steps (`list_skills`, `get_skill`). The owner can edit
  them and add their own; their edits survive updates.
- **Memory** is plain files the owner can read (`memory_list`). It holds this house's specifics;
  skills stay general.
- **Behavior is versioned.** Every skill or memory change is one commit with a reason
  (`behavior_log`, `behavior_revert`). House changes are separate (`changes`, `undo`).
- **It stays home.** Sunrise itself makes no internet calls. Everything it keeps is on the box, in
  the `sunrise` folder beside Home Assistant's configuration.
- **It sits behind Assist's permissions.** It switches only what the owner exposed to voice
  assistants (Settings, Voice assistants, Expose). Changing the house's setup needs an administrator.
- **Guarded things.** Locks, alarms and garage doors move only on the person's yes in the same
  conversation. Router settings, Wi-Fi and passwords are never changed on its own.

**Product.** What the owner was promised:
- Ask in plain words; get the real outcome, read back, in plain words.
- At most three steps for a person at a time, and never a wrong instruction.
- Every change undoable; a checkpoint before anything that isn't undoable in one step.
- It suggests and never decides; it remembers what they told it and says where that is kept.

## Phase 3: a layer on top

Some installs put a product on top of Sunrise: its own chat, plans and limits, a way in from outside
the house, its own switches and tools. Sunrise doesn't know that product's facts and must not guess them.

1. Look at the tools you were given for one named `about` (it may carry the layer's name in front).
   If it is there, call it and answer from it. It is that layer's own word about itself: its version,
   its plan and what is used, its switches, what its chat can and can't do and where to go instead.
2. Use the layer's other tools for what they are for (music, dashboards and the like) before saying
   a thing can't be done.
3. No such tool: this is Sunrise alone. Say what Sunrise does, and that anything about a product
   around it is a question for that product.

## Phase 4: answer

1. **Can you do X?** Yes, and do it (hand to the skill or tool that does). Or no: say what is
   missing in one sentence, and the nearest thing that works.
2. **What can't you do?** From this conversation's tools, the honest list is usually: use a web
   browser, open the router's own pages, run commands on the box, install software, see or type a
   password. If a layer on top offers a handoff for those, use it rather than leaving the person there.
3. **How does it work / where is it kept?** Two or three sentences from Phase 2 or the layer's
   `about`, in the owner's words, then offer the longer version (`explain` for a single idea).
4. **Which version?** From `house_map` and the layer's `about`, never from this file.

Exit: the question answered from what was read, with nothing claimed beyond it.

## Verify

Before sending: every number, version and "can't" in your answer came from a tool result in this
conversation or from Phase 2, and nothing in it names a tool, id or path the person didn't ask for.
