"""Skills live in git: every write is one commit (who, why), a revert is a new commit, a user-edited
built-in is theirs, and an edit that weakens a safety rule is refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.sunrise.store import BehaviorError, SkillError, Store, sanitize, score, weakens_rules

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "custom_components" / "sunrise" / "bundled_skills"


def skill(name: str, body: str = "Do the thing. Then read back. Never touch the router. Say how to undo.") -> str:
    return f"---\nname: {name}\ndescription: A test skill that does one thing and when to use it.\n---\n\n" \
           f"Read references/HOUSE-BASICS.md. Done means references/RUBRIC.md passes.\n\n{body}\n"


def test_each_write_is_a_commit_and_a_revert_is_a_new_one(tmp_path) -> None:
    s = Store(tmp_path)
    c1 = s.write("morning", skill("morning"), author="user", reason="new skill")
    assert c1["commit"] and c1["changed"]
    c2 = s.write("morning", skill("morning", "Do the thing. Then read back. Never touch the router. Say how to undo. "
                                             "The kitchen bulb is on the stairs switch."), author="agent", reason="house detail")
    assert c2["commit"] != c1["commit"] and "+" in c2["diff"]
    hist = s.behavior_log("morning")
    assert [h["reason"] for h in hist] == ["house detail", "new skill"] and [h["author"] for h in hist] == ["agent", "user"]
    assert hist[0]["files"] == ["M skills/morning/SKILL.md"]
    assert "stairs switch" in s.behavior_log(commit=c2["commit"])[0]["diff"]
    r = s.behavior_revert(c2["commit"], author="user")
    assert r["changed"] and s.read("morning") == skill("morning")
    assert s.behavior_log("skills/morning")[0]["reason"] == f'undo "house detail" ({c2["commit"]})'
    assert len(s.behavior_log("morning")) == 3  # history is added to, never rewritten
    assert s.write("morning", skill("morning"), author="user", reason="same")["changed"] is False
    with pytest.raises(BehaviorError):
        s.behavior_revert("0000000")
    with pytest.raises(BehaviorError):
        s.behavior_revert("--hard")


def test_the_repository_tracks_behavior_only_and_has_no_remote(tmp_path) -> None:
    s = Store(tmp_path)
    s.write("morning", skill("morning"), author="user", reason="new skill")
    s.memory_write("house.md", "# House\nTwo floors.", reason="first look")
    s.put("audit", {"x": 1})
    s.append("runs", {"skill": "morning"})
    (tmp_path / "secrets.yaml").write_text("wifi: hunter2", encoding="utf-8")
    s.behavior_log()  # anything changed on disk is committed first
    tracked = set(s.git.run("ls-files").split())
    assert tracked == {".gitignore", "memory/house.md", "skills/morning/SKILL.md"}
    assert s.git.run("status", "--short").strip() == ""  # everything else is ignored
    assert s.git.run("remote").strip() == ""
    assert not (tmp_path / "history").exists() and not (tmp_path / "memory_history").exists()


def test_an_edit_made_by_hand_is_committed_as_the_users(tmp_path) -> None:
    s = Store(tmp_path)
    s.memory_write("house.md", "# House\nTwo floors.", reason="first look")
    (tmp_path / "memory" / "house.md").write_text("# House\nThree floors.\n", encoding="utf-8")
    top = s.behavior_log("house.md")[0]
    assert top["author"] == "user" and top["reason"] == "edited on disk"


def test_one_file_can_go_back_to_an_earlier_commit(tmp_path) -> None:
    s = Store(tmp_path)
    one = s.memory_write("house.md", "# House\nTwo floors.", reason="first look")
    s.memory_write("owner.md", "# Owner\nShort answers.", reason="they said so")
    s.memory_write("house.md", "# House\nThree floors.", reason="recount")
    back = s.behavior_revert(one["commit"], "house.md", reason="the recount was wrong")
    assert back["files"] == ["M memory/house.md"] and "Two floors" in s.memory_read("house.md")
    assert "Short answers" in s.memory_read("owner.md")  # nothing else moved
    assert s.behavior_revert(one["commit"], "house.md")["changed"] is False
    with pytest.raises(BehaviorError, match="didn't exist"):
        s.behavior_revert(one["commit"], "owner.md")


def test_without_git_the_error_says_what_to_do(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(BehaviorError, match="needs the git program"):
        Store(tmp_path / "data").memory_write("house.md", "# House", reason="r")


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
    assert [h["reason"] for h in s.behavior_log("x-y")] == ["new"]


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
    assert s.behavior_log("other-skill")[0]["author"] == "product" and s.behavior_log("other-skill")[0]["reason"] == "Sunrise 0.2.0: built-in skills"
    # Putting their copy back to the shipped text makes it a built-in again.
    first = s.behavior_log("build-a-skill")[-1]["commit"]
    s.behavior_revert(first, "build-a-skill")
    assert not {x["name"]: x for x in s.list()}["build-a-skill"]["user_edited"]


def test_weakens_rules_spots_dropped_safety_words() -> None:
    assert weakens_rules("take a backup first", "go") == ["it drops 'backup', which the current version relies on"]
    assert weakens_rules("x", "x and more") == []


def test_score_and_sanitize() -> None:
    assert score({f"R{i}": True for i in range(1, 7)}) == 6
    assert score({f"R{i}": True for i in range(1, 7)}, broke_rule=True) == 0
    s = sanitize({"a": "Kitchen Pendant 2 at 10.0.0.220 (a8:bb:50:00:00:dc) light.kitchen_pendant_2 me@x.com"}, ["Kitchen Pendant 2"])
    assert s == {"a": "<name0> at <ip> (<mac>) light.<id> <email>"}
