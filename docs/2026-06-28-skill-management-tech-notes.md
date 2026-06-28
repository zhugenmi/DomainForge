# Skill 管理与可插拔安装 — 技术说明

**日期**: 2026-06-28
**分支**: feat/skill-management
**特性**: 标准 SKILL.md 可插拔 skill 系统

## 1. 架构决策

- **Skill = 指令包，非 function-calling tool**：Skill 是给 agent 阅读的 markdown 指令包（`SKILL.md` 为核心），独立于 `ToolRegistry`。builtin tools（calculator、web_search 等）走 `ToolRegistry` 参与函数调用；skill 走 `SkillRegistry`，其正文注入 agent 系统提示。两者并存、互不污染。
- **A1 始终注入模型**：所有 `enabled=True` skill 的 `SKILL.md` 正文在每次 chat 请求时拼入系统提示。简单、确定，token 占用随 skill 数线性增长；首版接受，后续可演进到 A2 按需检索注入。
- **MarketplaceAdapter 抽象 + LocalMarketplaceAdapter 实现**：marketplace 接口抽象为 `search/info/download` 三方法 + `source_id` 属性。`LocalMarketplaceAdapter` 读本地 `skills/marketplace/` 目录作 mock 源；后续 `ClawhubAdapter` 实现同接口走 HTTP 即可接入真实平台，service 层零改动。
- **持久化 + 启动重建**：`installed_skills` 表存元数据 + `installed_path`；启动 lifespan 从 DB 查 `enabled=True` 行，`load_skill_from_dir` 重建 `SkillRegistry`。安装的 skill 重启后仍在，enabled 状态保留。

## 2. 实现细节

### 2.1 后端模块划分（`app/skills/`）

| 文件 | 职责 |
|---|---|
| `manifest.py` | `SkillManifest` dataclass + `parse_skill_md()`：用 `python-frontmatter` 解析 SKILL.md，校验 `name`（必填、匹配 `^[a-z0-9-]+$`）、`description`（必填），可选 `version`/`author`/`license`。解析失败抛 `SkillManifestError(ValueError)`。 |
| `loader.py` | `SkillDescriptor`（manifest + path + files）+ `load_skill_from_dir()`：读目录下 SKILL.md，校验目录名 == manifest.name，`rglob` 收集相对文件列表。 |
| `registry.py` | `SkillRegistry`：`{name: SkillDescriptor}` 内存 dict，`add/remove/get/list_all`。模块单例 `skill_registry`。enabled 语义由"启动只加载 enabled 行 + set_enabled 增删"保证，`list_all()` 返回即当前 enabled 集合。 |
| `injection.py` | `build_skill_context_block(registry) -> str`：组装 header + 每个 skill 一段 `## 技能：{name}\n{body_md}`。空 registry 返回空串。 |
| `service.py` | `SkillService`：install（download→load→copytree→DB upsert→registry.add）、uninstall（路径校验→registry.remove→rmtree→DB delete）、set_enabled（DB 更新→registry 增删）、list/get/search。DTO: `InstalledSkillDTO`、`InstalledSkillDetailDTO`。 |
| `marketplace/base.py` | `MarketplaceAdapter` ABC：`source_id` 属性 + async `search/info/download`。 |
| `marketplace/models.py` | `SkillPackageInfo` dataclass（8 字段，含 `body_preview` 前 300 字）。 |
| `marketplace/local_adapter.py` | `LocalMarketplaceAdapter`：扫 `skills/marketplace/*/SKILL.md`，`source_id="local"`，search 匹配 name/description 子串（大小写不敏感），空 query 返回全部，`download` 返回包目录 Path（不拷贝，由 service 拷贝）。 |

### 2.2 持久化

`installed_skills` 表（Alembic 迁移 `0008_installed_skills`）：

| 列 | 类型 | 说明 |
|---|---|---|
| `name` | String(100) PK | = frontmatter name = 目录名 |
| `version` | String(50) | |
| `source` | String(50) | marketplace source_id（"local"） |
| `manifest_json` | Text | 完整 manifest 快照（asdict 序列化） |
| `installed_path` | String(500) | `skills/installed/<name>` 绝对路径 |
| `enabled` | Boolean | 是否注入上下文 |
| `installed_at` | DateTime | server_default now |

`SkillRepo`（`app/database/repositories/skill_repo.py`）：`upsert/get/list_all/list_enabled/set_enabled/delete`，async，依赖 `AsyncSession`，caller commit。

启动加载（`app/main.py` lifespan `_load_installed_skills`）：`async with async_session_factory() as db: rows = SkillRepo(db).list_enabled()`，逐行 `load_skill_from_dir` + `skill_registry.add`，per-skill try/except 不阻塞启动。

### 2.3 注入点（A1）

`app/runtime/nodes/answer_node.py`：`AnswerNode.__init__` 加 `skill_registry: SkillRegistry | None = None` 参数。在系统提示组装完成（reasoning 块之后、messages 构建之前）插入：

