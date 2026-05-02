# Skills 支持功能实施计划

> 项目: rdsai-cli (aliyun/rdsai-cli)
> 语言: Python 3.13
> 框架: LangGraph + Typer
> 版本: 草案 v1.0

---

## 1. 需求分析

### 1.1 什么是 Skills

Skills 是可复用的高层次能力包，与 MCP tools（单个工具函数）和 subagent（独立代理）不同，Skills 是 **工作流描述**，包含：

| 组成部分 | 文件 | 说明 |
|---------|------|------|
| 元数据 + 指令 | `SKILL.md` | YAML frontmatter + Markdown 正文 |
| 参考文档 | `references/` | 补充知识材料，按需检索 |
| 模板文件 | `templates/` | 可复用的 SQL/配置模板 |
| 脚本文件 | `scripts/` | Python/Shell 脚本 |
| 静态资源 | `assets/` | 图片、数据文件等 |

### 1.2 与现有能力的关系

```
MCP Tools     → 单个函数级工具，动态加载，侧重外部服务集成
Subagent      → 完整代理，独立 agent loop，侧重复杂任务委派
Skills        → 工作流指令集，注入 system prompt，侧重高层任务模式
```

Skills 的核心价值：
- **声明式**：以 Markdown 描述"做什么"而非"怎么做"
- **可组合**：多个 Skills 可以同时激活
- **轻量级**：不启动额外代理循环，直接增强主 agent 能力

### 1.3 核心用例

1. **内置 Skills**：随项目分发（如 `mysql-performance-diagnosis`、`schema-migration-review`）
2. **用户 Skills**：放在 `~/.rdsai-cli/skills/` 目录
3. **项目 Skills**：放在工作目录下的 `.rdsai-skills/` 目录
4. **Skill 发现**：agent 的 system prompt 中列出已激活的 Skills 摘要

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    ShellREPL (repl.py)                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │              /skills 元命令                        │  │
│  │   list | enable | disable | view | install        │  │
│  └───────────────────────┬───────────────────────────┘  │
└──────────────────────────┼──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  SkillsManager                           │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────────────┐ │
│  │ Discovery   │ │ Registry     │ │ Lifecycle         │ │
│  │ (3 sources) │ │ (enable/     │ │ (install/uninstall│ │
│  │             │ │  disable)    │ │  from git/tarball)│ │
│  └──────┬──────┘ └──────┬───────┘ └────────┬──────────┘ │
└─────────┼───────────────┼──────────────────┼────────────┘
          │               │                  │
┌─────────▼───────────────▼──────────────────┼────────────┐
│              Skill Catalog                 │            │
│                                              │
│  ┌──────────────┐  ┌──────────────┐          │
│  │ Builtin      │  │ User         │          │
│  │ skills/      │  │ ~/.rdsai-    │          │
│  │ (project)    │  │ cli/skills/  │          │
│  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                   │
│  ┌──────▼─────────────────▼───────┐           │
│  │  SkillSpec (SKILL.md parser)   │           │
│  │  - frontmatter: name, desc,    │           │
│  │    category, version           │           │
│  │  - body: instructions (markdown)│          │
│  │  - references/, templates/,    │           │
│  │    scripts/, assets/           │           │
│  └────────────────────────────────┘           │
└──────────────────────┬────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    Agent 集成                            │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │  system_prompt 注入                         │         │
│  │  ┌──────────────────────────────────────┐  │         │
│  │  │ # Available Skills                   │  │         │
│  │  │ ## mysql-performance-diagnosis       │  │         │
│  │  │ > Diagnose MySQL performance issues  │  │         │
│  │  │ ## schema-migration-review           │  │         │
│  │  │ > Review schema migration scripts    │  │         │
│  │  └──────────────────────────────────────┘  │         │
│  └────────────────────────────────────────────┘         │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │  context.py 新增 ContextType.SKILLS        │         │
│  │  → 按需注入 Skill instructions 到消息       │         │
│  └────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────┘
```

### 2.2 模块职责划分

| 模块 | 路径 | 职责 |
|------|------|------|
| **SkillSpec** | `skills/spec.py` | SKILL.md 解析，YAML frontmatter + body 分离 |
| **SkillsManager** | `skills/manager.py` | 发现、注册、启用/禁用、安装 |
| **SkillRegistry** | `skills/registry.py` | 内存中已启用 Skill 的注册表 |
| **集成到 Agent** | `loop/agent.py`（修改） | 将已启用 Skills 注入 system prompt |
| **集成到 Context** | `loop/context.py`（修改） | 可选：按需注入详细 Skill 指令 |
| **/skills 命令** | `ui/metacmd/skills.py` | REPL 交互命令 |
| **补全器** | `ui/completers.py`（修改） | Skill 名称 tab 补全 |

### 2.3 数据流

```
启动阶段:
  Application.create()
    └→ SkillsManager.discover_all()        # 扫描三个来源
    └→ SkillsManager.load_enabled()        # 从 config.json 读取已启用列表
    └→ Agent system prompt 注入 Skills 摘要

