"""Tests for skill specification parsing."""

from pathlib import Path

import pytest

from skills import SkillParseError, SkillSpec


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_skill_file():
    spec = SkillSpec.from_file(FIXTURES_DIR / "example-skill" / "SKILL.md", source="project")

    assert spec.name == "example-skill"
    assert spec.description == "Help with example workflows"
    assert spec.version == "1.0.0"
    assert spec.category == "testing"
    assert spec.tags == ["examples", "tests"]
    assert spec.dependencies == ["other-skill"]
    assert spec.body == "# Example Skill\n\nFollow the example workflow."
    assert spec.source == "project"
    assert spec.references_dir == spec.skill_dir / "references"
    assert spec.templates_dir == spec.skill_dir / "templates"
    assert spec.scripts_dir == spec.skill_dir / "scripts"
    assert spec.assets_dir == spec.skill_dir / "assets"


def test_to_dict():
    spec = SkillSpec.from_file(FIXTURES_DIR / "example-skill" / "SKILL.md", source="project")

    data = spec.to_dict()

    assert data["name"] == "example-skill"
    assert data["description"] == "Help with example workflows"
    assert data["source"] == "project"
    assert data["resource_dirs"]["references"].endswith("references")


def test_summary():
    spec = SkillSpec.from_file(FIXTURES_DIR / "example-skill" / "SKILL.md")

    assert spec.summary() == "example-skill: Help with example workflows"


def test_missing_frontmatter(tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# No frontmatter\n", encoding="utf-8")

    with pytest.raises(SkillParseError, match="Missing YAML frontmatter"):
        SkillSpec.from_file(skill_file)


def test_invalid_tags_type(tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(
        "---\nname: bad-skill\ndescription: Bad skill\ntags: wrong\n---\nBody\n",
        encoding="utf-8",
    )

    with pytest.raises(SkillParseError, match="tags"):
        SkillSpec.from_file(skill_file)
