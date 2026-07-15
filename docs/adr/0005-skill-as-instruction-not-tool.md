# ADR 0005:Skill 是指令包,非 function-calling tool

> 状态:已采纳 | 日期:2026-06-28

## 背景

引入 Skill 系统时,初版设计误将 skill 设计为 `skill.yaml`(manifest) + `tools.py`(导出 Tool 子类) + 依赖的结构,混同于 function-calling tool 包。

## 决策

Skill 是给 agent 阅读的**指令包**(`SKILL.md` 为核心,YAML frontmatter + markdown 正文),不子类化 `Tool`,不进 `ToolRegistry`,而是注入 agent 系统提示上下文。`ToolRegistry`(函数调用)与 `SkillRegistry`(指令)解耦并存。

## 理由

### 调研

确认主流 skill 规范:clawhub / Anthropic agent-skills 均以 `SKILL.md` 为核心,是指令包而非可执行工具包。

### 备选方案与拒绝原因

| 方案 | 拒绝原因 |
|---|---|
| Skill = Tool 子类,进 ToolRegistry | 混淆两个概念--Skill 是"教 agent 怎么做",Tool 是"agent 能调用什么";Tool 需要 schema + executor,Skill 只需 markdown;强行合并会让 Skill 强制实现 execute,且 Skill 正文无法注入 prompt |
| Skill 走独立 registry 但参与函数调用 | LLM 无法区分 Skill 与 Tool 的调用语义;Skill 无 executor,LLM 调用后无返回值 |

### 选"指令包 + 系统提示注入"的理由

1. **符合主流规范**:clawhub / Anthropic agent-skills 同款模型,生态兼容。
2. **概念清晰**:Skill = 知识/指令(声明式),Tool = 能力/动作(命令式)。两者并存、互不污染。
3. **零执行风险**:Skill 只是文本,不执行代码,无沙箱/签名需求;Tool 才需考虑权限/二次确认。
4. **注入简单**:`build_skill_context_block(registry)` 拼系统提示,AnswerNode 已有 prompt 组装逻辑,接入点单一。
5. **演进路径**:A1 始终注入(首版) -> A2 按需检索注入(skill 数多时,用 embedding 相似度匹配 top-k)。指令包模型让 A2 只改 retrieval,不改 Skill 本身。

## 后果

- **正面**:概念清晰;生态兼容;零执行风险;注入简单。
- **负面**:A1 始终注入导致系统提示随 skill 数线性膨胀--首版接受,后续 A2 演进。
- **边界**:Skill 可选带 `scripts/` 目录,但首版不限制 agent 执行这些脚本。后续若需让 Skill 执行代码,加包签名 + 脚本白名单 + 沙箱,不影响 Skill 本身的指令包语义。
- **与 Tool 的协作**:Skill 可在正文中指示 agent"遇到 X 场景时调用 Y 工具",但 Skill 本身不调用工具--agent 读指令后自行决定调 Tool。
