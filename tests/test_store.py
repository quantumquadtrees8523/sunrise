"""Skills are checkpointed and revertable: every write saves a checkpoint (version, time, author,
reason, diff) first, a revert is a new version, a user-edited built-in is theirs, and an edit that
weakens a safety rule is refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.sunrise.store import SkillError, Store, sanitize, score, weakens_rules

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "custom_components" / "sunrise" / "bundled_skills"


def skill(name: str, body: str = "Do the thing. Then read back. Never touch the router. Say how to undo.") -> str:
    return f"---\nname: {name}\ndescription: A test skill that does one thing and when to use it.\n---\n\n" \
           f"Read references/HOUSE-BASICS.md. Done means references/RUBRIC.md passes.\n\n{body}\n"


def test_write_checkpoints_and_revert(tmp_path) -> None:
    s = Store(tmp_path)
    c1 = s.write("morning", skill("morning"), author="user", reason="new skill")
    assert c1["version"] == 1
    c2 = s.write("morning", skill("morning", "Do the thing. Then read back. Never touch the router. Say how to undo. "
                                             "The kitchen bulb is on the stairs switch."), author="agent", reason="house detail")
    assert c2["version"] == 2 and "+" in c2["diff"]
    hist = s.history("morning")
    assert [h["version"] for h in hist] == [1, 2] and hist[1]["author"] == "agent" and hist[1]["reason"] == "house detail"
    r = s.revert("morning", 1)
    assert r["version"] == 3 and s.read("morning") == skill("morning")
    assert s.history("morning")[-1]["reason"] == "revert to version 1"
    assert s.write("morning", skill("morning"), author="user", reason="same")["changed"] is False
    with pytest.raises(SkillError):
        s.revert("morning", 9)


def test_refuses_invalid_and_weakening_edits(tmp_path) -> None:
    s = Store(tmp_path)
    with pytest.raises(SkillError, match="frontmatter name"):
        s.write("x-y", skill("other"), author="user", reason="r")
    with pytest.raises(SkillError, match="rubric"):
        s.write("x-y", skill("x-y").replace("references/RUBRIC.md", "the rules"), author="user", reason="r")
    with pytest.raises(SkillError, match="author"):
        s.write("x-y", skill("x-y"), author="robot", reason="r")
    with pytest.raises(SkillError, match="why"):
        s.write("x-y", skill("x-y"), author="user", reason=" ")
    s.write("x-y", skill("x-y"), author="user", reason="new")
    with pytest.raises(SkillError, match="weaken"):
        s.write("x-y", skill("x-y", "Do the thing quickly."), author="agent", reason="shorter")
    with pytest.raises(SkillError, match="weaken"):
        s.write("x-y", skill("x-y", "Do the thing. Then read back. Never touch the router. Say how to undo. "
                                     "Skip the backup to save time."), author="agent", reason="faster")
    assert s.history("x-y")[-1]["version"] == 1


def test_built_ins_follow_the_product_until_the_user_edits_them(tmp_path) -> None:
    s = Store(tmp_path)
    # Two built-ins: the shipped builder and a second one made from it.
    shipped = tmp_path / "v1"
    for p in SHIPPED.rglob("*.md"):
        dst = shipped / p.relative_to(SHIPPED)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    other = shipped / "other-skill" / "SKILL.md"
    other.parent.mkdir()
    other.write_text((SHIPPED / "build-a-skill" / "SKILL.md").read_text(encoding="utf-8").replace("name: build-a-skill", "name: other-skill"),
                     encoding="utf-8")
    done = s.install_shipped(shipped, "0.1.0")
    assert {"build-a-skill", "other-skill"} <= set(done["added"])
    assert (tmp_path / "skills" / "build-a-skill" / "references" / "RUBRIC.md").is_file()
    meta = s.meta()["build-a-skill"]
    assert meta["origin"] == "product" and meta["user_edited"] is False
    # The user adds a house detail: now it's theirs.
    text = s.read("build-a-skill") + "\nThe hallway bulb is on the 2-way switch by the stairs.\n"
    s.write("build-a-skill", text, author="user", reason="my hallway")
    # A product update arrives with a different text: their copy is kept and flagged.
    newer = tmp_path / "v2"
    for p in shipped.rglob("*.md"):
        dst = newer / p.relative_to(shipped)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(p.read_text(encoding="utf-8").replace("Done means", "Done, always, means"), encoding="utf-8")
    done = s.install_shipped(newer, "0.2.0")
    assert "build-a-skill" in done["kept_user_copy"] and "other-skill" in done["updated"]
    assert "2-way switch" in s.read("build-a-skill")
    listed = {x["name"]: x for x in s.list()}
    assert listed["build-a-skill"]["user_edited"] and listed["build-a-skill"].get("update_available")
    assert not listed["other-skill"]["user_edited"]
    assert s.history("other-skill")[-1]["author"] == "product"


def test_weakens_rules_spots_dropped_safety_words() -> None:
    assert weakens_rules("take a backup first", "go") == ["it drops 'backup', which the current version relies on"]
    assert weakens_rules("x", "x and more") == []


def test_score_and_sanitize() -> None:
    assert score({f"R{i}": True for i in range(1, 7)}) == 6
    assert score({f"R{i}": True for i in range(1, 7)}, broke_rule=True) == 0
    s = sanitize({"a": "Kitchen Pendant 2 at 10.0.0.220 (a8:bb:50:00:00:dc) light.kitchen_pendant_2 me@x.com"}, ["Kitchen Pendant 2"])
    assert s == {"a": "<name0> at <ip> (<mac>) light.<id> <email>"}
