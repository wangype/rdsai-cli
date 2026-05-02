"""Exceptions for the skills subsystem."""


class SkillError(Exception):
    """Base exception for skill-related failures."""


class SkillNotFoundError(SkillError):
    """Raised when a skill cannot be found."""


class SkillAlreadyExistsError(SkillError):
    """Raised when installing a skill that already exists."""


class SkillParseError(SkillError):
    """Raised when a SKILL.md file cannot be parsed."""
