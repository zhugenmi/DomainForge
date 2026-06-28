import pytest

from app.skills.manifest import SkillManifest, SkillManifestError, parse_skill_md


VALID = '''---
name: legal-citation-extractor
description: "Use when extracting legal citations."
version: "1.0.0"
author: example
license: MIT
---

# Legal Citation Extractor

Body text here.
'''


def test_parse_valid_skill_md():
    m = parse_skill_md(VALID)
    assert isinstance(m, SkillManifest)
    assert m.name == "legal-citation-extractor"
    assert m.description == "Use when extracting legal citations."
    assert m.version == "1.0.0"
    assert m.author == "example"
    assert m.license == "MIT"
    assert "# Legal Citation Extractor" in m.body_md
    assert "---" not in m.body_md.splitlines()[0]


def test_parse_missing_name_raises():
    content = "---\ndescription: \"x\"\n---\nbody\n"
    with pytest.raises(SkillManifestError, match="name"):
        parse_skill_md(content)


def test_parse_missing_description_raises():
    content = "---\nname: foo\n---\nbody\n"
    with pytest.raises(SkillManifestError, match="description"):
        parse_skill_md(content)


def test_parse_invalid_name_format_raises():
    content = "---\nname: Bad_Name\ndescription: \"x\"\n---\nbody\n"
    with pytest.raises(SkillManifestError, match="name"):
        parse_skill_md(content)


def test_parse_optional_fields_default_empty():
    content = "---\nname: foo\ndescription: \"x\"\n---\nbody\n"
    m = parse_skill_md(content)
    assert m.version == ""
    assert m.author == ""
    assert m.license == ""