运行阶段:
  用户输入 → NeoLoop.run()
    └→ ContextManager.build()
         └→ 已启用 Skills 的详细指令注入消息（可选，按需）

交互阶段:
  用户输入 /skills list    → SkillsManager.list_all() → 表格输出
  用户输入 /skills enable  → SkillsManager.enable()  → 更新 system prompt
  用户输入 /skills install → SkillsManager.install() → 下载并注册
```

---

## 3. 文件结构设计

### 3.1 新增文件

```
rdsai-cli/
├── skills/                          # 新增模块
│   ├── __init__.py
│   ├── spec.py                      # SkillSpec 类，SKILL.md 解析
│   ├── manager.py                   # SkillsManager 类，发现/注册/生命周期
│   └── errors.py                    # SkillError, SkillNotFoundError 等
│
├── skills/builtin/                  # 内置 Skills 目录
│   └── (未来添加，初始为空)
│
├── ui/metacmd/skills.py             # /skills REPL 元命令
│
└── tests/skills/                    # 测试目录
    ├── __init__.py
    ├── test_spec.py                 # SKILL.md 解析测试
    ├── test_manager.py              # 发现/注册/生命周期测试
    └── fixtures/                    # 测试用 Skill 样本
        └── sample_skill/
            ├── SKILL.md
            ├── references/
            ├── templates/
            └── scripts/
```

### 3.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `loop/agent.py` | `load_agent()` 中注入已启用 Skills 摘要到 system prompt |
| `loop/runtime.py` | `Runtime` 增加 `skills_manager` 字段 |
| `loop/context.py` | 可选：增加 `ContextType.SKILLS` 和按需注入逻辑 |
| `app.py` | `Application.create()` 初始化 SkillsManager，传入 Runtime |
| `ui/metacmd/__init__.py` | import skills 模块触发注册 |
| `ui/completers.py` | 增加 `/skills enable/disable` 的 skill name 补全 |
| `config/app.py` | `Config` 增加 `enabled_skills: list[str]` 字段 |
| `config/base.py` | 增加 `get_skills_dir()` 工具函数 |

### 3.3 用户数据目录

```
~/.rdsai-cli/
├── config.json              # 增加 enabled_skills 字段
├── skills/                  # 用户安装的 Skills
│   ├── mysql-performance-diagnosis/
│   │   └── SKILL.md
│   └── schema-migration-review/
│       ├── SKILL.md
│       └── templates/
│           └── migration_review.sql
└── ...
```

### 3.4 项目级 Skills 目录（可选）

```
项目目录/
└── .rdsai-skills/           # 项目级 Skills（按优先级高于用户 Skills）
    └── custom-workflow/
        └── SKILL.md
