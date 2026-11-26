---
name: connect-to-box
description: "Find a Home Assistant box on the network and get a repeatable, key-based shell on it, starting from the box record if one exists. Ends with a working shell command, install type, config path and container name written to the box record. Use on its own (\"get me onto the box\", \"ssh to home assistant\") or as the first step of any skill that installs or changes things on the box."
---

# Connect to the box

Gets Claude Code from "there's a Home Assistant box somewhere" to "here is a
command that gives me a shell on it, and here's where everything is". Nothing
in here is specific to what you're about to do on the box. Other skills (for
example `sunrise:install`) call this first and rely on its
output contract.

Two scripts ship in `scripts/` beside this file. Neither is on the `PATH`, so
use their full path, including in commands you hand to the owner:

- `scripts/find-box.sh [host]`: read-only discovery. It does mDNS, a sequential
  port scan, the install type, HTTPS/CA/OAuth checks, and possible ways in. It
  ends with `FIND_BOX_*=` lines you can parse.
- `scripts/box-secret`: the owner stores secrets and you reference them (see
  *Secrets*). It replaces `sunrise-secret` and still finds secrets that tool
  stored.

## Stance

Real boxes are in dirty states. Assume something is broken, half-configured,
or left over from an earlier experiment. Work out what you're dealing with
before you change anything, and when the obvious route is closed, find another.

**Meet the owner where their box is.** Never propose rebuilding, reimaging or
starting clean. A box that has been lived in for years is the normal case, not
an obstacle. The owner's time and data are worth more than your convenience. A
fresh install is only ever a last resort the owner raises.

**Explain as you go.** When a term may be new to the owner (SSH key, mDNS,
certificate), explain it in one plain sentence. For more, use `sunrise:explain`
if it's installed. This plugin can be installed without Sunrise, so otherwise
explain it inline in the same shape: what it is with an everyday comparison,
why it matters at this step, what they'd see or do, and whether it's safe to
ignore. Then carry on from the same step.

## Hard rules

- **Never type, print or store passwords or tokens.** You can't authenticate
  with a password, over SSH or anywhere else. Every route onto the box ends in
  key-based access or a command the owner runs themselves. Plan for this from
  the start.
- **Never guess usernames.** Spraying logins is hostile and gets blocked. Ask.
- This skill changes **nothing** on the box except adding the owner's public
  key, which the owner does themselves with `ssh-copy-id`. Everything else is
  read-only.
- **Run owner commands in the visible terminal panel** (`run_in_terminal`) so
  you can read what they printed. Don't take "done" on trust. In testing, the
  owner ran `ssh-copy-id` somewhere else, said it was done, and it had added
  nothing. The second run, in the panel, showed it waiting at the password
  prompt and then succeeding.

---

## The box record: read it first, write it as you go

Most of what goes wrong on a box comes from **not knowing things about it**.
The record is where that knowledge accumulates, and the next run starts from
it instead of from nothing.

### Where it lives

```
~/.claude/connect-to-box/boxes/<box-slug>/box.md          # answer-first record
~/.claude/connect-to-box/boxes/<box-slug>/box-history.md  # optional blow-by-blow
```