```python
if self.skill_registry is not None:
    skill_block = build_skill_context_block(self.skill_registry)
    if skill_block:
        system_prompt += f"\n\n{skill_block}"
```

`AgentRuntime` 透传 `skill_registry` 给 `AnswerNode`；`app/api/chat.py` 的 `_build_runtime` 传入全局 `skill_registry` 单例。`skill_registry=None` 或空时无注入（系统提示不含 "技能指令"）。

### 2.4 API 端点（`app/api/skills.py`，前缀 `/api/v1/skills`）

| Method | Path | 用途 | 错误 |
|---|---|---|---|
| GET | `/marketplace?q=` | 搜索 marketplace | |
| GET | `/marketplace/{id}` | marketplace 包详情 | 404 不存在 |
| POST | `/marketplace/{id}/install` | 安装 | 409 已安装；404 不存在 |
| GET | `/installed` | 列已安装 | |
| GET | `/installed/{name}` | 已安装详情 | 404 |
| PATCH | `/installed/{name}` | 切换 enabled | 404 |
| DELETE | `/installed/{name}` | 卸载 | 404；400 路径穿越 |

### 2.5 前端结构

- `frontend/src/lib/api.ts`：3 类型（`InstalledSkill`/`SkillDetail`/`SkillPackageInfo`）+ 7 API 函数。
- `frontend/src/components/skills/TabSwitch.tsx`：两 tab 切换（active 主蓝 #2563EB）。
- `frontend/src/components/skills/SkillCard.tsx`：discriminated union（installed/marketplace 两模式）。installed 模式显示 enabled 徽章 + 点击开抽屉；marketplace 模式显示"已安装"徽章或"安装"按钮。
- `frontend/src/components/skills/SkillDetailDrawer.tsx`：侧滑抽屉，installed/marketplace 两模式复用。渲染 frontmatter 元信息 + `ReactMarkdown`+`remarkGfm` 渲染 SKILL.md 正文；installed 模式额外有 enable 开关 + 卸载（带确认）+ 文件树。
- `frontend/src/components/skills/SkillsView.tsx`：重构为两 tab。「已安装」tab = 内置工具只读分区（`ToolCard` 标"内置"徽章）+ 已安装 Skill 分区；「市场」tab = 搜索框 + 结果网格。`installedNames` Set 控制市场卡片的"已安装"徽章。

## 3. 遇到的问题与解决方案

### 3.1 Skill 格式认知偏差

**问题**：初版设计误将 skill 设计为 `skill.yaml`（manifest）+ `tools.py`（导出 Tool 子类）+ 依赖的结构，混同于 function-calling tool 包。

**根因**：未先确认主流 skill 规范（clawhub / Anthropic agent-skills）。

**解决**：调研标准 SKILL.md 格式后，改为"指令包"模型——`SKILL.md`（YAML frontmatter + markdown 正文）为核心，可选 `scripts/`、`LICENSE.txt`。Skill 不子类化 `Tool`，不进 `ToolRegistry`，而是注入系统提示。`ToolRegistry`（函数调用）与 `SkillRegistry`（指令）解耦并存。

### 3.2 enabled 语义的 registry 一致性

**问题**：`SkillRegistry.list_all()` 是否应过滤 `enabled=True`？若不过滤，A1 注入会把 disabled skill 也注入。

**根因**：enabled 状态存 DB，registry 是内存镜像，两者需同步策略。

**解决**：采用"registry 只持有 enabled skill"契约——启动 lifespan 只加载 `list_enabled()` 行；`set_enabled(False)` 从 registry 移除，`set_enabled(True)` 重新加载。因此 `list_all()` 返回的就是当前 enabled 集合，injection 直接用 `list_all()` 无需二次过滤。设计 spec §4.3 明确记录此契约。

### 3.3 卸载路径穿越防护

**问题**：`uninstall(name)` 删除 `installed_path` 指向的目录。若 DB 行被篡改使 `installed_path` 指向 `installed_root` 之外（如 `/etc`），`shutil.rmtree` 会误删。

**根因**：`installed_path` 来自 DB，不可信。

**解决**：`uninstall` 先 `Path(row.installed_path).resolve()` 和 `self.installed_root.resolve()`，再 `target.relative_to(root)`——若 target 不在 root 之内抛 `ValueError`（被 API 层转为 400）。`resolve()` 处理符号链接。测试 `test_uninstall_rejects_path_traversal` 模拟篡改 DB 行验证此守卫。

### 3.4 测试中 `_make_factory` 的 async 陷阱

**问题**：Task 10 测试用 `monkeypatch.setattr("app.main.async_session_factory", _make_factory(db))` 替换 session 工厂。plan 原稿把 `_make_factory` 写成 `async def`，调用 `_make_factory(db)` 返回的是 coroutine 而非上下文管理器类，`async with` 会失败。

**根因**：`async def` 函数调用返回 coroutine，需 `await` 才得到返回值；而此处需要的是同步调用返回一个 async CM 类。

