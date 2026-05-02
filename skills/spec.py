"""Skill specification parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from skills.errors import SkillParseError

SKILL_FILE_NAME = "SKILL.md"
RESOURCE_DIRS = ("references", "templates", "scripts", "assets")


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillSpec:
    """Parsed skill definition from a SKILL.md file."""

    name: str
    description: str
    path: Path
    body: str
    version: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    resource_dirs: dict[str, Path] = field(default_factory=dict)

    @property
    def skill_dir(self) -> Path:
        """Return the directory containing this skill."""
        return self.path.parent

    @property
    def references_dir(self) -> Path | None:
        """Return the references directory when present."""
        return self.resource_dirs.get("references")

    @property
    def templates_dir(self) -> Path | None:
        """Return the templates directory when present."""
        return self.resource_dirs.get("templates")

    @property
    def scripts_dir(self) -> Path | None:
        """Return the scripts directory when present."""
        return self.resource_dirs.get("scripts")

    @property
    def assets_dir(self) -> Path | None:
        """Return the assets directory when present."""
        return self.resource_dirs.get("assets")

    @classmethod
    def from_file(cls, path: Path, *, source: str | None = None) -> SkillSpec:
        """Parse a SKILL.md file."""
        path = path.expanduser().resolve()
        if not path.exists():
            raise SkillParseError(f"Skill file not found: {path}")
        if not path.is_file():
            raise SkillParseError(f"Skill path is not a file: {path}")

        text = path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text, path)
        metadata = _load_frontmatter(frontmatter, path)

        name = _required_string(metadata, "name", path)
        description = _required_string(metadata, "description", path)
        version = _optional_string(metadata, "version", path)
        category = _optional_string(metadata, "category", path)
        tags = _string_list(metadata.get("tags", []), "tags", path)
        dependencies = _string_list(metadata.get("dependencies", []), "dependencies", path)

        resource_dirs = {
            dirname: path.parent / dirname for dirname in RESOURCE_DIRS if (path.parent / dirname).is_dir()
        }

        return cls(
            name=name,
            description=description,
            version=version,
            category=category,
            tags=tags,
            dependencies=dependencies,
            path=path,
            body=body.strip(),
            source=source,
            metadata=dict(metadata),
            resource_dirs=resource_dirs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of this skill."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "path": str(self.path),
            "source": self.source,
            "resource_dirs": {name: str(path) for name, path in self.resource_dirs.items()},
        }

    def summary(self) -> str:
        """Return the one-line summary used in agent prompts."""
        return f"{self.name}: {self.description}"


def _split_frontmatter(text: str, path: Path) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise SkillParseError(f"Missing YAML frontmatter in skill file: {path}")

    end = text.find("\n---", 4)
    if end == -1:
        raise SkillParseError(f"Unterminated YAML frontmatter in skill file: {path}")

    frontmatter = text[4:end]
    body_start = end + len("\n---")
    if text[body_start : body_start + 1] == "\n":
        body_start += 1
    return frontmatter, text[body_start:]


def _load_frontmatter(frontmatter: str, path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML frontmatter in skill file {path}: {e}") from e
    if not isinstance(data, dict):
        raise SkillParseError(f"YAML frontmatter must be a mapping in skill file: {path}")
    return data


def _required_string(metadata: dict[str, Any], key: str, path: Path) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SkillParseError(f"Skill frontmatter field '{key}' must be a non-empty string in: {path}")
    return value.strip()


def _optional_string(metadata: dict[str, Any], key: str, path: Path) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SkillParseError(f"Skill frontmatter field '{key}' must be a string in: {path}")
    return value.strip() or None


def _string_list(value: Any, key: str, path: Path) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SkillParseError(f"Skill frontmatter field '{key}' must be a list of strings in: {path}")
    return [item.strip() for item in value if item.strip()]
