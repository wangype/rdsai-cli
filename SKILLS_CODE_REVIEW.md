# Skills Support Code Review Report

**Commit:** 5f4a363 (feature/skills-support)  
**Reviewer:** AI Testing Engineer  
**Date:** 2026-05-02

---

## Summary

Reviewed 7 new files and 5 modified files. Overall the code is well-structured with good use of dataclasses, type hints, and loguru logging. However, several bugs and gaps were identified.

**Issue counts:**
- 🔴 Critical: 1
- 🟡 Important: 4
- 🔵 Minor: 8
- 🟢 Tests missing: 12 test cases

---

## 🔴 Critical Issues

### C1: `_ensure_discovered` re-scans on every call when no skills found

**File:** `skills/manager.py`, lines 115-117

```python
def _ensure_discovered(self) -> None:
    if not self._skills:  # BUG: {} is falsy
        self.discover_all()
```

When `discover_all()` finds zero skills, `self._skills = {}`. Since `{}` is falsy, `not self._skills` is `True`, so the next call to `_ensure_discovered()` re-scans all directories. Verified: 3 roots × 2 calls = 6 scans instead of 3.

**Impact:** Repeated unnecessary filesystem I/O on every call to `get()`, `list_enabled()`, `enable()`.

**Fix:** Use a boolean flag instead:
```python
def __init__(...):
    ...
    self._discovered = False

def _ensure_discovered(self) -> None:
    if not self._discovered:
        self.discover_all()
        self._discovered = True
```

---

## 🟡 Important Issues

### I1: `disable()` doesn't require discovery, `enable()` does — asymmetric behavior

**File:** `skills/manager.py`, lines 58-71

`enable()` calls `_ensure_discovered()` and raises `SkillNotFoundError` if the skill doesn't exist. `disable()` does NOT call `_ensure_discovered()` and silently does nothing if the skill wasn't discovered. This asymmetry could be confusing:

```python
manager.disable("never-existed")  # silently succeeds, no error
manager.enable("never-existed")   # raises SkillNotFoundError
```

**Recommendation:** Either make `disable()` also require discovery (raise if not found), or document the asymmetry. At minimum, add a test covering this behavior.

### I2: `SkillAlreadyExistsError` is defined but never raised

**File:** `skills/errors.py` line 12, `skills/__init__.py` line 4

The error class is exported in `__all__` but no code path raises it. `enable()` silently does nothing if the skill is already enabled. Either:
- Remove the unused error class, or
- Use it in `enable()` to raise when skill is already enabled.

### I3: No validation on `enabled_skills` config entries

**File:** `config/app.py` line 44

```python
enabled_skills: list[str] = Field(default_factory=list, description="Enabled skills")
```

If a user manually edits `config.json` to add non-string entries (e.g., `[123, null]`), Pydantic would reject this. But if entries are valid strings referencing non-existent skills, `list_enabled()` silently skips them (line 80). This could lead to confusion where enabled skills don't appear. Consider logging a warning for stale entries.

### I4: `install_from_git` has no test for `NotImplementedError`

**File:** `skills/manager.py` line 90-95

The method is a Phase 5 placeholder that raises `NotImplementedError`, but there is no test asserting this behavior. A test should exist to prevent accidental regression (e.g., someone accidentally removing the raise).

---

## 🔵 Minor Issues

### M1: `metadata` field in `SkillSpec` duplicates parsed fields

**File:** `skills/spec.py` line 30, line 92

```python
metadata: dict[str, Any] = field(default_factory=dict)
# ...
metadata=dict(metadata),  # includes name, description, version, etc.
```

The `metadata` dict stores ALL frontmatter fields including `name`, `description`, `version`, `tags`, etc. — duplicating the individual attributes. Users might expect `metadata` to contain only custom/extra fields. Consider filtering out known fields before storing.

### M2: `to_dict()` omits `body` and `metadata`

**File:** `skills/spec.py` lines 96-108

Serialization loses `body` (the skill content) and `metadata`. If `to_dict()` is intended for full round-trip serialization, these should be included. If it's for display/config purposes only, this should be documented.

### M3: `save_config` missing return type annotation

**File:** `config/app.py` line 126

```python
def save_config(config: Config, config_file: Path | None = None):  # missing -> None
```

