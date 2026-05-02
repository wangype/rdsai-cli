"""Tests for skill discovery and enablement."""

import json
from pathlib import Path

import pytest

from config import Config, load_config
from skills import SkillNotFoundError, SkillsManager


def write_skill(root: Path, dirname: str, name: str, description: str) -> None:
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nBody\n",
        encoding="utf-8",
    )


def test_discover_all_with_priority(tmp_path):
    builtin_dir = tmp_path / "builtin"
    user_dir = tmp_path / "user"
    project_dir = tmp_path / "project"
    write_skill(builtin_dir, "common", "common-skill", "Builtin description")
    write_skill(user_dir, "common", "common-skill", "User description")
    write_skill(project_dir, "common", "common-skill", "Project description")
    write_skill(user_dir, "user-only", "user-only", "User only")

    manager = SkillsManager(
        Config(),
        builtin_dir=builtin_dir,
        user_dir=user_dir,
        project_dir=project_dir,
    )

    skills = manager.discover_all()

    assert [skill.name for skill in skills] == ["common-skill", "user-only"]
    assert manager.get("common-skill").description == "Project description"
    assert manager.get("common-skill").source == "project"


def test_enable_disable_persists_config(tmp_path):
    config_file = tmp_path / "config.json"
    project_dir = tmp_path / "project"
    write_skill(project_dir, "example", "example", "Example skill")
    config = Config()
    manager = SkillsManager(
        config,
        config_file=config_file,
        builtin_dir=tmp_path / "builtin",
        user_dir=tmp_path / "user",
        project_dir=project_dir,
    )
    manager.discover_all()

    manager.enable("example")

    assert config.enabled_skills == ["example"]
    assert json.loads(config_file.read_text(encoding="utf-8"))["enabled_skills"] == ["example"]
    assert [skill.name for skill in manager.list_enabled()] == ["example"]

    manager.disable("example")

    assert config.enabled_skills == []
    assert json.loads(config_file.read_text(encoding="utf-8"))["enabled_skills"] == []


def test_enable_missing_skill_raises(tmp_path):
    manager = SkillsManager(
        Config(),
        builtin_dir=tmp_path / "builtin",
        user_dir=tmp_path / "user",
        project_dir=tmp_path / "project",
    )

    with pytest.raises(SkillNotFoundError, match="missing"):
        manager.enable("missing")


def test_load_config_accepts_enabled_skills(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"enabled_skills": ["example"]}', encoding="utf-8")

    config = load_config(config_file)

    assert config.enabled_skills == ["example"]