**解决**：改为 `def _make_factory(db)`（同步函数），返回内部定义的 `_F` 类（实现 `__aenter__`/`__aexit__`）。plan 执行时作为 pre-flight 修正记录并通知实现者。

### 3.5 runtime.py 的未使用导入

**问题**：plan Task 11 Step 4 指示在 `runtime.py` 加 `from app.skills.registry import skill_registry as global_skill_registry`，但 Step 5 让 `chat.py` 显式传入全局 `skill_registry`，导致该导入未使用（dead import）。

**根因**：plan 前后步骤设计冗余。

**解决**：pre-flight 扫描发现此矛盾，通知实现者不加该导入。`AgentRuntime.skill_registry` 默认 `None`，由 `chat.py` 显式传入全局单例。

### 3.6 API 端点返回 `vars(dto)` 而非 pydantic response_model

**问题**：plan 设计 API 端点用 `vars(dto)` 返回 dict，未定义 pydantic 响应模型。

**根因**：plan 为简化首版，DTO 是 dataclass，`vars()` 转 dict 后 FastAPI 自动 JSON 序列化。

**解决**：保留 plan 设计（功能正确，测试通过）。后续若需 OpenAPI schema 严格化，可为每个端点定义 pydantic `response_model`。记录为演进项。

## 4. 测试

### 4.1 测试文件清单

| 文件 | 覆盖 | 用例数 |
|---|---|---|
| `tests/skills/test_manifest.py` | SKILL.md 解析、缺字段、非法 name、可选字段默认 | 5 |
| `tests/skills/test_loader.py` | 目录加载、缺 SKILL.md、name 不匹配、非法 manifest | 4 |
| `tests/skills/test_registry.py` | add/remove/get/list_all、overwrite、missing noop | 6 |
| `tests/skills/test_injection.py` | 空 registry 空串、单 skill 注入、多 skill 分段 | 3 |
| `tests/database/test_skill_repo.py` | upsert/get、list_all、list_enabled、set_enabled、delete | 5 |
| `tests/skills/test_marketplace.py` | source_id、search 匹配、info、download、空目录 | 10 |
| `tests/skills/test_service.py` | install/uninstall/enable/list/get + 路径穿越 | 11 |
| `tests/api/test_skills_api.py` | 7 端点全流程含错误路径 | 9 |
| `tests/test_main_lifespan_skills.py` | lifespan 加载 enabled skill | 1 |
| `tests/runtime/test_answer_node_skill_injection.py` | A1 注入系统提示、None/空不注入 | 3 |

### 4.2 最终运行结果

```
pytest -q
319 passed, 9 warnings, 11 errors in 5.05s
```

11 errors 全部是 `test_new_apis.py` / `test_session_agent.py` 中的 `RuntimeError: There is no current event loop` —— 这是 pre-existing 的测试顺序噪音（在 rag-citations 分支已存在，早于本特性），与本特性无关。

```
cd frontend && npx tsc --noEmit   # exit 0，无错误
```

### 4.3 端到端 API 验证（curl）

启动后端后逐项验证：
- `GET /marketplace` → 2 个示例包
- `GET /marketplace?q=legal` → 1 个
- `POST /marketplace/legal-citation-extractor/install` → 200
- 重复 install → 409
- `PATCH /installed/{name} {"enabled":false}` → enabled=false
- `DELETE /installed/{name}` → 204
- `DELETE /installed/nope` → 404
- 安装后重启后端 → skill 仍在，lifespan 日志显示 `SELECT ... FROM installed_skills WHERE enabled IS true` 重建 registry

### 4.4 前端验证

`/skills` 页面 HTTP 200 渲染（含"技能管理"标题）；前端代理 `/api/v1/skills/*` 正常（marketplace 返回 2，installed 返回 0）。tsc 无错误。

## 5. 演进方向

- **A2 按需检索注入**：skill 数增多时，A1 始终注入导致系统提示膨胀。可用 embedding 相似度匹配 top-k 相关 skill 再注入（复用现有 `EmbeddingService`）。
- **ClawhubAdapter 真实接入**：实现 `MarketplaceAdapter` 接口走 clawhub HTTP API，service 层零改动。注意 clawhub 的 `skill_id` 可能与 `manifest.name` 不同——当前前端 `installedNames` Set 用 `name` 键、市场卡用 `skill_id` 查（本地 adapter 下两者相等），接入 clawhub 时需统一标识策略。
- **skill 包签名/沙箱**：首版不限制 agent 执行 `scripts/` 下脚本。后续可加包签名验证 + 脚本执行白名单/沙箱。
- **skill 版本升级与依赖管理**：当前 install 检测 name 冲突直接 409。可加 `upgrade` 端点支持版本升级，以及 skill 间依赖声明。
- **API 响应模型严格化**：为 7 端点定义 pydantic `response_model`，使 OpenAPI schema 完整。
- **前端 React 优化**：`installedNames` Set 用 `useMemo`；`SkillDetailDrawer` 加 `AbortController` 防快速关闭时的 stale setState；卸载失败时重置确认状态。
