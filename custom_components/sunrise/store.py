"""Files this integration keeps in the user's data folder (outside custom_components, so an
integration update never overwrites them). Plain Python, no Home Assistant imports: blocking file
I/O, so Home Assistant code calls it in the executor.

<config>/sunrise/                  a git repository: the agent's behavior, one commit per change
  skills/<name>/SKILL.md          the live text of every skill (built-in copies and the user's own)
  skills/<name>/references/       RUBRIC.md and HOUSE-BASICS.md, rewritten from the shipped copy
  memory/**/*.md                  what the agent remembers about this house and its owner: plain
                                  Markdown the owner can open, e.g. owner.md, house.md, playbooks/x.md
  .gitignore                      only skills/ and memory/ are tracked; nothing else here ever is
  skills.json                     per skill: origin, shipped hash, user_edited (not tracked)
  audit.json, changes.jsonl, runs.jsonl   run data (not tracked)

Git is the history: every skill or memory change is one commit (message: the reason; author: user,
agent or product), read with `git log` and put back with a new commit. The repository has no
remote and nothing here ever fetches or pushes. Home Assistant's own images ship the git binary.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

AUTHORS = ("user", "agent", "product")
NAME_RX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REFERENCES = ("RUBRIC.md", "HOUSE-BASICS.md")
RUBRIC_REF = "references/RUBRIC.md"
# Words a skill's text keeps once it has them: an edit that drops one weakens a safety rule.
GUARDED = ("backup", "read back", "never", "undo", "router", "password", RUBRIC_REF)
BAD_PHRASES = re.compile(
    r"ignore (the )?(rubric|rules|safety)|skip (the )?(backup|read.?back|re-?check)|no need to (back ?up|read back|check)"
    r"|router password (is|[:=])|without (asking|a yes|their ok)|(un)?lock .{0,20}without",
    re.IGNORECASE)


MEMORY_RX = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*){0,2}\.md$")
MEMORY_MAX_BYTES = 32_000
MEMORY_MAX_FILES = 200
# Memory is for facts and preferences, never credentials. A refusal names what tripped it.
SECRET_RX = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\beyJ[\w-]{15,}\.[\w-]{10,}\.[\w-]{10,}"
    r"|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|xox[abp]-[\w-]{10,}|AKIA[0-9A-Z]{16})"
    r"|\bBearer\s+[\w.~+/-]{20,}"
    r"|\b(?:pass(?:word|phrase|code)?|passwd|pwd|secret|token|api[ _-]?key|wi-?fi key|psk|pin)\b\s*(?:is|[:=])\s*\S{4,}",
    re.IGNORECASE)


class MemoryError_(ValueError):
    """A memory write that was refused; the message says why in plain words."""


class SkillError(ValueError):
    """A skill write that was refused; the message says why in plain words."""


def _now() -> float:
    return time.time()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def frontmatter(text: str) -> dict[str, str]:
    """The `name` and `description` of a SKILL.md (simple `key: value` YAML frontmatter)."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith(" "):
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def validate_skill(name: str, text: str) -> list[str]:
    """Problems with a SKILL.md, per agentskills.io plus this pack's own rule (cite the rubric)."""
    problems = []
    fm = frontmatter(text)
    if not NAME_RX.match(name or "") or len(name) > 64:
        problems.append("the name must be lowercase letters, digits and single hyphens, at most 64 characters")
    if not fm:
        problems.append("the text must start with frontmatter (--- name: ... description: ... ---)")
    elif fm.get("name") != name:
        problems.append(f"the frontmatter name must be {name!r}")
    desc = fm.get("description", "")
    if not desc:
        problems.append("the frontmatter needs a description (what it does and when to use it)")
    elif len(desc) > 1024:
        problems.append("the description must be at most 1024 characters")
    if RUBRIC_REF not in text:
        problems.append(f"the skill must point to the rubric ({RUBRIC_REF})")
    return problems


def weakens_rules(old: str, new: str) -> list[str]:
    """Why `new` would weaken the fixed safety rules compared with `old` (empty: it doesn't)."""
    out = []
    lo, ln = old.lower(), new.lower()
    for word in GUARDED:
        if word.lower() in lo and word.lower() not in ln:
            out.append(f"it drops {word!r}, which the current version relies on")
    bad = BAD_PHRASES.search(new)
    if bad and not BAD_PHRASES.search(old):
        out.append(f"it says {bad.group(0)!r}")
    return out