```

---

## 4. 分步骤实施计划

### Phase 1: 基础设施（Skills 解析与发现）

**目标**：实现 SKILL.md 解析和多源发现能力

#### Step 1.1: 定义 SkillSpec 数据结构

**文件**: `skills/spec.py`

**任务**:
- 定义 `SkillSpec` dataclass，包含：
  - `id: str` — Skill 唯一标识（目录名或 frontmatter 中的 name）
  - `name: str` — 人类可读名称
  - `description: str` — 简短描述
  - `category: str` — 分类（diagnosis / optimization / migration / etc.）
  - `version: str` — 版本号
  - `source: str` — 来源（builtin / user / project）
  - `path: Path` — Skill 根目录
  - `instructions: str` — SKILL.md body（Markdown 指令正文）
  - `references: list[Path]` — 参考文件路径列表
  - `templates: list[Path]` — 模板文件路径列表
  - `scripts: list[Path]` — 脚本文件路径列表
  - `assets: list[Path]` — 静态资源路径列表
  - `enabled: bool` — 是否启用

**要点**:
- 使用 `pyyaml` 解析 YAML frontmatter（`--- ... ---` 之间的内容）
- SKILL.md 格式类似 Jekyll frontmatter：
  ```markdown
  ---
  name: mysql-performance-diagnosis
  description: Diagnose and resolve MySQL performance issues
  category: diagnosis
  version: 1.0.0
  ---

  # MySQL Performance Diagnosis

  When the user asks about slow queries or performance issues:

  1. First check the slow query log...
  2. Then analyze execution plans...
  ...
  ```
- 支持最小化 frontmatter（只要求 `name` 和 `description`）

#### Step 1.2: 定义错误类型

**文件**: `skills/errors.py`

**任务**:
- `SkillError(Exception)` — 基类
- `SkillNotFoundError(SkillError)` — Skill 未找到
- `SkillParseError(SkillError)` — SKILL.md 解析失败
- `SkillInstallError(SkillError)` — 安装失败

#### Step 1.3: 实现发现机制

**文件**: `skills/manager.py`

**任务**:
- 实现三个发现源：
  1. **Builtin**: `skills/builtin/` 目录下每个子目录（包内资源）
  2. **User**: `~/.rdsai-cli/skills/` 目录下每个子目录
  3. **Project**: 当前工作目录下 `.rdsai-skills/` 子目录
- 每个子目录必须包含 `SKILL.md`，否则跳过并记录 warning
- 同名 Skill 按优先级覆盖：Project > User > Builtin

**要点**:
- 发现时只加载 frontmatter 元数据（name, description, category, version）
- 指令正文（body）延迟加载，仅在启用时读取
- 使用 `pathlib` 进行目录遍历

#### Step 1.4: 编写单元测试

**文件**: `tests/skills/test_spec.py`, `tests/skills/test_manager.py`

**任务**:
- 测试正常 SKILL.md 解析
- 测试缺少 frontmatter 的报错
- 测试缺少 name/description 的报错
- 测试多源发现和优先级覆盖
- 测试不存在目录的优雅处理

---

### Phase 2: 注册与生命周期管理

**目标**：实现 Skill 的启用/禁用/安装/卸载

#### Step 2.1: 实现 SkillsManager 核心

**文件**: `skills/manager.py`

**任务**:
- `SkillsManager` 类包含：
  - `discover_all()` — 扫描所有来源，构建目录
  - `list_all()` — 返回所有发现的 Skills
  - `list_enabled()` — 返回已启用的 Skills
  - `enable(skill_id: str)` — 启用指定 Skill
  - `disable(skill_id: str)` — 禁用指定 Skill
  - `get(spec_id: str) -> SkillSpec | None` — 获取单个 Skill
  - `save_state()` — 持久化已启用列表到 config.json
  - `load_state()` — 从 config.json 加载已启用列表

**要点**:
- 启用/禁用操作修改内存状态，同时标记需要持久化
- `save_state()` 由调用方（Application 或命令）在适当时机触发
- 已启用 Skills 的 `instructions` 字段在启用时懒加载

#### Step 2.2: 集成到 Config

**文件**: `config/app.py`

**任务**:
- `Config` 类增加 `enabled_skills: list[str] = Field(default_factory=list)`
- 序列化时自动保存，反序列化时自动加载

**要点**:
- `enabled_skills` 存储 Skill ID 列表
- 默认值为空列表

#### Step 2.3: 集成到 Runtime

**文件**: `loop/runtime.py`

**任务**:
- `Runtime` 增加 `skills_manager: SkillsManager | None = field(default=None)`
- `Application.create()` 中创建 SkillsManager 并传入 Runtime

#### Step 2.4: 安装/卸载（Phase 2 可选）

**文件**: `skills/manager.py`

**任务**:
- `install(source: str)` — 从 git URL 或本地路径安装
  - git: clone 到 `~/.rdsai-cli/skills/<name>/`
  - 本地: 复制目录到 `~/.rdsai-cli/skills/<name>/`
- `uninstall(skill_id: str)` — 删除用户 Skills 目录
  - 不允许卸载 builtin skills

**要点**:
- 安装时验证 `SKILL.md` 存在且格式正确
- 安装后自动启用
- 卸载前确认已禁用或提示风险

---

### Phase 3: Agent 集成（System Prompt 注入）

**目标**：将已启用 Skills 的指令注入到 agent 的 system prompt

#### Step 3.1: 修改 Agent 加载流程

**文件**: `loop/agent.py`

**任务**:
- `load_agent()` 增加可选参数 `skills_manager: SkillsManager | None = None`
- 在 `_load_system_prompt()` 之后，追加已启用 Skills 摘要段：
  ```markdown
  ---

  # Available Skills

  You have the following skills enabled. Use them when appropriate:

  ## mysql-performance-diagnosis
  Diagnose and resolve MySQL performance issues.

  ## schema-migration-review
  Review and validate schema migration scripts.
  ```
- 如果 `skills_manager` 为 None 或无已启用 Skills，不追加任何内容

**要点**:
- 只注入摘要（name + description），不注入完整指令正文
- 完整指令通过 Context 层按需注入（Step 3.2）
- 或者另一种策略：直接注入完整指令正文（更简单但消耗 token）

**推荐策略**：
- 对于指令较短的 Skills（< 500 tokens）→ 直接注入完整指令到 system prompt
- 对于指令较长的 Skills → 注入摘要，通过 Context 层按需注入
- 初始实现采用直接注入完整指令的策略，简单可靠；后续可优化

#### Step 3.2: 修改 Application 创建流程

**文件**: `app.py`

**任务**:
- 在 `Application.create()` 中：
  1. 创建 `SkillsManager` 实例
  2. 调用 `skills_manager.discover_all()`
  3. 调用 `skills_manager.load_state(config.enabled_skills)`
  4. 将 `skills_manager` 传入 `Runtime.create()`
  5. 将 `skills_manager` 传入 `load_agent()`

#### Step 3.3: Runtime 变更处理

**文件**: `loop/runtime.py`

**任务**:
- Runtime 保存 `skills_manager` 引用
- 当 `/skills enable/disable` 命令执行后，通知 agent 更新 system prompt

**更新 system prompt 的策略**：
- 方案 A：重新加载 agent（通过 `Reload` 异常触发 session 重启）
- 方案 B：动态更新 `agent.system_prompt` 属性（推荐，无需重启）
  - 在 NeoLoop 中增加 `refresh_system_prompt()` 方法
  - 从 skills_manager 获取最新已启用 Skills，重新生成 system prompt

---

### Phase 4: REPL 交互（/skills 命令）

**目标**：提供 REPL 元命令来管理 Skills

#### Step 4.1: 实现 /skills 元命令

**文件**: `ui/metacmd/skills.py`

**任务**:
- 使用 `@meta_command` 装饰器注册
- 支持子命令：
  - `/skills list` — 列出所有 Skills（发现 + 启用状态）
  - `/skills list --enabled` — 仅列出已启用的
  - `/skills enable <skill_id>` — 启用 Skill
  - `/skills disable <skill_id>` — 禁用 Skill
  - `/skills view <skill_id>` — 查看 Skill 详情（元数据 + 指令摘要）
  - `/skills install <source>` — 安装新 Skill
  - `/skills uninstall <skill_id>` — 卸载 Skill

**输出示例** (`/skills list`):

```
#   Name                          Category     Status     Source
─── ───────────────────────────── ──────────── ────────── ──────
1   mysql-performance-diagnosis   diagnosis    ● Enabled  builtin
2   schema-migration-review       migration    ○ Disabled builtin
3   custom-workflow               custom       ● Enabled  user
```

**要点**:
- 启用/禁用操作立即生效，调用 `refresh_system_prompt()` 更新 agent
- 启用/禁用操作保存到 config.json
- 使用 Rich Table 格式化输出

#### Step 4.2: 注册模块

**文件**: `ui/metacmd/__init__.py`

**任务**:
- 添加 `from ui.metacmd import skills  # noqa: F401`