`<box-slug>` is the mDNS instance name, lowercased and hyphenated ("Home
Server" → `home-server`). This folder is **outside the plugin**, so plugin
updates never wipe it. It's on the machine running Claude Code, so you can read
it while the box is unreachable, which is exactly when you need it. List the
folder to see which boxes are known. If there's more than one and the owner
didn't say which, ask.

If the calling skill can also write to the box (for example Sunrise's
`memory_write`), it may keep a second copy there. The client-side copy is the
one that matters.

### Step 0: read it

Before you run anything, read `box.md` for the box. If it has a **WORKS** line
under *Getting a shell*, try exactly that command first:

```
ssh -o BatchMode=yes -o ConnectTimeout=5 <the WORKS command> 'id -un; uname -sr'
```

If it works, skip discovery and the ladder and go straight to *Take stock*, to
refresh anything that may have changed. If it fails, record the failure (date,
error) and start the ladder at the rung after the one that used to work. The
**FAILED** lines tell you which dead ends not to re-test.

### Write incrementally, including failures

Append each fact **the moment you learn it**. A run that dies halfway is when
the record earns its keep. Write down what *didn't* work and why ("key X
rejected for user Y", "port 22 open but password unknown", "browser terminal
is a container, not the host"). Each of those cost real time to discover once,
and will cost it again if you don't record it.

### Template

```markdown
# Box: <name>

## Getting a shell          <- the section that saves the next hour
- WORKS:   ssh -i ~/.ssh/<key> <user>@<host>      (access ladder rung N, <date>)
- Install type: HA OS / Container / Core / Supervised, on <host OS>
- sudo:    nopass / needs password / n/a   | docker group: yes/no
- Write path: <how you write HA's config, e.g. docker exec <container> ... as root>
- FAILED:  <rung, what was tried, the error, date>
- Note:    the HA web login is NOT the host password

## Reaching it
- Addresses:  <hostname(s)>, <LAN IP>, <external URL if any>
- Found by:   mDNS / owner told me / other
- Open ports: <port: what answers>
- HA version: <version> (from mDNS TXT, <date>)

## Where things are
- HA config on host: <path>  ->  <mount point in container>
- Container name:    <name>   image: <image:tag>
- File ownership:    <user:group, mode; which group grants write>
- Backups:           <path>; default backup agents: <list>
- Other services:    <reverse proxy, voice, IDE containers, and their ports>

## How the box is deployed
- Managed by: compose project <name>, files <exact -f list>
- Owner tooling: <Makefile targets, deploy/ scripts, approval flow>
- HA version pin lives in: <file:line>
- Anything that would revert a local edit: <git branch deploys, etc.>

## HTTPS / MCP
- HTTPS base: <url>   cert issuer: <public / private CA name>
- CA root saved at: <path on this machine>, trusted via <how>
- OAuth discovery: works / no issuer / protected-resource 404 -> token

## Secrets
- Names only, never values. Where each is stored.

## Baseline (written by the calling skill before it changes anything)
- Open repairs: <list>
- Error categories in the log: <count + source for each>

## Test device
- <entity_id> "<friendly name>", chosen by the owner, exact prior state
```

Keep `box.md` **answer-first**. Someone reading it in a hurry needs the
working shell command and the config path on the first screen, not a
chronology. Put the chronology in `box-history.md`.

---

## Phase A: find the box

Run `scripts/find-box.sh` (pass a host if the record or the owner gives one).
By hand, it comes down to:

1. **mDNS, not a subnet scan.** HA advertises `_home-assistant._tcp`. The TXT
   record gives you `version`, `internal_url` and `external_url` without
   authentication. **HA doesn't expose its version to an unauthenticated
   caller, so mDNS is the only free source.**
   ```
   dns-sd -B _home-assistant._tcp local ; dns-sd -L "<instance>" _home-assistant._tcp local   # macOS
   avahi-browse -rpt _home-assistant._tcp                                                     # Linux
   ```
2. **Parallel port scans give wrong answers.** A `for … & wait` sweep reports
   open ports as closed, and does it repeatably. Scan sequentially
   (`nc -z -G 2 -w 2`).
3. Finding nothing over mDNS isn't conclusive (different VLAN, or mDNS
   blocked). Ask the owner for the address.
4. **Port 2375 open means an unauthenticated Docker API.** Flag it to the owner
   as a security problem. Don't quietly use it.

Write *Reaching it* to the record now.

## Phase B: the access ladder

Walk the rungs in order. **Each failure tells you something. Record it and
move down rather than retrying the same rung.**

### Rung 1: do you already have access?

Use the username the owner gave you, try existing keys non-interactively, and
fail fast:

```
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new <user>@<box> 'id; uname -sr'
```

Add `-v` and grep for `Offering public key` / `Authentications that can
continue` to tell "key rejected" apart from "no key offered". Check
`~/.ssh/config` and `known_hosts` for hints, but a key that `~/.ssh/config`
uses for GitHub isn't necessarily authorized on the box.

### Rung 2: what kind of box is it?

- **HA OS** (4357 open): the owner installs the **Terminal & SSH** add-on from
  the HA UI and you get a shell without host credentials. Easiest case, so go
  there first.
- **Container / Core / Supervised** (4357 closed): there's no add-on store, so
  you need a real shell on the host. HA's API has no file-write endpoint.

### Rung 3: is there already a shell you can reach?

Dirty boxes often have a leftover one: 8443/8080/3000 code-server, 7681 ttyd,
9000/9443 Portainer, 10000 Webmin. A browser IDE needs a real browser to
finish its first-run download; `curl` sits on a 202 forever. **Check whether
that shell is actually on the host**, because it usually isn't:

```
cat /etc/os-release | head -2      # compare with the SSH banner find-box.sh printed
[ -f /.dockerenv ] && echo CONTAINER
command -v docker || echo "no docker client - cannot reach the host's containers"
ls -la /config 2>/dev/null         # is HA's config mounted in here?
```

