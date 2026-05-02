"""Skill discovery and enablement management."""

from __future__ import annotations

from pathlib import Path

from config.app import Config, save_config
from config.base import get_share_dir, get_skills_dir
from skills.errors import SkillNotFoundError, SkillParseError
from skills.spec import SKILL_FILE_NAME, SkillSpec
from utils.logging import logger


class SkillsManager:
    """Discover skills from builtin, user, and project locations."""

    def __init__(
        self,
        config: Config,
        *,
        config_file: Path | None = None,
        builtin_dir: Path | None = None,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._config_file = config_file
        self._builtin_dir = builtin_dir or get_skills_dir()
        self._user_dir = user_dir or (get_share_dir() / "skills")
        self._project_dir = project_dir or (Path.cwd() / ".rdsai-skills")
        self._skills: dict[str, SkillSpec] = {}
        self._discovered: bool = False  # track whether discovery has been attempted

    @property
    def config(self) -> Config:
        """Return the underlying application config."""
        return self._config

    def discover_all(self) -> list[SkillSpec]:
        """Discover all skills, applying priority project > user > builtin for duplicate names."""
        skills: dict[str, SkillSpec] = {}
        for source, root in (
            ("builtin", self._builtin_dir),
            ("user", self._user_dir),
            ("project", self._project_dir),
        ):
            for skill in self._discover_root(root, source):
                if skill.name in skills:
                    logger.info(
                        "Skill {name} from {source} overrides {old_source}",
                        name=skill.name,
                        source=source,
                        old_source=skills[skill.name].source,
                    )
                skills[skill.name] = skill
        self._skills = skills
        self._discovered = True
        return self.list_all()

    def enable(self, skill_name: str) -> None:
        """Enable a discovered skill and persist the setting."""
        self._ensure_discovered()
        if skill_name not in self._skills:
            raise SkillNotFoundError(f"Skill not found: {skill_name}")
        if skill_name not in self._config.enabled_skills:
            self._config.enabled_skills.append(skill_name)
            self._save()

    def disable(self, skill_name: str) -> None:
        """Disable a skill and persist the setting."""
        if skill_name in self._config.enabled_skills:
            self._config.enabled_skills = [name for name in self._config.enabled_skills if name != skill_name]
            self._save()

    def list_all(self) -> list[SkillSpec]:
        """Return all discovered skills."""
        return [self._skills[name] for name in sorted(self._skills)]

    def list_enabled(self) -> list[SkillSpec]:
        """Return enabled skills that are currently discoverable."""
        self._ensure_discovered()
        return [self._skills[name] for name in self._config.enabled_skills if name in self._skills]

    def get(self, skill_name: str) -> SkillSpec:
        """Get a discovered skill by name."""
        self._ensure_discovered()
        try:
            return self._skills[skill_name]
        except KeyError as e:
            raise SkillNotFoundError(f"Skill not found: {skill_name}") from e

    def install_from_git(self, git_url: str) -> None:
        """Install a skill from a Git repository.

        Phase 5 placeholder.
        """
        raise NotImplementedError(f"Installing skills from git is not implemented yet: {git_url}")

    def _discover_root(self, root: Path, source: str) -> list[SkillSpec]:
        if not root.exists():
            return []
        if not root.is_dir():
            logger.warning("Skipping skills root because it is not a directory: {root}", root=root)
            return []

        skills: list[SkillSpec] = []
        for skill_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            skill_file = skill_dir / SKILL_FILE_NAME
            if not skill_file.exists():
                continue
            try:
                skills.append(SkillSpec.from_file(skill_file, source=source))
            except (OSError, SkillParseError) as e:
                logger.warning("Skipping invalid skill {skill_file}: {error}", skill_file=skill_file, error=e)
        return skills

    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self.discover_all()

    def _save(self) -> None:
        save_config(self._config, self._config_file)