#### Step 4.3: 补全支持

**文件**: `ui/completers.py`

**任务**:
- 为 `/skills enable` 添加 skill name 补全（列出所有已发现但未启用的 Skills）
- 为 `/skills disable` 添加 skill name 补全（列出所有已启用的 Skills）
- 为 `/skills view` 添加 skill name 补全（列出所有已发现的 Skills）
- 为 `/skills uninstall` 添加 skill name 补全（仅用户安装的 Skills）

**要点**:
- 补全器通过 `ShellREPL.loop.runtime.skills_manager` 访问 SkillsManager
- 使用 `arg_completer` 回调模式（与 /mcp 命令一致）

---

### Phase 5: 高级功能（可选，后续迭代）

#### Step 5.1: Context 层按需注入

**文件**: `loop/context.py`

**任务**:
- 新增 `ContextType.SKILLS`
- 在 `ContextManager` 中增加 `set_skills_context()` 方法
- 当 agent 首次提及某个 Skill 时，注入该 Skill 的完整指令到消息上下文
- 使用内容哈希去重，避免重复注入

**要点**:
- 这是对 Step 3.1 直接注入策略的优化
- 初始可不做，等 token 消耗问题显现后再引入

#### Step 5.2: Skill 触发词匹配

**文件**: `skills/manager.py`

