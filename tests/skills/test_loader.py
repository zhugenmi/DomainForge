from pathlib import Path

import pytest

from app.skills.loader import SkillDescriptor, load_skill_from_dir


VALID_SKILL_MD = '''---
name: foo
description: "x"
---

# Foo

body
'''


def test_load_valid_dir(tmp_path: Path):
    d = tmp_path / "foo"
    d.mkdir()
    (d / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
    (d / "scripts").mkdir()
    (d / "scripts" / "run.py").write_text("# script", encoding="utf-8")

    desc = load_skill_from_dir(d)
    assert isinstance(desc, SkillDescriptor)
    assert desc.manifest.name == "foo"
    assert desc.path == d
    assert "SKILL.md" in desc.files
    assert "scripts/run.py" in desc.files


def test_load_missing_skill_md_raises(tmp_path: Path):
    d = tmp_path / "foo"
    d.mkdir()
    with pytest.raises(FileNotFoundError):
        load_skill_from_dir(d)


def test_load_dir_name_mismatch_raises(tmp_path: Path):
    d = tmp_path / "wrong-name"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: other\ndescription: "x"\n---\nbody\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="目录名与 name 不一致"):
        load_skill_from_dir(d)


def test_load_invalid_manifest_raises(tmp_path: Path):
    d = tmp_path / "foo"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\ndescription: "x"\n---\nbody\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="name"):
        load_skill_from_dir(d)