def diff(old: str, new: str, name: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"{name}/before", f"{name}/after"))


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class BehaviorError(ValueError):
    """A history read or revert that was refused; the message says why in plain words."""


GITIGNORE = """# Sunrise tracks the agent's behavior only: its skills and its memory.
# Run data, caches and anything else in this folder stay out of the history.
/*
!/.gitignore
!/skills/
!/memory/
"""
COMMIT_RX = re.compile(r"^[0-9a-f]{4,40}$")
TRACKED = ("skills", "memory")
DIFF_MAX = 6000


class Git:
    """The git repository at the data folder: fixed argv, no shell, no remote, no network. It
    ignores every config outside the repository (a user's global hooks or signing can't interfere)
    and names its own folder as safe, so it works whoever owns the files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def run(self, *args: str, check: bool = True) -> str:
        env = {"PATH": os.environ.get("PATH") or "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
               "GIT_DIR": str(self.root / ".git"), "GIT_WORK_TREE": str(self.root)}
        try:
            done = subprocess.run(["git", "-c", f"safe.directory={self.root}", "-c", "core.hooksPath=/dev/null", *args],  # noqa: S603, S607
                                  cwd=self.root, env=env, capture_output=True, text=True, timeout=30, check=False)
        except FileNotFoundError as exc:
            raise BehaviorError("Sunrise needs the git program, which Home Assistant's own images include. "
                                "Install git on this machine, then reload Sunrise.") from exc
        except subprocess.TimeoutExpired as exc:
            raise BehaviorError("git took too long; nothing was changed") from exc
        if check and done.returncode != 0:
            raise BehaviorError((done.stderr or done.stdout).strip().splitlines()[-1] if (done.stderr or done.stdout).strip() else "git failed")
        return done.stdout

    def init(self) -> bool:
        """Make the repository if it isn't there. True when it was just created."""
        self.root.mkdir(parents=True, exist_ok=True)
        new = not (self.root / ".git").is_dir()
        if new:
            self.run("init", "-q", "-b", "main")
            for key, value in (("user.name", "Sunrise"), ("user.email", "sunrise@localhost"), ("commit.gpgsign", "false"),
                               ("core.autocrlf", "false"), ("gc.auto", "200")):
                self.run("config", key, value)
        ignore = self.root / ".gitignore"
        if not ignore.is_file() or ignore.read_text(encoding="utf-8") != GITIGNORE:
            ignore.write_text(GITIGNORE, encoding="utf-8")
        return new

    def commit(self, reason: str, author: str, paths: tuple[str, ...] = (".gitignore", *TRACKED)) -> str | None:
        """Stage `paths` (whatever exists of them) and commit. Returns the short commit id, or None if nothing changed."""
        here = [p for p in paths if (self.root / p).exists() or self.run("ls-files", "--", p).strip()]
        if not here:
            return None
        self.run("add", "-A", "--", *here)
        if not self.run("diff", "--cached", "--name-only", "--", *here).strip():
            return None
        message = " ".join((reason or "").split())[:200] or "change"
        self.run("commit", "-q", "-m", message, f"--author={author} <{author}@sunrise.invalid>", "--", *here)
        return self.run("rev-parse", "--short", "HEAD").strip()

    def head(self) -> dict[str, Any] | None:
        out = self.run("log", "-1", "--format=%h%x1f%an%x1f%aI%x1f%s", check=False).strip()
        if not out:
            return None
        commit, author, when, reason = out.split("\x1f", 3)
        return {"commit": commit, "author": author, "when": when, "reason": reason}