If HA's config is mounted in, you may be able to work from there. Otherwise
these shells are **bootstraps, not the route**: use one to set up proper SSH,
then stop using it.

### Rung 4: key-based SSH (the generic step, an owner step)

Put the command in the owner's terminal panel so you can watch it:

```
ssh-copy-id -i ~/.ssh/<key>.pub <user>@<box>
```

Say: *"Type your **host** password at the prompt. I never see it. It's not
your Home Assistant login."* Same hostname, two different credential stores. A
password-manager entry saved against the box's hostname is almost certainly
the HA web login, and it fails with `Permission denied`, which looks identical
to a wrong username.

Read the panel. Success ends with `Number of key(s) added: 1`. Then re-run
rung 1. **If the key is still rejected**, don't conclude the box is broken.
Have the owner run a read-only check over password SSH (they type the
password) and read it back from the panel:

```
ssh -o PubkeyAuthentication=no <user>@<box> 'ls -ld ~ ~/.ssh ~/.ssh/authorized_keys; grep -c "<key comment>" ~/.ssh/authorized_keys'
```

A count of `0` means the copy never landed, so run it again in the panel. With
a count of `1`, look at permissions. `sshd` ignores `authorized_keys` if the
home folder or `~/.ssh` is group- or world-writable. If `authorized_keys`
already holds keys you didn't add, **leave them alone and tell the owner**.

### Rung 5: the owner doesn't have the host password

In order of preference:

1. **Another shell on the box** (rung 3, or another machine with a key). With
   root or passwordless sudo (`sudo -n true && echo nopass`), run
   `sudo passwd <user>`. Plain `passwd` asks for the *current* password, so it
   won't help.
2. **Console access**: log in at the box, or boot to recovery and reset.
3. **VPS / cloud**: reset from the provider's console.
4. **Provisioning history**: a compose file, Ansible or CI workflow names the
   deploy account and key. Ask the owner to look.

If none of these work, **stop**. Say plainly that the box can't be reached and
what the owner would need to do. Don't keep trying passwords.

### Rung 6: record it, before anything else

The moment a shell works, write the **Getting a shell** block, including the
failed rungs. The next run starts at the rung that worked.

## Phase C: take stock (read-only)

Find out how you'll actually work on the box. Write each fact as you learn it.

```
id; sudo -n true 2>/dev/null && echo SUDO_NOPASS || echo SUDO_NEEDS_PW
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
docker inspect --format '{{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' <ha-container>
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}} | {{index .Config.Labels "com.docker.compose.project.config_files"}} | {{index .Config.Labels "com.docker.compose.project.working_dir"}}' <ha-container>
ls -la <config>
```

Lessons that hold on most Container installs:

- **The docker group is enough; you don't need sudo.** If the user is in the
  `docker` group, `docker exec <ha-container> …` runs as root inside the
  container. Don't ask for a sudo password.
- **HA's config is usually root-owned** (for example `root:<user>`, mode 755).
  You can read it, but writing it from the host fails. Write through the
  container instead: `docker exec -w /config <ha-container> …`.
- **`.storage/*` is often root-only readable.** Read it through the container
  too, and print only the keys you need, never whole files. They hold tokens
  and backup passwords:
  ```
  docker exec <ha-container> python3 -c "import json;d=json.load(open('/config/.storage/backup'))['data'];print(d['config']['create_backup']['agent_ids'])"
  ```
- **Match the running compose file set exactly**
  (`com.docker.compose.project.config_files`). Recreating with a different
  `-f` set silently changes the service's configuration.
- **Look for the owner's own tooling** (Makefile, `deploy/`, version pins in
  compose) before inventing a command, and note anything that would revert a
  local edit.
- Write the *Where things are* and *How the box is deployed* blocks.

## Restarting Home Assistant: the two checks that give false positives

You don't restart in this skill, but callers do, so this lives here. Both
obvious readiness checks report success too early:

| Check | Observed | Verdict |
|---|---|---|
| `GET /manifest.json` → 200 | 3 s after restart; HA actually took 17 s | false positive |
| `docker ps` shows `(healthy)` | 4 s after restart (Docker keeps the old verdict until its next probe) | false positive |
| `Home Assistant initialized in Ns` in the log, timestamped after the restart | held every time | **use this** |

```
docker restart <ha-container>; sleep 45
grep "Home Assistant initialized" <config>/home-assistant.log | tail -1   # check the timestamp
```

**The log rotates on restart**, so compare error *categories* before and
after, not totals.

## Phase D: HTTPS and MCP reachability (when the caller needs it)

