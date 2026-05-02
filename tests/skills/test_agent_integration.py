"""Tests for injecting enabled skills into agent prompts."""

from unittest.mock import MagicMock

import pytest
import yaml

from config import Config, Session
from loop.agent import load_agent
from loop.runtime import BuiltinSystemPromptArgs, Runtime
from skills import SkillsManager

from tests.skills.test_manager import write_skill


@pytest.mark.asyncio
async def test_load_agent_injects_enabled_skills(tmp_path):
    project_dir = tmp_path / "project"
    write_skill(project_dir, "example", "example", "Example skill")
    config = Config(enabled_skills=["example"])
    skills_manager = SkillsManager(
        config,
        builtin_dir=tmp_path / "builtin",
        user_dir=tmp_path / "user",
        project_dir=project_dir,
    )
    skills_manager.discover_all()
    runtime = Runtime(
        config=config,
        llm=None,
        session=MagicMock(spec=Session),
        builtin_args=BuiltinSystemPromptArgs(CLI_NOW="2024-01-01T00:00:00", CLI_LANGUAGE="en"),
        skills_manager=skills_manager,
    )
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("Base prompt", encoding="utf-8")
    agent_file = tmp_path / "agent.yaml"
    agent_file.write_text(
        yaml.safe_dump({"version": 1, "agent": {"name": "test", "system_prompt_path": "system.md"}}),
        encoding="utf-8",
    )

    agent = await load_agent(agent_file, runtime)

    assert agent.system_prompt == "Base prompt\n\n# Available Skills\n- example: Example skill"