**任务**:
- 在 `SkillSpec` frontmatter 中支持 `triggers: list[str]` 字段
- 当用户输入包含触发词时，自动激活对应 Skill 的详细指令注入

#### Step 5.3: Skill 模板引用

**文件**: `skills/spec.py`, `skills/manager.py`

**任务**:
- 实现 `get_template(name: str) -> str` 方法
- Agent 可以通过工具调用获取 Skill 中的模板内容
- 未来可添加 `skill_template` 工具

#### Step 5.4: Skill 脚本执行

**文件**: `skills/manager.py`

**任务**:
- 实现 `run_script(name: str, args: list[str]) -> str` 方法
- 安全地执行 Skill 中的脚本（沙箱隔离）
- 未来可添加 `skill_run_script` 工具

#### Step 5.5: Skill 市场/仓库

**任务**:
- 实现 `/skills search <query>` — 搜索远程 Skill 仓库
- 实现 Skill 的 version 检查与更新
- 可选：对接 GitHub Releases 或专用 registry

---

## 5. 测试策略

### 5.1 测试分层

```
┌─────────────────────────────────────────┐
│  Integration Tests (tests/skills/)      │
│  - /skills 命令端到端测试                │
│  - Agent system prompt 集成测试          │
│  - SkillsManager + Config 集成测试       │
├─────────────────────────────────────────┤
│  Unit Tests (tests/skills/)             │
│  - SkillSpec 解析测试                   │
│  - SkillsManager 发现/注册测试           │
│  - SkillsManager 生命周期测试            │
├─────────────────────────────────────────┤
│  Fixture Tests (tests/skills/fixtures/) │
│  - 样本 SKILL.md 文件                   │
│  - 完整 Skill 目录结构                   │
│  - 边界情况（空文件、无效 YAML 等）       │
└─────────────────────────────────────────┘
```