`find-box.sh` checks most of this. Set `MCP_PATH` to the endpoint the caller
will use.

- **Pick the address**: a local HTTPS name the owner already uses (reverse DNS
  often gives it, e.g. `homeassistant` → `homeassistant.local`), then their remote address.
  An HTTPS name doesn't prove it's HA. A redirect to `/sign-in` or an empty
  `/auth/providers` means a login gate is in front.
- **OAuth discovery**:
  - `/.well-known/oauth-protected-resource<MCP_PATH>` → **404** means OAuth
    can't work, because the client has nowhere to start.
  - `/.well-known/oauth-authorization-server` with no `issuer`, or an issuer
    of `127.0.0.1`, also means OAuth won't work. Note this happened **even
    with `trusted_proxies` set**.
  - In any of these cases, use a long-lived token. If the endpoint itself
    answers `POST` with 401, the problem is auth, not transport.
- **Private CA** (a reverse proxy's own local authority, e.g. Caddy's, or
  self-signed): extract the root (the Caddy path is shown; other proxies keep
  it elsewhere) and confirm:
  ```
  mkdir -p ~/.claude/certs
  ssh <box> 'docker exec <caddy-container> cat /data/caddy/pki/authorities/local/root.crt' > ~/.claude/certs/<box-slug>-root.crt
  curl --cacert ~/.claude/certs/<box-slug>-root.crt https://<name>/manifest.json   # 200 => cert was the issue
  ```
  Claude Code only trusts it via **`NODE_EXTRA_CA_CERTS` in the environment it
  is launched from**. Add `export NODE_EXTRA_CA_CERTS=…` to the owner's shell
  profile (ask first, since it's a persistent config change). The desktop app
  picked it up from `~/.zshrc` after a restart. **`env` in
  `~/.claude/settings.json` doesn't work**: it's applied too late for Node's
  TLS. `launchctl setenv` is a fallback until the next reboot. Fixing TLS
  alone won't help if OAuth discovery is also broken, so check both.

Write the *HTTPS / MCP* block.

---

## Secrets: the owner stores, you reference

**You never hold a secret**, not in a variable, a file you write, or a
message. You write a *reference*, and the shell resolves it when the command
runs:

```
<skill-dir>/scripts/box-secret set ha-token     # the OWNER runs this. Prompts. Nothing echoes.
<skill-dir>/scripts/box-secret get ha-token     # prints the value and nothing else
<skill-dir>/scripts/box-secret check ha-token   # exit 0/1, prints no secret
```

```
curl -H "Authorization: Bearer $(<skill-dir>/scripts/box-secret get ha-token)" http://<box>:8123/api/
```

**Put the prompt in front of them rather than asking for a paste.** Open
`box-secret set <name>` in their terminal panel, then say exactly where the
value comes from. For an HA token: *"Home Assistant → your profile → Security
→ Long-lived access tokens → Create, name it 'Claude', copy it, and paste it
at the prompt. It won't echo, and I never see it."* Asking "what's the token?"
in chat invites a paste into the transcript, and a stuck owner may hand over
their whole credentials file.

You'll be blocked from writing a credential to disk, even with `chmod 600`.
That refusal is correct. Don't work around it.

To pass a secret to a process on the box, pipe it over stdin. Don't put it in
argv, an env file, or a script:
`box-secret get ha-token | ssh <box> 'docker exec -i <container> python3 /tmp/x.py'`.

**Never ask for the SSH password.** `ssh-copy-id` has the owner type it
straight into the prompt.

### If a secret arrives in chat anyway

Write one short paragraph, then move on:
1. Name which secrets you saw, by label, never by value.
2. Say they're now in the transcript, and recommend rotating them, most
   valuable first.
3. Say you won't use or store any the task doesn't need.
4. Carry on. Don't lecture.

---

## Output contract

This skill is done when the box record has all of these, and you've told the
caller (or the owner) them:

1. **Shell:** the exact command that works (`WORKS:` line), tested this run.
2. **Install type:** HA OS / Container / Core / Supervised, and the host OS.
3. **Config path:** on the host, and its mount point in the container.
4. **Container name** (and image tag) for HA, or "n/a" on HA OS/Core.
5. **Write path:** how files under the config get written (add-on shell,
   `docker exec`, sudo).
6. **HA version** and where it came from.

If the caller asked for Phase D, also include the HTTPS base, OAuth verdict,
and CA status. If any item is missing, say which one and why. Don't report
success.

Then tell the owner where the record is and what the shell command is. They
probably didn't know any of it either.
