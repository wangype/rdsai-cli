"""Tests for loop.skills module."""

from __future__ import annotations

from pathlib import Path

from config import Config, Session
from loop.agent import Agent
from loop.runtime import BuiltinSystemPromptArgs, Runtime
from loop.skills import SkillManager, parse_skill_frontmatter
from loop.toolset import DynamicToolset


def test_parse_skill_frontmatter(tmp_path: Path) -> None:
    """Test valid YAML frontmatter parsing."""
    skill_dir = _write_skill(tmp_path, name="sql-explain", description="Explain SQL", version="1.2.3")

    skill = parse_skill_frontmatter(skill_dir / "SKILL.md")

    assert skill.name == "sql-explain"
    assert skill.description == "Explain SQL"
    assert skill.version == "1.2.3"
    assert skill.tools == []
    assert skill.prompt_file == "prompt.md"
    assert skill.requires_env == []
    assert skill.enabled is True


def test_list_skills_sorts_by_name(tmp_path: Path) -> None:
    """Test that enabled skills are returned alphabetically."""
    _write_skill(tmp_path, name="zeta")
    _write_skill(tmp_path, name="alpha")
    _write_skill(tmp_path, name="middle")

    manager = SkillManager(tmp_path)

    assert [skill.name for skill in manager.list_skills()] == ["alpha", "middle", "zeta"]


def test_enable_disable_skill(tmp_path: Path) -> None:
    """Test toggling enabled state."""
    _write_skill(tmp_path, name="sql-explain")
    manager = SkillManager(tmp_path)

    assert manager.disable_skill("sql-explain") is True
    assert manager.list_skills() == []
    assert manager.enable_skill("sql-explain") is True
    assert [skill.name for skill in manager.list_skills()] == ["sql-explain"]
    assert manager.disable_skill("missing") is False


def test_apply_to_agent_merges_prompt_and_tools(tmp_path: Path, monkeypatch) -> None:
    """Test applying a skill appends its prompt and registers tools."""
    tool_module = _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_skill(
        tmp_path,
        name="sql-explain",
        prompt="Skill prompt text",
        tools=[f"{tool_module}:DummySkillTool"],
    )
    manager = SkillManager(tmp_path)
    agent = _make_agent(manager)

    manager.apply_to_agent(agent)

    assert agent.system_prompt == "Base prompt\n\nSkill prompt text"
    assert agent.toolset.has_tool("DummySkillTool")


def test_apply_to_agent_skips_skill_with_missing_env(tmp_path: Path, monkeypatch) -> None:
    """Test skills with missing required environment variables are skipped."""
    tool_module = _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv("RDSAI_SKILL_TEST_ENV", raising=False)
    _write_skill(
        tmp_path,
        name="env-skill",
        prompt="Should not appear",
        tools=[f"{tool_module}:DummySkillTool"],
        requires_env=["RDSAI_SKILL_TEST_ENV"],
    )
    manager = SkillManager(tmp_path)
    agent = _make_agent(manager)

    manager.apply_to_agent(agent)

    assert agent.system_prompt == "Base prompt"
    assert not agent.toolset.has_tool("DummySkillTool")


def test_install_skill_from_local_path(tmp_path: Path) -> None:
    """Test installing a skill from a local directory."""
    skills_dir = tmp_path / "installed"
    source_dir = _write_skill(tmp_path / "source", name="installable")
    manager = SkillManager(skills_dir)

    skill = manager.install_skill(str(source_dir))

    assert skill.name == "installable"
    assert (skills_dir / "installable" / "SKILL.md").exists()
    assert [installed.name for installed in manager.list_skills()] == ["installable"]


def test_uninstall_skill(tmp_path: Path) -> None:
    """Test uninstalling a skill removes its directory."""
    _write_skill(tmp_path, name="sql-explain")
    manager = SkillManager(tmp_path)

    assert manager.uninstall_skill("sql-explain") is True
    assert not (tmp_path / "sql-explain").exists()
    assert manager.list_skills() == []
    assert manager.uninstall_skill("missing") is False


def _write_skill(
    skills_dir: Path,
    *,
    name: str,
    description: str = "Test skill",
    version: str = "1.0.0",
    prompt: str = "Prompt text",
    prompt_file: str | None = "prompt.md",
    tools: list[str] | None = None,
    requires_env: list[str] | None = None,
) -> Path:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    tools = tools or []
    requires_env = requires_env or []
    prompt_file_yaml = "null" if prompt_file is None else f'"{prompt_file}"'
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "\n".join(
            [
                "---",
                f'name: "{name}"',
                f'description: "{description}"',
                f'version: "{version}"',
                f"tools: {tools}",
                f"prompt_file: {prompt_file_yaml}",
                f"requires_env: {requires_env}",
                "---",
                description,
            ]
        ),
        encoding="utf-8",
    )
    if prompt_file is not None:
        (skill_dir / prompt_file).write_text(prompt, encoding="utf-8")
    return skill_dir


def _write_tool_module(tmp_path: Path) -> str:
    module_name = "dummy_skill_tool"
    (tmp_path / f"{module_name}.py").write_text(
        "\n".join(
            [
                "from loop.toolset import BaseTool, ToolOk",
                "",
                "",
                "class DummySkillTool(BaseTool):",
                '    name = "DummySkillTool"',
                '    description = "Dummy skill tool"',
                "    params = type(None)",
                "",
                "    async def __call__(self, params):",
                "        return ToolOk(output='ok')",
            ]
        ),
        encoding="utf-8",
    )
    return module_name


def _make_agent(skill_manager: SkillManager) -> Agent:
    runtime = Runtime(
        config=Config(),
        llm=None,
        session=Session(id="test-session"),
        builtin_args=BuiltinSystemPromptArgs(CLI_NOW="2024-01-01T00:00:00+00:00", CLI_LANGUAGE="en"),
        skill_manager=skill_manager,
    )
    return Agent(name="test-agent", system_prompt="Base prompt", toolset=DynamicToolset(), runtime=runtime)
