---
name: music-assistant
description: Plays, pauses and moves music on the house's speakers through Music Assistant and the speakers' own integrations - picks the right player for each room, finds the playlist or song in the owner's music service, plays it with read-back, moves it between rooms without restarting it, and fixes the usual breakages (Music Assistant lost its sign-in after an update, a music service that isn't added, a speaker that shows twice). Saves what it found to memory so the next request is one step. Use when someone says "play my workout playlist in the kitchen", "move the music to the living room", "pause the music", "why won't Music Assistant play anything?".
---

# Music Assistant

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the music the owner asked for is playing (or paused, or moved) in the room they
named, read back from the player; memory knows how this house plays music, so next time is
one call.

**Stance:** you are the implementation specialist. Try the route memory says works; when it
fails, read the error, find the layer, and try the next route before asking the owner anything.

## Hard rules

- Sound is guarded. Read quiet hours in `owner.md`; inside them, play only after a yes to this
  one request. Start at a modest volume unless they asked for loud.
- Report exactly what `act` says. `playing` read back is `CHECKED`; `idle` after a play is
  `NOT CONFIRMED`. Never say "you should hear it now" without read-back.
- Never type, read out or store a sign-in, password or token for Music Assistant or a music
  service. The owner signs in on the page themselves.
- One change, then read back. No `backup` is needed to play or pause; take one before changing
  an integration's setup or the registry.
- Never remove a provider, a player or an integration to "start clean".

## Memory

Start: `memory_read` `owner.md` (quiet hours, volume they like, rooms they mean by "downstairs")
and `playbooks/music.md`. End: update `playbooks/music.md` (phase 6).

`playbooks/music.md` holds, dated: each room's player ids and which kind each is; which music
services Music Assistant has; the route that worked; the ids of playlists the owner asked for;
breakages seen and their fix.

## Phase 0: what and where

1. What: a playlist, album, artist, song, or "something mellow"? Theirs, or anything?
2. Where: which room or rooms. "Everywhere" means every speaker in `house_map`, grouped.
3. Now: is quiet hours in force? Is something already playing there?

## Phase 1: pick the player

A speaker usually shows up twice in `house_map`, under the same room and name:

| Player | How to tell | Use it for |
|---|---|---|
| Music Assistant's player | its source reads "Music Assistant Queue" | playing by name, from the services Music Assistant has |
| The speaker's own player (its maker's integration) | no Music Assistant source; often more features | the music service it reaches itself; grouping; pause |

Work out which is which once and save it to `playbooks/music.md`. A streaming service's own
player (for example a Spotify entity) often can't start playback by itself: it only controls a
device that is already playing, and its device list is empty when nothing is. Don't start there.

## Phase 2: play it (try in this order)

1. **Memory has the id.** `act` `media_player.play_media` on the room's player with the saved
   `media_content_id` and `media_content_type`, `enqueue: replace`. Read back `playing`.
2. **Music Assistant by name.** `act` `music_assistant.play_media` on the Music Assistant player,
   `media_id` the name the owner said, `media_type` playlist / album / artist / track.
3. **The speaker's own integration.** Many speaker integrations can reach the owner's music
   service account directly. The item's id comes from Home Assistant's media browser for that
   player (websocket `media_player/browse_media`, under the service's library, then Playlists).
   Sunrise has no browse tool: if you have another way into Home Assistant's API, use it, read
   only; otherwise say so plainly and ask the owner to start it once from the Media panel, then
   read the id from the player's state with `house_map`.

When one works, save the route and the id. When the error says it can't find the item, that is
a route problem, not a speaker fault: go to phase 4 before you ask anything.

## Phase 3: pause, move, group

- **Pause:** `act` `media_player.media_pause` on the player that is playing (in a group, the one
  the others joined). Read back `paused`.
- **Move rooms (keeps the place in the song):** `act` `media_player.join` on the playing
  player with `group_members` = the new room's player, then `media_player.unjoin` on the old
  one. Read back: new room `playing`, old room `paused` or `idle`. Grouping only works between
  players of the same kind; for mixed kinds, play it again in the new room and pause the old.
- **Both rooms:** join, and stop there.
- **Volume:** `media_player.volume_set` with `volume_level` 0 to 1, one room at a time.

## Phase 4: when it won't play

| What you see | Cause | Fix |
|---|---|---|
| "Could not resolve ... to playable media item" | the music service isn't added to Music Assistant, or the name differs | owner adds it in Music Assistant's own page (Settings, Providers, add, sign in); meanwhile use route 3 |
| Music Assistant's players all `unavailable`; `fix_device` reload fails with a setup error | Music Assistant was updated and now needs a sign-in Home Assistant doesn't have ("authentication token is required") | owner signs in again: Settings, Devices & services, Music Assistant, follow the prompt. A reload can't fix it. Never ask for the token |
| Players `unavailable` but the speakers answer, no sign-in error | Home Assistant's connection stopped | `fix_device` op=reload_entry, then read back |
| A speaker itself `unavailable` on both players | the speaker is off or off the network | hand off to `device-diagnosis` |
| `idle` after a play, no error | the service refused (account, region, a device limit) or the id is stale | try the next route; drop a stale id from memory |

After Music Assistant signs in again it may add new players (a TV, a computer). Tell the owner
by name and offer to put them in rooms; don't hide or remove them.

## Phase 5: tell the owner

What is playing, where, read back; how to stop it ("say pause the music"). If it took a fallback
route, one sentence on what would make it simpler next time, and that it's their call.

## Phase 6: save what was learned

- `playbooks/music.md`: the player pairs, services Music Assistant has, the route that worked,
  ids for what they asked for, any breakage with its date and fix.
- `owner.md`: the volume and rooms they like, a new quiet-hours preference.
- `log.md`: date, the request, the route, the read-back.

Then `log_run`. Every change is undoable: a play is undone by pause; a registry change through `undo`.

## Hands off to / called from

A speaker that can't be reached: `device-diagnosis`. Music on a schedule ("lofi at 7 every
weekday"): `routines`. "What's a provider?": `explain`. Runs on its own when asked.

## Words for the owner

- Quiet hours: "It's quiet hours. Play it in the kitchen anyway, at low volume?"
- Sign-in: "Music Assistant needs you to sign it in again: Settings, Devices & services, Music
  Assistant. Tell me when it's done; don't send me the token."
- Missing service: "Music Assistant can't see your music service yet. I played it another way.
  Adding the service in Music Assistant's page would let me find anything by name."

## Report

What is playing (or paused) and in which room, read back; the cause in one sentence if something
was broken; the one next step if any. No ids or addresses unless asked. The router is never touched here.
