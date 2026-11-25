"""Files this integration keeps in the user's data folder (outside custom_components, so an
integration update never overwrites them). Plain Python, no Home Assistant imports: blocking file
I/O, so Home Assistant code calls it in the executor.

<config>/sunrise/
  skills/<name>/SKILL.md          the live text of every skill (built-in copies and the user's own)
  skills/<name>/references/       RUBRIC.md and HOUSE-BASICS.md, rewritten from the shipped copy
  history/<name>/v0001.json ...   one checkpoint per write: version, time, author, reason, diff, text
  skills.json                     per skill: origin, version, shipped hash, user_edited
  memory/**/*.md                  what the agent remembers about this house and its owner: plain
                                  Markdown the owner can open, e.g. owner.md, house.md, playbooks/x.md
  memory_history/<file>/v0001.json  one checkpoint per memory write or delete
  profile.json, suggestions.json, audit.json, changes.jsonl, runs.jsonl
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
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


class Store:
    """Everything under one data folder."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.history_dir = self.root / "history"
        self.meta_path = self.root / "skills.json"

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

    def write(self, name: str, text: str, *, author: str, reason: str, check_rules: bool = True) -> dict[str, Any]:
        """The one way a skill's text changes: validate, checkpoint, write. Returns the checkpoint."""
        if author not in AUTHORS:
            raise SkillError(f"author must be one of {', '.join(AUTHORS)}")
        if not (reason or "").strip():
            raise SkillError("say why (reason) the skill changes")
        text = text if text.endswith("\n") else text + "\n"
        problems = validate_skill(name, text)
        if problems:
            raise SkillError("Not saved: " + "; ".join(problems) + ".")
        old = self.read(name) or ""
        if old == text:
            return {"name": name, "version": self.meta().get(name, {}).get("version", 0), "changed": False}
        if check_rules and author != "product" and old:
            weak = weakens_rules(old, text)
            if weak:
                raise SkillError("Not saved: the change would weaken the safety rules (" + "; ".join(weak) + ").")
        meta = self.meta()
        entry = meta.setdefault(name, {"origin": "product" if author == "product" else "user", "version": 0})
        version = int(entry.get("version", 0)) + 1
        checkpoint = {"name": name, "version": version, "ts": _now(), "author": author, "reason": reason.strip(),
                      "diff": diff(old, text, name), "text": text, "previous_sha": sha(old) if old else None}
        _write_json(self.history_dir / name / f"v{version:04d}.json", checkpoint)
        path = self.skill_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        entry["version"] = version
        entry["sha"] = sha(text)
        if author == "product":
            entry["shipped_sha"] = sha(text)
            entry["user_edited"] = False
            entry.pop("update_available", None)
        elif entry.get("origin") == "product":
            entry["user_edited"] = True  # theirs now: a product update never replaces it
        _write_json(self.meta_path, meta)
        return {k: checkpoint[k] for k in ("name", "version", "ts", "author", "reason", "diff")} | {"changed": True}

    def history(self, name: str) -> list[dict[str, Any]]:
        folder = self.history_dir / name
        out = []
        for p in sorted(folder.glob("v*.json")) if folder.is_dir() else []:
            c = _read_json(p, {})
            out.append({k: c.get(k) for k in ("version", "ts", "author", "reason")} | {"lines_changed": _changed(c.get("diff", ""))})
        return out

    def checkpoint(self, name: str, version: int) -> dict[str, Any] | None:
        c = _read_json(self.history_dir / name / f"v{int(version):04d}.json", None)
        return c if isinstance(c, dict) else None

    def revert(self, name: str, version: int, *, author: str = "user") -> dict[str, Any]:
        """Put version `version`'s text back, as a new checkpoint (history is never rewritten)."""
        c = self.checkpoint(name, version)
        if not c:
            raise SkillError(f"{name} has no version {version}; skill_history lists them")
        return self.write(name, c["text"], author=author, reason=f"revert to version {version}", check_rules=False)

    def list(self) -> list[dict[str, Any]]:
        meta = self.meta()
        out = []
        for p in sorted(self.skills_dir.glob("*/SKILL.md")) if self.skills_dir.is_dir() else []:
            name = p.parent.name
            fm = frontmatter(p.read_text(encoding="utf-8"))
            m = meta.get(name, {})
            out.append({"name": name, "description": fm.get("description", ""), "origin": m.get("origin", "user"),
                        "version": m.get("version", 0), "user_edited": bool(m.get("user_edited")),
                        **({"update_available": True} if m.get("update_available") else {})})
        return out

    def install_shipped(self, shipped: Path, version: str) -> dict[str, list[str]]:
        """Copy the integration's built-in skills in. New ones are added; untouched ones follow the
        product; a copy the user edited is kept and only flagged `update_available`."""
        done: dict[str, list[str]] = {"added": [], "updated": [], "kept_user_copy": []}
        refs = shipped / "_shared"
        meta = self.meta()
        for src in sorted(shipped.glob("*/SKILL.md")):
            name = src.parent.name
            text = src.read_text(encoding="utf-8")
            current = self.read(name)
            m = meta.get(name, {})
            if current is None:
                self.write(name, text, author="product", reason=f"installed with Sunrise {version}")
                done["added"].append(name)
            elif current == text:
                pass
            elif m.get("user_edited") or m.get("origin") == "user":
                if m.get("shipped_sha") != sha(text):
                    meta = self.meta()
                    meta.setdefault(name, {})["update_available"] = True
                    _write_json(self.meta_path, meta)
                done["kept_user_copy"].append(name)
            else:
                self.write(name, text, author="product", reason=f"updated with Sunrise {version}")
                done["updated"].append(name)
            meta = self.meta()
        for folder in self.skills_dir.glob("*/") if self.skills_dir.is_dir() else []:
            (folder / "references").mkdir(exist_ok=True)
            for ref in REFERENCES:
                if (refs / ref).is_file():
                    shutil.copyfile(refs / ref, folder / "references" / ref)
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

    def _memory_history(self, name: str) -> Path:
        return self.root / "memory_history" / name[:-3].replace("/", "__")

    def _memory_checkpoint(self, name: str, old: str, new: str | None, author: str, reason: str) -> dict[str, Any]:
        folder = self._memory_history(name)
        version = len(list(folder.glob("v*.json"))) + 1 if folder.is_dir() else 1
        c = {"name": name, "version": version, "ts": _now(), "author": author, "reason": reason.strip(),
             "diff": diff(old, new or "", name), "text": new, "deleted": new is None}
        _write_json(folder / f"v{version:04d}.json", c)
        return c

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
        """Replace one memory file's whole text. The old text is checkpointed first."""
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
        old = self.memory_read(name)
        if old == text:
            return {"name": name, "changed": False}
        if old is None and len(self.memory_list()) >= MEMORY_MAX_FILES:
            raise MemoryError_(f"there are already {MEMORY_MAX_FILES} memory files; merge or delete some first")
        c = self._memory_checkpoint(name, old or "", text, author, reason)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {k: c[k] for k in ("name", "version", "ts", "author", "reason", "diff")} | {"changed": True}

    def memory_delete(self, name: str, *, author: str = "agent", reason: str) -> dict[str, Any]:
        path = self.memory_path(name)
        name = path.relative_to(self.memory_dir).as_posix()
        old = self.memory_read(name)
        if old is None:
            raise MemoryError_(f"no memory file {name!r}; memory_list lists them")
        if not (reason or "").strip():
            raise MemoryError_("say why (reason) it's deleted, in one line")
        c = self._memory_checkpoint(name, old, None, author, reason)
        path.unlink()
        return {"name": name, "deleted": True, "version": c["version"],
                "undo": f"memory_revert name={name} version={c['version'] - 1}" if c["version"] > 1 else None}

    def memory_history(self, name: str) -> list[dict[str, Any]]:
        self.memory_path(name)
        folder = self._memory_history(name.strip().lstrip("/"))
        out = []
        for p in sorted(folder.glob("v*.json")) if folder.is_dir() else []:
            c = _read_json(p, {})
            out.append({k: c.get(k) for k in ("version", "ts", "author", "reason", "deleted")} | {"lines_changed": _changed(c.get("diff", ""))})
        return out

    def memory_revert(self, name: str, version: int, *, author: str = "agent") -> dict[str, Any]:
        """Put an earlier version's text back, as a new checkpoint."""
        self.memory_path(name)
        name = name.strip().lstrip("/")
        c = _read_json(self._memory_history(name) / f"v{int(version):04d}.json", None)
        if not isinstance(c, dict) or c.get("text") is None:
            raise MemoryError_(f"{name} has no version {version} with text; memory_history lists them")
        return self.memory_write(name, c["text"], author=author, reason=f"revert to version {version}")

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


def _changed(d: str) -> int:
    return sum(1 for line in d.splitlines() if line[:1] in "+-" and not line.startswith(("+++", "---")))


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
