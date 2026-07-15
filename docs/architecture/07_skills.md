# 07 Skill 管理模块:可插拔指令包系统

> 版本:0.1.0 | 日期:2026-06-28 | 对应代码:`app/skills/`、`app/api/skills.py`、`app/database/models/skill.py`、`app/database/repositories/skill_repo.py`、`app/runtime/nodes/answer_node.py`、`alembic/versions/0008_installed_skills.py`

---

## 1. 设计目标

引入标准 `SKILL.md` 可插拔 skill 系统:支持从 marketplace 搜索/安装/卸载 skill,enabled skill 的正文注入 agent 系统提示,安装状态持久化跨重启保留。

### 1.1 核心架构决策

- **Skill = 指令包,非 function-calling tool**:Skill 是给 agent 阅读的 markdown 指令包(`SKILL.md` 为核心),独立于 `ToolRegistry`。builtin tools(calculator、web_search 等)走 `ToolRegistry` 参与函数调用;skill 走 `SkillRegistry`,其正文注入 agent 系统提示。两者并存、互不污染。详见 [adr/0005-skill-as-instruction-not-tool.md](../adr/0005-skill-as-instruction-not-tool.md)。
- **A1 始终注入模型**:所有 `enabled=True` skill 的 `SKILL.md` 正文在每次 chat 请求时拼入系统提示。简单、确定,token 占用随 skill 数线性增长;首版接受,后续可演进到 A2 按需检索注入。
- **MarketplaceAdapter 抽象 + LocalMarketplaceAdapter 实现**:marketplace 接口抽象为 `search/info/download` 三方法 + `source_id` 属性。`LocalMarketplaceAdapter` 读本地 `skills/marketplace/` 目录作 mock 源;后续 `ClawhubAdapter` 实现同接口走 HTTP 即可接入真实平台,service 层零改动。
- **持久化 + 启动重建**:`installed_skills` 表存元数据 + `installed_path`;启动 lifespan 从 DB 查 `enabled=True` 行,`load_skill_from_dir` 重建 `SkillRegistry`。安装的 skill 重启后仍在,enabled 状态保留。

---

## 2. 模块划分

`app/skills/` 下文件职责:

| 文件 | 职责 |
|---|---|
| `manifest.py` | `SkillManifest` dataclass + `parse_skill_md()`:用 `python-frontmatter` 解析 SKILL.md,校验 `name`(必填、匹配 `^[a-z0-9-]+$`)、`description`(必填),可选 `version`/`author`/`license`。解析失败抛 `SkillManifestError(ValueError)`。 |
| `loader.py` | `SkillDescriptor`(manifest + path + files) + `load_skill_from_dir()`:读目录下 SKILL.md,校验目录名 == manifest.name,`rglob` 收集相对文件列表。 |
| `registry.py` | `SkillRegistry`:`{name: SkillDescriptor}` 内存 dict,`add/remove/get/list_all`。模块单例 `skill_registry`。enabled 语义由"启动只加载 enabled 行 + set_enabled 增删"保证,`list_all()` 返回即当前 enabled 集合。 |
| `injection.py` | `build_skill_context_block(registry) -> str`:组装 header + 每个 skill 一段 `## 技能:{name}\n{body_md}`。空 registry 返回空串。 |
| `service.py` | `SkillService`:install(download->load->copytree->DB upsert->registry.add)、uninstall(路径校验->registry.remove->rmtree->DB delete)、set_enabled(DB 更新->registry 增删)、list/get/search。DTO: `InstalledSkillDTO`、`InstalledSkillDetailDTO`。 |
| `marketplace/base.py` | `MarketplaceAdapter` ABC:`source_id` 属性 + async `search/info/download`。 |
| `marketplace/models.py` | `SkillPackageInfo` dataclass(8 字段,含 `body_preview` 前 300 字)。 |
| `marketplace/local_adapter.py` | `LocalMarketplaceAdapter`:扫 `skills/marketplace/*/SKILL.md`,`source_id="local"`,search 匹配 name/description 子串(大小写不敏感),空 query 返回全部,`download` 返回包目录 Path(不拷贝,由 service 拷贝)。 |

---

## 3. 持久化

`installed_skills` 表(Alembic 迁移 `0008_installed_skills`):