Project guideline requires type hints for all function signatures (`mypy` has `disallow_untyped_defs = true`). This is a pre-existing issue but relevant since skills code calls this function.

### M4: `_discover_root` silently swallows all `OSError`

**File:** `skills/manager.py` line 111

```python
except (OSError, SkillParseError) as e:
    logger.warning("Skipping invalid skill {skill_file}: {error}", ...)
```

`OSError` includes `PermissionError`, `IsADirectoryError`, etc. A permission error on a skill file would be silently skipped with only a warning log. Consider logging at `ERROR` level for permission-related issues so they're more visible.

### M5: `_split_frontmatter` edge case with `\r\n` line endings

**File:** `skills/spec.py` line 116

```python
if not text.startswith("---\n"):
```

Python's `read_text()` uses universal newlines by default, converting `\r\n` to `\n`. This is correct. But if someone reads the file differently (e.g., binary mode), this would break. Not a real bug, but worth a defensive comment.

### M6: No duplicate detection in tags/dependencies

**File:** `skills/spec.py` lines 156-161

```python
def _string_list(value: Any, key: str, path: Path) -> list[str]:
    ...
    return [item.strip() for item in value if item.strip()]
```

If a SKILL.md has `tags: [foo, foo, bar]`, the result is `["foo", "foo", "bar"]`. Consider `dict.fromkeys()` or `set` to deduplicate while preserving order.

### M7: Prompt injection risk via skill names/descriptions

**File:** `loop/agent.py` lines 105-114

```python
skills_prompt = "\n".join(["# Available Skills", *[f"- {skill.summary()}" for skill in skills]])
return f"{system_prompt}\n\n{skills_prompt}"
```

Malicious skill content (e.g., `name: "x\n\nIgnore all previous instructions"`) could alter the agent's behavior. Consider sanitizing or escaping skill names/descriptions before injection.

### M8: `load_agent` has redundant `skills_manager` parameter

**File:** `loop/agent.py` line 41

```python
async def load_agent(agent_file, runtime, skills_manager: SkillsManager | None = None):
```

The caller in `app.py` never passes this parameter — it always uses `runtime.skills_manager`. The parameter adds unnecessary API surface. Consider removing it.

---

## 📋 Test Coverage Gaps

The current 10 tests cover basic happy paths but miss the following scenarios:

### Missing `test_spec.py` tests:
1. **Empty frontmatter body** — SKILL.md with `---\nname: x\ndescription: y\n---\n` (no body after closing `---`)
2. **Invalid YAML** — frontmatter that parses to a non-dict value (e.g., `---\n- item1\n- item2\n---\nBody`)
3. **Whitespace-only name/description** — should raise `SkillParseError`
4. **Dependencies as non-list** — `dependencies: "not-a-list"`
5. **Missing optional fields** — no `version`, `category`, `tags`, `dependencies`
6. **Resource dirs detection** — SKILL.md with/without `references/`, `templates/`, etc. subdirectories
7. **`from_file` with non-existent path** — raises `SkillParseError` with correct message
8. **`from_file` with directory path** — raises `SkillParseError`

### Missing `test_manager.py` tests:
9. **`list_enabled` with stale enabled skill** — skill enabled in config but no longer discoverable
10. **`get()` method** — happy path and missing skill
11. **`install_from_git` raises `NotImplementedError`**
12. **Multiple skills in same root directory**
13. **`discover_all` when all roots are missing** (empty result)
14. **`_ensure_discovered` doesn't re-scan after discovery** (regression test for C1)
15. **`disable()` on non-existent skill** (asymmetric behavior test for I1)

---

## Files Modified (Annotations)

All issues are annotated inline below:

### `skills/manager.py`

**Line 32:** ✅ FIXED — Added `self._discovered: bool = False` to track discovery state.  
**Line 57:** ✅ FIXED — Set `self._discovered = True` at end of `discover_all()`.  
**Line 118:** ✅ FIXED — Changed `_ensure_discovered` check from `not self._skills` to `not self._discovered`.

---

## Verification

- All 22 existing tests pass (10 skills + 12 runtime)
- Code style checks pass (ruff + format)
- Bug C1 fix verified: no re-scans on repeated `_ensure_discovered` calls
