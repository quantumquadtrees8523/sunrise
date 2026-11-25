"""Copy the canonical skills (skills/) into the places they ship from:

- each skill's own references/ folder (RUBRIC.md, HOUSE-BASICS.md), so a skill installed alone with
  `npx skills add` still has the rubric it points to;
- the integration's bundled_skills/ folder, which HACS installs with the integration.

`python3 scripts/sync_skills.py` writes; `--check` exits 1 if anything is stale (a test runs it).
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SHARED = SKILLS / "_shared"
BUNDLED = ROOT / "custom_components" / "sunrise" / "bundled_skills"


def plan() -> list[tuple[Path, Path]]:
    pairs = []
    for skill in sorted(p.parent for p in SKILLS.glob("*/SKILL.md")):
        for ref in sorted(SHARED.glob("*.md")):
            pairs.append((ref, skill / "references" / ref.name))
        pairs.append((skill / "SKILL.md", BUNDLED / skill.name / "SKILL.md"))
    for ref in sorted(SHARED.glob("*.md")):
        pairs.append((ref, BUNDLED / "_shared" / ref.name))
    return pairs


def main(check: bool) -> int:
    stale = [dst for src, dst in plan() if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False)]
    wanted = {dst for _src, dst in plan()}
    extra = [p for p in BUNDLED.rglob("*.md") if p not in wanted] if BUNDLED.is_dir() else []
    if check:
        for p in stale + extra:
            print(f"stale: {p.relative_to(ROOT)}")
        return 1 if stale or extra else 0
    for src, dst in plan():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    for p in extra:
        p.unlink()
    print(f"synced {len(plan())} files")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