### 5.2 单元测试清单

| 测试文件 | 测试用例 |
|---------|---------|
| `test_spec.py` | `test_parse_valid_skill()` — 解析完整 SKILL.md |
| `test_spec.py` | `test_parse_minimal_skill()` — 仅 name + description |
| `test_spec.py` | `test_parse_missing_name()` — 缺少 name 报错 |
| `test_spec.py` | `test_parse_invalid_yaml()` — 无效 YAML 报错 |
| `test_spec.py` | `test_parse_no_frontmatter()` — 无 frontmatter 报错 |
| `test_spec.py` | `test_list_references()` — references/ 目录扫描 |
| `test_spec.py` | `test_list_templates()` — templates/ 目录扫描 |
| `test_spec.py` | `test_list_scripts()` — scripts/ 目录扫描 |
| `test_manager.py` | `test_discover_builtin()` — builtin 源发现 |
| `test_manager.py` | `test_discover_user()` — user 源发现 |
| `test_manager.py` | `test_discover_project()` — project 源发现 |
| `test_manager.py` | `test_priority_override()` — 同名 Skill 优先级 |
| `test_manager.py` | `test_enable_disable()` — 启用/禁用操作 |
| `test_manager.py` | `test_save_load_state()` — 状态持久化 |
| `test_manager.py` | `test_enable_nonexistent()` — 启用不存在的 Skill |
| `test_manager.py` | `test_list_enabled()` — 已启用列表过滤 |

### 5.3 集成测试清单

| 测试文件 | 测试用例 |
|---------|---------|
| `test_integration.py` | `test_skills_in_system_prompt()` — Skills 正确注入 system prompt |
| `test_integration.py` | `test_skills_enable_updates_prompt()` — 启用后 prompt 更新 |
| `test_integration.py` | `test_config_persistence()` — enabled_skills 持久化到 config.json |

### 5.4 测试 Fixture 结构

```
tests/skills/fixtures/
├── valid_skill/
│   ├── SKILL.md                  # 完整 frontmatter + body
│   ├── references/
│   │   └── guide.md
│   ├── templates/
│   │   └── query.sql
│   └── scripts/
│       └── analyze.py
├── minimal_skill/
│   └── SKILL.md                  # 仅 name + description
├── invalid_yaml/
│   └── SKILL.md                  # frontmatter 包含无效 YAML
├── no_frontmatter/
│   └── SKILL.md                  # 纯 Markdown，无 frontmatter
└── missing_name/
    └── SKILL.md                  # 有 frontmatter 但缺少 name
```

---

## 6. 风险评估与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| System prompt 过长导致 token 消耗 | 高 | 限制每个 Skill 指令长度；支持按需注入（Phase 5） |
| Skill 目录结构不规范 | 低 | 严格验证 SKILL.md 格式；跳过无效目录并记录 warning |
| 多源同名冲突 | 中 | 明确的优先级规则（Project > User > Builtin） |
| 启用/禁用后 agent 状态不一致 | 中 | 使用 `refresh_system_prompt()` 同步更新 |
| Skill 安装安全风险 | 中 | 初始不支持远程安装；仅支持本地路径和可信 git 源；后续添加沙箱 |

---

## 7. 时间估算

