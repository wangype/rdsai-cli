"""Skill management for extending agent prompts and tools."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from config import Config, Session, get_share_dir
from loop.toolset import BaseTool
from utils.logging import logger

if TYPE_CHECKING:
    from loop.agent import Agent


@dataclass(frozen=True, slots=True, kw_only=True)
class Skill:
    """A parsed skill definition."""

    name: str
    description: str
    version: str
    tools: list[str]
    prompt_file: str | None
    requires_env: list[str]
    enabled: bool = True


class SkillError(Exception):
    """Raised when a skill definition is invalid."""

    pass


def parse_skill_frontmatter(skill_file: Path) -> Skill:
    """Parse a SKILL.md file and return its skill definition."""
    if not skill_file.exists():
        raise SkillError(f"Skill file not found: {skill_file}")
    if not skill_file.is_file():
        raise SkillError(f"Skill path is not a file: {skill_file}")

    text = skill_file.read_text(encoding="utf-8")
    frontmatter, markdown_description = _split_frontmatter(text, skill_file)
    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as e:
        raise SkillError(f"Invalid YAML in skill file: {e}") from e
    if not isinstance(data, dict):
        raise SkillError("Skill frontmatter must be a YAML mapping")

    name = _get_str(data, "name")
    description = _get_str(data, "description", required=False) or markdown_description
    version = _get_str(data, "version")
    tools = _get_str_list(data, "tools")
    prompt_file = _get_optional_str(data, "prompt_file")
    requires_env = _get_str_list(data, "requires_env")
    enabled = bool(data.get("enabled", True))

    return Skill(
        name=name,
        description=description,
        version=version,
        tools=tools,
        prompt_file=prompt_file,
        requires_env=requires_env,
        enabled=enabled,
    )


class SkillManager:
    """Manage installed skills and apply them to loaded agents."""

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or get_share_dir() / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._skill_dirs: dict[str, Path] = {}
        self._scan()

    def list_skills(self) -> list[Skill]:
        """Return enabled skills sorted by name."""
        return sorted((skill for skill in self._skills.values() if skill.enabled), key=lambda skill: skill.name)

    def all_skills(self) -> list[Skill]:
        """Return all installed skills sorted by name."""
        return sorted(self._skills.values(), key=lambda skill: skill.name)

    def enable_skill(self, name: str) -> bool:
        """Enable a skill by name."""
        skill = self._skills.get(name)
        if skill is None:
            return False
        self._skills[name] = replace(skill, enabled=True)
        return True

    def disable_skill(self, name: str) -> bool:
        """Disable a skill by name."""
        skill = self._skills.get(name)
        if skill is None:
            return False
        self._skills[name] = replace(skill, enabled=False)
        return True

    def install_skill(self, source: str) -> Skill:
        """Install a skill from a local skill directory."""
        source_dir = Path(source).expanduser().resolve()
        if not source_dir.exists() or not source_dir.is_dir():
            raise SkillError(f"Skill source is not a directory: {source}")

        skill = parse_skill_frontmatter(source_dir / "SKILL.md")
        destination = self.skills_dir / skill.name
        if destination.resolve() != source_dir:
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source_dir, destination)

        self._skills[skill.name] = skill
        self._skill_dirs[skill.name] = destination
        return skill

    def uninstall_skill(self, name: str) -> bool:
        """Uninstall a skill by name."""
        skill_dir = self._skill_dirs.get(name)
        if skill_dir is None:
            return False
        shutil.rmtree(skill_dir)
        del self._skills[name]
        del self._skill_dirs[name]
        return True

    def apply_to_agent(self, agent: Agent) -> None:
        """Apply enabled skills to an agent by merging prompts and registering tools."""
        from loop.agent import _load_system_prompt, _load_tool
        from loop.runtime import BuiltinSystemPromptArgs, Runtime

        prompt_parts = [agent.system_prompt]
        loaded_tools: list[BaseTool[Any]] = []
        dependencies: dict[type[Any], Any] = {
            Runtime: agent.runtime,
            Config: agent.runtime.config,
            BuiltinSystemPromptArgs: agent.runtime.builtin_args,
            Session: agent.runtime.session,
        }

        for skill in self.list_skills():
            if any(os.environ.get(env_var) is None for env_var in skill.requires_env):
                logger.info("Skipping skill with missing environment variable: {skill}", skill=skill.name)
                continue

            skill_dir = self._skill_dirs[skill.name]
            if skill.prompt_file:
                prompt_path = skill_dir / skill.prompt_file
                if prompt_path.exists() and prompt_path.is_file():
                    prompt_parts.append(_load_system_prompt(prompt_path, {}, agent.runtime.builtin_args))

            for tool_path in skill.tools:
                tool = _load_tool(tool_path, dependencies)
                if tool is not None:
                    loaded_tools.append(tool)
                else:
                    logger.warning("Failed to load skill tool: {tool_path}", tool_path=tool_path)

        object.__setattr__(agent, "system_prompt", "\n\n".join(part for part in prompt_parts if part))
        agent.toolset.add_tools(loaded_tools)

    def _scan(self) -> None:
        for skill_dir in sorted(path for path in self.skills_dir.iterdir() if path.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                skill = parse_skill_frontmatter(skill_file)
            except SkillError as e:
                logger.warning("Skipping invalid skill {path}: {error}", path=skill_file, error=e)
                continue
            self._skills[skill.name] = skill
            self._skill_dirs[skill.name] = skill_dir


def _split_frontmatter(text: str, skill_file: Path) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise SkillError(f"Skill file missing YAML frontmatter: {skill_file}")
    end = text.find("\n---", 4)
    if end == -1:
        raise SkillError(f"Skill file has unterminated YAML frontmatter: {skill_file}")
    frontmatter = text[4:end]
    markdown = text[end + 4 :].strip()
    return frontmatter, markdown


def _get_str(data: dict[Any, Any], key: str, *, required: bool = True) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise SkillError(f"Skill field '{key}' must be a string")
    return value


def _get_optional_str(data: dict[Any, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SkillError(f"Skill field '{key}' must be a string or null")
    return value


def _get_str_list(data: dict[Any, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SkillError(f"Skill field '{key}' must be a list of strings")
    return value
