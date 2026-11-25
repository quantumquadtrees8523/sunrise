"""Every SKILL.md is a valid Agent Skill (agentskills.io: name + description frontmatter, name
matches its folder, lowercase-hyphen, <= 64 chars; description <= 1024) and cites the shared rubric,
and the copies that ship (references/, the integration's bundled_skills/) are in sync."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from custom_components.sunrise.store import frontmatter, validate_skill

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted(p for p in (ROOT / "skills").glob("*/SKILL.md"))
V0 = {"add-a-device", "build-a-skill", "device-diagnosis", "improve-home", "learn-the-house", "routines", "undo", "wifi-diagnosis"}


def test_the_v0_skills_are_all_here() -> None:
    assert {p.parent.name for p in SKILLS} == V0


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_is_valid_and_cites_the_rubric(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert validate_skill(path.parent.name, text) == []
    fm = frontmatter(text)
    assert 40 < len(fm["description"]) <= 1024
    assert "references/RUBRIC.md" in text and "references/HOUSE-BASICS.md" in text
    assert (path.parent / "references" / "RUBRIC.md").is_file()
    assert len(text.splitlines()) <= 160, "keep skills short"


def test_rubric_has_the_owners_checks_and_safety_rules() -> None:
    rubric = (ROOT / "skills" / "_shared" / "RUBRIC.md").read_text(encoding="utf-8")
    for words in ("read", "Plain words", "At most 3", "Never a wrong instruction", "without read-back", "No jargon",
                  "Never change router settings", "backup"):
        assert words in rubric, words
    assert all(f"| R{i} |" in rubric for i in range(1, 7)) and all(f"S{i}:" in rubric for i in range(1, 8))


def test_skills_are_general_and_use_memory_for_the_specifics() -> None:
    """A shipped skill holds the method; one house's brands, models and addresses belong in memory."""
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        assert "memory_" in text or "house.md" in text, path.parent.name
        assert not re.search(r"\b(WiZ|Verizon|Fios|CR1000|Spectrum|Govee|\d+\.\d+\.\d+\.\d+)\b", text), path.parent.name


def test_the_router_rule_reads_the_same_everywhere() -> None:
    rubric = (ROOT / "skills" / "_shared" / "RUBRIC.md").read_text(encoding="utf-8")
    basics = (ROOT / "skills" / "_shared" / "HOUSE-BASICS.md").read_text(encoding="utf-8")
    from custom_components.sunrise.api import RULES  # noqa: PLC0415

    for text in (rubric, basics, RULES):
        flat = " ".join(text.split())
        assert "yes to each change" in flat or "yes to this one change" in flat
        assert "password" in flat


def test_every_handoff_names_a_skill_that_exists_and_every_skill_says_its_handoffs() -> None:
    """Skills chain by naming each other in one line; a name that isn't a shipped skill is a dead end."""
    from custom_components.sunrise.api import RULES  # noqa: PLC0415

    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        assert "## Hands off to / called from" in text, path.parent.name
        named = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", text))
        assert named <= V0, (path.parent.name, named - V0)
    assert set(re.findall(r"\b([a-z]+(?:-[a-z]+){1,2})\b(?= then| first)", RULES)) <= V0


def test_house_basics_is_not_a_skill() -> None:
    assert not (ROOT / "skills" / "_shared" / "SKILL.md").exists()


def test_shipped_copies_are_in_sync() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_skills.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + "\nrun: python3 scripts/sync_skills.py"


def test_house_basics_says_what_needs_the_internet() -> None:
    assert "Internet" in (ROOT / "skills" / "_shared" / "HOUSE-BASICS.md").read_text(encoding="utf-8")


def test_every_tool_a_skill_names_exists() -> None:
    """The shared basics list exactly the tools the integration serves, and no skill, README or
    plugin text names a tool that was removed."""
    from custom_components.sunrise.api import SPECS

    tools = {s.name for s in SPECS}
    basics = (ROOT / "skills" / "_shared" / "HOUSE-BASICS.md").read_text(encoding="utf-8")
    listed = basics.split("Their names are", 1)[1].split("When several", 1)[0]
    assert set(re.findall(r"`([a-z_]+)`", listed)) == tools
    gone = {"profile_get", "profile_update", "skill_history", "skill_revert", "memory_history", "memory_revert"}
    texts = [*ROOT.glob("skills/**/*.md"), ROOT / "README.md", *ROOT.glob("claude-plugin/**/*.md")]
    for path in texts:
        text = path.read_text(encoding="utf-8")
        assert not {g for g in gone if g in text}, path
        assert "`suggestions`" not in text, path