| Phase | 任务 | 估算时间 |
|-------|------|---------|
| Phase 1 | SkillSpec 解析 + 发现机制 | 2-3 天 |
| Phase 2 | 注册管理 + Config 集成 | 2-3 天 |
| Phase 3 | Agent system prompt 集成 | 1-2 天 |
| Phase 4 | REPL /skills 命令 + 补全 | 2-3 天 |
| Phase 5 | 高级功能（可选） | 3-5 天 |
| **总计** | **基础功能（Phase 1-4）** | **7-11 天** |

---

## 8. 验收标准

1. [ ] SKILL.md 格式正确解析，包含 frontmatter 元数据和 body 指令
2. [ ] 三个发现源（builtin / user / project）正常工作
3. [ ] `/skills list` 显示所有 Skills 及启用状态
4. [ ] `/skills enable/disable` 正确切换状态并更新 agent
5. [ ] 已启用 Skills 的指令出现在 agent system prompt 中
6. [ ] 启用/禁用状态持久化到 config.json，重启后恢复
7. [ ] tab 补全对 `/skills enable/disable/view` 的 skill name 生效
8. [ ] 所有单元测试通过
9. [ ] 集成测试通过
10. [ ] 代码通过 `./dev/code-style.sh --check` 和 `./dev/pytest.sh`

---

## 9. SKILL.md 格式规范（参考）

### 9.1 完整示例

```markdown
---
name: mysql-performance-diagnosis
description: Diagnose and resolve MySQL performance issues through systematic analysis
category: diagnosis
version: 1.0.0
triggers:
  - slow query
  - performance
  - latency
---

# MySQL Performance Diagnosis

## Overview

When the user reports slow queries or performance degradation, follow this workflow:

## Step 1: Identify the Problem

1. Check if the user has provided a specific slow query
2. If not, ask the user to describe the symptoms
3. Use `MySQLSelect` to check the slow query log:
   ```sql
   SELECT * FROM mysql.slow_log ORDER BY start_time DESC LIMIT 10;
   ```

## Step 2: Analyze Execution Plan

For each identified slow query:

1. Run `MySQLExplain` to get the execution plan
2. Look for full table scans (type=ALL), missing indexes
3. Check `rows` column for estimated row examination count

## Step 3: Check System Status

Run these concurrently:
- `MySQLShow` with "SHOW ENGINE INNODB STATUS"
- `MySQLShow` with "SHOW PROCESSLIST"
- `MySQLSelect` for performance_schema queries

## Step 4: Provide Recommendations

Structure findings using:
- **Root cause**: Primary issue identified
- **Impact**: Affected queries/tables
- **Recommendation**: Specific actions with expected improvement
```

### 9.2 Frontmatter 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Skill 唯一标识，小写字母+连字符 |
| `description` | string | ✅ | 一句话描述（< 100 字符） |
| `category` | string | ❌ | 分类标签 |
| `version` | string | ❌ | 语义化版本号 |
| `triggers` | list[string] | ❌ | 触发关键词列表 |
| `author` | string | ❌ | 作者信息 |
| `tags` | list[string] | ❌ | 搜索标签 |

### 9.3 目录结构要求

```
<skill-id>/
├── SKILL.md              # 必需：元数据 + 指令
├── references/           # 可选：参考文档（.md, .txt）
├── templates/            # 可选：模板文件（.sql, .yaml, etc.）
├── scripts/              # 可选：脚本文件（.py, .sh）
└── assets/               # 可选：静态资源
```

---

## 10. 后续演进路线

```
Phase 1-4 (基础)    Phase 5 (高级)         Future (远景)
    │                   │                     │
    ├── 解析             ├── 按需注入            ├── Skill 市场
    ├── 发现             ├── 触发词匹配          ├── Skill 脚本工具
    ├── 注册             ├── 模板引用            ├── Skill 组合/流水线
    ├── System Prompt    ├── 脚本执行            ├── Skill 评测基准
    └── REPL 命令        └── 版本管理            └── Skill 共享平台
```