| 列 | 类型 | 说明 |
|---|---|---|
| `name` | String(100) PK | = frontmatter name = 目录名 |
| `version` | String(50) | |
| `source` | String(50) | marketplace source_id("local") |
| `manifest_json` | Text | 完整 manifest 快照(asdict 序列化) |
| `installed_path` | String(500) | `skills/installed/<name>` 绝对路径 |
| `enabled` | Boolean | 是否注入上下文 |
| `installed_at` | DateTime | server_default now |

`SkillRepo`(`app/database/repositories/skill_repo.py`):`upsert/get/list_all/list_enabled/set_enabled/delete`,async,依赖 `AsyncSession`,caller commit。

启动加载(`app/main.py` lifespan `_load_installed_skills`):`async with async_session_factory() as db: rows = SkillRepo(db).list_enabled()`,逐行 `load_skill_from_dir` + `skill_registry.add`,per-skill try/except 不阻塞启动。

---

## 4. 注入点(A1)

`app/runtime/nodes/answer_node.py`:`AnswerNode.__init__` 加 `skill_registry: SkillRegistry | None = None` 参数。在系统提示组装完成(reasoning 块之后、messages 构建之前)插入:

```python
if self.skill_registry is not None:
    skill_block = build_skill_context_block(self.skill_registry)
    if skill_block:
        system_prompt += f"\n\n{skill_block}"
```

`AgentRuntime` 透传 `skill_registry` 给 `AnswerNode`;`app/api/chat.py` 的 `_build_runtime` 传入全局 `skill_registry` 单例。`skill_registry=None` 或空时无注入(系统提示不含"技能指令")。

### 4.1 enabled 语义的 registry 一致性

采用"registry 只持有 enabled skill"契约:
- 启动 lifespan 只加载 `list_enabled()` 行
- `set_enabled(False)` 从 registry 移除
- `set_enabled(True)` 重新加载

因此 `list_all()` 返回的就是当前 enabled 集合,injection 直接用 `list_all()` 无需二次过滤。

---

## 5. API 端点

`app/api/skills.py`,前缀 `/api/v1/skills`:

| Method | Path | 用途 | 错误 |
|---|---|---|---|
| GET | `/marketplace?q=` | 搜索 marketplace | |
| GET | `/marketplace/{id}` | marketplace 包详情 | 404 不存在 |
| POST | `/marketplace/{id}/install` | 安装 | 409 已安装;404 不存在 |
| GET | `/installed` | 列已安装 | |
| GET | `/installed/{name}` | 已安装详情 | 404 |
| PATCH | `/installed/{name}` | 切换 enabled | 404 |
| DELETE | `/installed/{name}` | 卸载 | 404;400 路径穿越 |

> **卸载路径穿越防护**:`uninstall(name)` 删除 `installed_path` 指向的目录前,先 `Path(row.installed_path).resolve()` 和 `self.installed_root.resolve()`,再 `target.relative_to(root)`--若 target 不在 root 之内抛 `ValueError`(被 API 层转为 400)。详见 [fix/2026-06-28-skill-path-traversal.md](../fix/2026-06-28-skill-path-traversal.md)。

---

## 6. 当前限制与后续

1. **A2 按需检索注入**:skill 数增多时,A1 始终注入导致系统提示膨胀。可用 embedding 相似度匹配 top-k 相关 skill 再注入(复用现有 `EmbeddingService`)。
2. **ClawhubAdapter 真实接入**:实现 `MarketplaceAdapter` 接口走 clawhub HTTP API,service 层零改动。注意 clawhub 的 `skill_id` 可能与 `manifest.name` 不同--当前前端 `installedNames` Set 用 `name` 键、市场卡用 `skill_id` 查(本地 adapter 下两者相等),接入 clawhub 时需统一标识策略。
3. **skill 包签名/沙箱**:首版不限制 agent 执行 `scripts/` 下脚本。后续可加包签名验证 + 脚本执行白名单/沙箱。
4. **skill 版本升级与依赖管理**:当前 install 检测 name 冲突直接 409。可加 `upgrade` 端点支持版本升级,以及 skill 间依赖声明。
5. **API 响应模型严格化**:为 7 端点定义 pydantic `response_model`,使 OpenAPI schema 完整。
