"""Memory: Markdown files the agent writes and the owner can read, checkpointed, guarded, listed in
the prompt and shown as sensor.sunrise_memory."""

from __future__ import annotations

from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.sunrise.const import LLM_API_ID
from custom_components.sunrise.store import MEMORY_MAX_BYTES, MemoryError_, Store

from .conftest import call, setup_integration


def test_write_read_list_history_revert_and_delete(tmp_path: Path) -> None:
    s = Store(tmp_path)
    first = s.memory_write("house.md", "# House\n2026-01-02: two floors, router in the hall.", reason="first look")
    assert first["changed"] and first["version"] == 1
    assert (tmp_path / "memory" / "house.md").read_text().endswith("hall.\n")  # a plain file the owner can open
    s.memory_write("playbooks/router.md", "# Router\nAdmin page is at the gateway address.", reason="learned today")
    assert s.memory_write("house.md", "# House\n2026-01-02: two floors, router in the hall.", reason="same")["changed"] is False
    second = s.memory_write("house.md", "# House\n2026-01-03: three floors.", author="user", reason="they corrected me")
    assert second["version"] == 2 and "-2026-01-02" in second["diff"]
    listed = {f["name"]: f for f in s.memory_list()}
    assert set(listed) == {"house.md", "playbooks/router.md"} and listed["house.md"]["first_line"] == "House"
    assert [v["version"] for v in s.memory_history("house.md")] == [1, 2]
    assert s.memory_revert("house.md", 1)["version"] == 3 and "two floors" in s.memory_read("house.md")
    gone = s.memory_delete("house.md", reason="wrong house")
    assert gone["deleted"] and s.memory_read("house.md") is None and gone["undo"]
    assert s.memory_history("house.md")[-1]["deleted"] is True
    assert "two floors" in (s.memory_revert("house.md", 3) and s.memory_read("house.md"))  # a delete can be undone


@pytest.mark.parametrize("name", ["../skills/x.md", "/etc/passwd", "notes.txt", "House.md", "a/b/c/d.md", "", ".hidden.md", "a/../b.md"])
def test_names_stay_inside_the_memory_folder(tmp_path: Path, name: str) -> None:
    with pytest.raises(MemoryError_):
        Store(tmp_path).memory_write(name, "x", reason="r")
    assert not list(tmp_path.rglob("*.md")) and not list(tmp_path.rglob("*.txt"))


@pytest.mark.parametrize("text", [
    "The Wi-Fi password is hunter2abc", "token: abcd1234efgh", "api_key=sk-test-0000000000000000000000",
    "-----BEGIN OPENSSH PRIVATE KEY-----\nabc", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
    "ha token eyJhbGciOiJIUzI1NiIsInR5cCI6.eyJpc3MiOiJhYmMiLCJpYXQiOjE3.SflKxwRJSMeKKF2QT4fwpM"])
def test_secrets_are_refused(tmp_path: Path, text: str) -> None:
    s = Store(tmp_path)
    with pytest.raises(MemoryError_, match="secret"):
        s.memory_write("house.md", f"# House\n{text}\n", reason="r")
    assert s.memory_list() == []


def test_plain_talk_about_passwords_is_fine_and_size_and_reason_are_checked(tmp_path: Path) -> None:
    s = Store(tmp_path)
    assert s.memory_write("owner.md", "# Owner\nThe router password is on the sticker; they type it themselves.", reason="how they sign in")["changed"]
    with pytest.raises(MemoryError_, match="too long"):
        s.memory_write("log.md", "x" * (MEMORY_MAX_BYTES + 1), reason="r")
    with pytest.raises(MemoryError_, match="why"):
        s.memory_write("log.md", "x", reason=" ")
    with pytest.raises(MemoryError_, match="empty"):
        s.memory_write("log.md", "  ", reason="r")


async def test_tools_prompt_and_sensor(hass: HomeAssistant, hass_admin_user, hass_read_only_user) -> None:
    await setup_integration(hass)
    assert hass.states.get("sensor.sunrise_memory").state == "0"
    saved = await call(hass, "memory_write", {"name": "owner.md", "text": "# Owner\n2026-01-02: wants one recommendation, not a menu.",
                                              "reason": "they said so"}, hass_admin_user.id)
    assert saved.data["changed"] and saved.data["version"] == 1
    await hass.async_block_till_done()
    state = hass.states.get("sensor.sunrise_memory")
    assert state.state == "1" and state.attributes["files"][0]["name"] == "owner.md"
    assert state.attributes["files"][0]["first_line"] == "Owner" and state.attributes["folder"].endswith("sunrise/memory")
    assert "one recommendation" in (await call(hass, "memory_read", {"name": "owner.md"})).data["text"]
    assert [f["name"] for f in (await call(hass, "memory_list")).data["files"]] == ["owner.md"]
    refused = await call(hass, "memory_write", {"name": "owner.md", "text": "password: hunter2abc", "reason": "r"}, hass_admin_user.id)
    assert refused.data["ok"] is False and "secret" in refused.data["error"]
    outside = await call(hass, "memory_read", {"name": "../skills.json"})
    assert outside.data["ok"] is False
    reader = await call(hass, "memory_write", {"name": "x.md", "text": "x", "reason": "r"}, hass_read_only_user.id)
    assert "administrator" in reader.data["error"]

    ctx = llm.LLMContext(platform="mcp_server", context=None, language="en", assistant="conversation", device_id=None)
    prompt = (await llm.async_get_api(hass, LLM_API_ID, ctx)).api_prompt
    assert "- owner.md: Owner" in prompt and "Never store passwords" in prompt

    assert (await call(hass, "memory_history", {"name": "owner.md"})).data["versions"][0]["reason"] == "they said so"
    await call(hass, "memory_delete", {"name": "owner.md", "reason": "test"}, hass_admin_user.id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sunrise_memory").state == "0"
    back = await call(hass, "memory_revert", {"name": "owner.md", "version": 1}, hass_admin_user.id)
    assert back.data["changed"]