class Store:
    """Everything under one data folder. Skills and memory are its git-tracked part."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.meta_path = self.root / "skills.json"
        self.git = Git(self.root)
        self._lock = threading.RLock()  # one git operation at a time
        self._ready = False

    def _repo(self) -> Git:
        """The repository, created on first use. Files edited by hand since the last commit are
        committed first (as the user's), so the history never loses what the owner wrote."""
        if not self._ready:
            if self.git.init():
                self.git.commit("Sunrise starts keeping the agent's behavior in git", "product")
            self._ready = True
        self.git.commit("edited on disk", "user")
        return self.git

    # --- skills -----------------------------------------------------------------------------

    def meta(self) -> dict[str, dict[str, Any]]:
        return _read_json(self.meta_path, {})

    def skill_path(self, name: str) -> Path:
        if not NAME_RX.match(name or ""):
            raise SkillError(f"{name!r} isn't a skill name")
        return self.skills_dir / name / "SKILL.md"

    def read(self, name: str) -> str | None:
        try:
            return self.skill_path(name).read_text(encoding="utf-8")
        except OSError:
            return None

    def write(self, name: str, text: str, *, author: str, reason: str, check_rules: bool = True, commit: bool = True) -> dict[str, Any]:
        """The one way a skill's text changes: validate, write, commit. Returns the commit."""
        if author not in AUTHORS:
            raise SkillError(f"author must be one of {', '.join(AUTHORS)}")
        if not (reason or "").strip():
            raise SkillError("say why (reason) the skill changes")
        text = text if text.endswith("\n") else text + "\n"
        problems = validate_skill(name, text)
        if problems:
            raise SkillError("Not saved: " + "; ".join(problems) + ".")
        with self._lock:
            old = self.read(name) or ""
            if old == text:
                return {"name": name, "changed": False}
            if check_rules and author != "product" and old:
                weak = weakens_rules(old, text)
                if weak:
                    raise SkillError("Not saved: the change would weaken the safety rules (" + "; ".join(weak) + ").")
            git = self._repo() if commit else None
            path = self.skill_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            meta = self.meta()
            entry = meta.setdefault(name, {"origin": "product" if author == "product" else "user"})
            if author == "product":
                entry["shipped_sha"] = sha(text)
                entry.pop("update_available", None)
            self._mark(entry, text)
            _write_json(self.meta_path, meta)
            made = git.commit(reason, author, (f"skills/{name}",)) if git else None
        return {"name": name, "commit": made, "ts": _now(), "author": author, "reason": reason.strip(),
                "diff": diff(old, text, name), "changed": True}

    @staticmethod
    def _mark(entry: dict[str, Any], text: str) -> None:
        """A built-in is the person's own once its text differs from the shipped one."""
        entry["sha"] = sha(text)
        entry["user_edited"] = entry.get("origin") == "product" and entry.get("shipped_sha") != sha(text)

    @staticmethod
    def _edited(entry: dict[str, Any], current: str) -> bool:
        """Whether a built-in is the person's: its file on disk differs from the text that was
        shipped, however it was changed (skill_update or by hand). Put back to the shipped text,
        it follows the product again. Without a shipped hash we can't tell, so trust the flag."""
        if entry.get("shipped_sha"):
            return entry["shipped_sha"] != sha(current)
        return bool(entry.get("user_edited"))

    def _refresh_meta(self) -> None:
        """After a revert put files back: make skills.json match what is on disk."""
        meta = self.meta()
        for name in list(meta):
            text = self.read(name)
            if text is None:
                del meta[name]
            else:
                self._mark(meta[name], text)
        for p in self.skills_dir.glob("*/SKILL.md") if self.skills_dir.is_dir() else []:
            if p.parent.name not in meta:
                meta[p.parent.name] = {"origin": "user"}
                self._mark(meta[p.parent.name], p.read_text(encoding="utf-8"))
        _write_json(self.meta_path, meta)

    def list(self) -> list[dict[str, Any]]:
        meta = self.meta()
        out = []
        for p in sorted(self.skills_dir.glob("*/SKILL.md")) if self.skills_dir.is_dir() else []:
            name = p.parent.name
            fm = frontmatter(p.read_text(encoding="utf-8"))
            m = meta.get(name, {})
            out.append({"name": name, "description": fm.get("description", ""), "origin": m.get("origin", "user"),
                        "user_edited": bool(m.get("user_edited")),
                        **({"update_available": True} if m.get("update_available") else {})})
        return out

    def install_shipped(self, shipped: Path, version: str) -> dict[str, list[str]]:
        """Copy the integration's built-in skills in, as one commit. New ones are added; untouched
        ones follow the product; a copy the user edited is kept and only flagged `update_available`."""
        done: dict[str, list[str]] = {"added": [], "updated": [], "kept_user_copy": []}
        refs = shipped / "_shared"
        with self._lock:
            git = self._repo()
            for src in sorted(shipped.glob("*/SKILL.md")):
                name = src.parent.name
                text = src.read_text(encoding="utf-8")
                current = self.read(name)
                m = self.meta().get(name, {})
                if current is None:
                    self.write(name, text, author="product", reason="installed", commit=False)
                    done["added"].append(name)
                elif current == text:
                    pass
                elif m.get("origin") == "user" or self._edited(m, current):
                    meta = self.meta()
                    entry = meta.setdefault(name, {"origin": "product"})
                    self._mark(entry, current)  # an edit made on disk counts as theirs too
                    if entry.get("shipped_sha") != sha(text):
                        entry["update_available"] = True
                    _write_json(self.meta_path, meta)
                    done["kept_user_copy"].append(name)
                else:
                    self.write(name, text, author="product", reason="updated", commit=False)
                    done["updated"].append(name)
            for folder in self.skills_dir.glob("*/") if self.skills_dir.is_dir() else []:
                (folder / "references").mkdir(exist_ok=True)
                for ref in REFERENCES:
                    if (refs / ref).is_file():
                        shutil.copyfile(refs / ref, folder / "references" / ref)
            git.commit(f"Sunrise {version}: built-in skills", "product")
        return done

    def reference(self, ref: str) -> str:
        for p in sorted(self.skills_dir.glob(f"*/references/{ref}")):
            return p.read_text(encoding="utf-8")
        return ""

    # --- memory: Markdown the agent writes and the owner can read ----------------------------

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    def memory_path(self, name: str) -> Path:
        name = (name or "").strip().lstrip("/")
        if not MEMORY_RX.match(name) or len(name) > 120:
            raise MemoryError_(f"{name!r} isn't a memory file name: lowercase, .md, at most two folders deep "
                               "(owner.md, house.md, playbooks/router.md)")
        return self.memory_dir / name

    def memory_list(self) -> list[dict[str, Any]]:
        """Every memory file: its name, first line, size and when it last changed."""
        out = []
        for p in sorted(self.memory_dir.rglob("*.md")) if self.memory_dir.is_dir() else []:
            name = p.relative_to(self.memory_dir).as_posix()
            text = p.read_text(encoding="utf-8")
            first = next((line.strip().lstrip("# ").strip() for line in text.splitlines() if line.strip()), "")
            out.append({"name": name, "first_line": first[:120], "bytes": len(text.encode()), "changed": p.stat().st_mtime})
        return out

    def memory_read(self, name: str) -> str | None:
        try:
            return self.memory_path(name).read_text(encoding="utf-8")
        except OSError:
            return None

    def memory_write(self, name: str, text: str, *, author: str = "agent", reason: str) -> dict[str, Any]:
        """Replace one memory file's whole text, as one commit."""
        path = self.memory_path(name)
        name = path.relative_to(self.memory_dir).as_posix()
        if author not in ("user", "agent"):
            raise MemoryError_("author is user or agent")
        if not (reason or "").strip():
            raise MemoryError_("say why (reason) the memory changes, in one line")
        if not (text or "").strip():
            raise MemoryError_("the text is empty; use memory_delete to remove a file")
        text = text if text.endswith("\n") else text + "\n"
        if len(text.encode()) > MEMORY_MAX_BYTES:
            raise MemoryError_(f"too long ({len(text.encode())} bytes; the limit is {MEMORY_MAX_BYTES}). "
                               "Memory is a reference card: keep what's true now and move history to log.md")
        secret = SECRET_RX.search(text)
        if secret:
            raise MemoryError_(f"Not saved: this looks like a secret ({secret.group(0)[:24]!r}...). Memory never holds "
                               "passwords, keys or tokens; say where the owner keeps it instead.")
        with self._lock:
            old = self.memory_read(name)
            if old == text:
                return {"name": name, "changed": False}
            if old is None and len(self.memory_list()) >= MEMORY_MAX_FILES:
                raise MemoryError_(f"there are already {MEMORY_MAX_FILES} memory files; merge or delete some first")
            git = self._repo()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            made = git.commit(reason, author, (f"memory/{name}",))
        return {"name": name, "commit": made, "ts": _now(), "author": author, "reason": reason.strip(),
                "diff": diff(old or "", text, name), "changed": True}

    def memory_delete(self, name: str, *, author: str = "agent", reason: str) -> dict[str, Any]:
        path = self.memory_path(name)
        name = path.relative_to(self.memory_dir).as_posix()
        if author not in ("user", "agent"):
            raise MemoryError_("author is user or agent")
        if not (reason or "").strip():
            raise MemoryError_("say why (reason) it's deleted, in one line")
        with self._lock:
            if self.memory_read(name) is None:
                raise MemoryError_(f"no memory file {name!r}; memory_list lists them")
            git = self._repo()
            path.unlink()
            made = git.commit(reason, author, (f"memory/{name}",))
        return {"name": name, "deleted": True, "commit": made, "undo": f"behavior_revert commit={made}"}

    # --- the history of both: git ------------------------------------------------------------

    def behavior_path(self, file: str | None) -> str | None:
        """A tool's `file` as a path inside the repository: memory/house.md, skills/<name>, a bare
        memory file name (house.md) or a bare skill name."""
        file = (file or "").strip().strip("/")
        if not file:
            return None
        if file.startswith("memory/"):
            return "memory/" + self.memory_path(file[7:]).relative_to(self.memory_dir).as_posix()
        if file.startswith("skills/"):
            file = file[7:].split("/")[0]
        if file.endswith(".md"):
            return "memory/" + self.memory_path(file).relative_to(self.memory_dir).as_posix()
        if not NAME_RX.match(file):
            raise BehaviorError(f"{file!r} isn't a memory file (house.md) or a skill name")
        return f"skills/{file}"

    def behavior_log(self, file: str | None = None, limit: int = 20, commit: str | None = None, with_diff: bool = False) -> list[dict[str, Any]]:
        """The latest commits, newest first: id, who, when, why and the files each touched. One file
        or skill narrows it; `commit` shows just that one; `with_diff` adds each commit's diff."""
        with self._lock:
            git, path = self._repo(), self.behavior_path(file)
            if commit is not None and not COMMIT_RX.match(commit):
                raise BehaviorError(f"{commit!r} isn't a commit id; behavior_log lists them")
            args = ["log", "--format=%x1e%h%x1f%an%x1f%aI%x1f%s", "--name-status", "-n", "1" if commit else str(max(1, min(int(limit), 100)))]
            out = git.run(*args, commit, check=False) if commit else git.run(*args, "--", *([path] if path else TRACKED), check=False)
            rows = []
            for block in out.split("\x1e")[1:]:
                head, _, files = block.partition("\n")
                cid, author, when, reason = head.split("\x1f", 3)
                row = {"commit": cid, "author": author, "when": when, "reason": reason,
                       "files": [f"{line.split(maxsplit=1)[0][0]} {line.split(maxsplit=1)[1]}" for line in files.splitlines() if line.strip()]}
                if with_diff or commit:
                    text = git.run("show", "--format=", cid, "--", *([path] if path else TRACKED), check=False)
                    row["diff"] = text if len(text) <= DIFF_MAX else text[:DIFF_MAX] + "\n... (cut; ask for one file)"
                rows.append(row)
        return rows

    def behavior_revert(self, commit: str, file: str | None = None, *, author: str = "agent", reason: str = "") -> dict[str, Any]:
        """Undo with a new commit, never by rewriting history. Without `file`: reverse exactly what
        `commit` changed. With `file`: put that one file or skill back the way it was at `commit`."""
        if not COMMIT_RX.match(commit or ""):
            raise BehaviorError(f"{commit!r} isn't a commit id; behavior_log lists them")
        if author not in ("user", "agent"):
            raise BehaviorError("author is user or agent")
        who = f"--author={author} <{author}@sunrise.invalid>"
        with self._lock:
            git, path = self._repo(), self.behavior_path(file)
            if not git.run("rev-parse", "-q", "--verify", f"{commit}^{{commit}}", check=False).strip():
                raise BehaviorError(f"no commit {commit}; behavior_log lists them")
            subject = git.run("log", "-1", "--format=%s", commit).strip()
            if path is None:
                git.run("revert", "--no-commit", commit, check=False)
                if git.run("diff", "--name-only", "--diff-filter=U").strip():
                    git.run("revert", "--abort", check=False)
                    git.run("reset", "-q", "--hard", "HEAD")
                    raise BehaviorError(f"Later changes build on commit {commit}, so it can't be reversed cleanly. "
                                        "Put one file back instead: behavior_revert commit=<an earlier commit> file=<the file>.")
                if not git.run("diff", "--cached", "--name-only").strip():
                    git.run("revert", "--quit", check=False)
                    return {"commit": None, "changed": False, "note": "nothing to put back: it's already undone"}
                message = " ".join(reason.split())[:200] or f'undo "{subject}" ({commit})'
                git.run("commit", "-q", "-m", message, who)
            else:
                if not git.run("ls-tree", "-r", "--name-only", commit, "--", path).strip():
                    raise BehaviorError(f"{file} didn't exist at commit {commit}. To bring back a deleted file, use the commit before the delete.")
                git.run("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", path)
                target = self.root / path
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                git.run("checkout", commit, "--", path)
                if not git.run("diff", "--cached", "--name-only").strip():
                    return {"commit": None, "changed": False, "note": f"{file} already matches commit {commit}"}
                message = " ".join(reason.split())[:200] or f"put {path} back to {commit}"
                git.run("commit", "-q", "-m", message, who)
            made = git.run("rev-parse", "--short", "HEAD").strip()
            files = [" ".join(line.split()) for line in git.run("show", "--format=", "--name-status", made).splitlines() if line.strip()]
            self._refresh_meta()
        return {"commit": made, "changed": True, "reason": message, "files": files, "undo": f"behavior_revert commit={made}"}

    def last_commit(self) -> dict[str, Any] | None:
        with self._lock:
            return self.git.head() if (self.root / ".git").is_dir() else None

    # --- small JSON records -----------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return _read_json(self.root / f"{key}.json", default)

    def put(self, key: str, data: Any) -> None:
        _write_json(self.root / f"{key}.json", data)

    def append(self, key: str, row: dict[str, Any]) -> dict[str, Any]:
        row = {"id": row.get("id") or uuid.uuid4().hex[:10], "ts": row.get("ts") or _now(), **row}
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / f"{key}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def rows(self, key: str) -> list[dict[str, Any]]:
        try:
            lines = (self.root / f"{key}.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def rewrite(self, key: str, rows: list[dict[str, Any]]) -> None:
        tmp = self.root / f"{key}.jsonl.tmp"
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(self.root / f"{key}.jsonl")


# --- run logs -----------------------------------------------------------------------------------

CHECKS = ("R1", "R2", "R3", "R4", "R5", "R6")
IP_RX = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
MAC_RX = re.compile(r"\b[0-9a-fA-F]{2}(?:[:-]?[0-9a-fA-F]{2}){5}\b")
ENTITY_RX = re.compile(r"\b[a-z_]+\.[a-z0-9_]+\b")
EMAIL_RX = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def score(checks: dict[str, Any], broke_rule: bool = False) -> int:
    return 0 if broke_rule else sum(1 for c in CHECKS if checks.get(c) is True)


def sanitize(value: Any, names: list[str] | None = None) -> Any:
    """A copy safe to share: addresses, MACs, entity ids, emails and the house's own names replaced."""
    if isinstance(value, dict):
        return {k: sanitize(v, names) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, names) for v in value]
    if not isinstance(value, str):
        return value
    s = MAC_RX.sub("<mac>", value)
    s = IP_RX.sub("<ip>", s)
    s = EMAIL_RX.sub("<email>", s)
    s = ENTITY_RX.sub(lambda m: m.group(0).split(".")[0] + ".<id>", s)
    for i, n in enumerate(sorted({n for n in names or [] if n and len(n) > 2}, key=len, reverse=True)):
        s = re.sub(re.escape(n), f"<name{i}>", s, flags=re.IGNORECASE)
    return s
