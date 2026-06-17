/**
 * Skills (Tools) data layer.
 *
 * 当前后端尚未暴露 /api/v1/skills 接口，内置工具元数据静态来自
 * app/tools/builtin/*.py。预留 fetchSkills() 便于将来对接真实接口。
 */

export type SkillStatus = "active" | "disabled";

export interface SkillParameter {
  name: string;
  type: "string" | "integer" | "number" | "boolean";
  description: string;
  required: boolean;
  default?: unknown;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  category: "compute" | "retrieval" | "system";
  status: SkillStatus;
  permissionScope: string;
  timeout: number;
  parameters: SkillParameter[];
  registeredAt: string; // ISO
}

const BUILTIN: Skill[] = [
  {
    id: "sk_calc_01",
    name: "calculator",
    description: "执行受限字符集的安全数学表达式求值。",
    category: "compute",
    status: "active",
    permissionScope: "default",
    timeout: 5,
    parameters: [
      {
        name: "expression",
        type: "string",
        description: "数学表达式，如 '2 + 3 * 4'",
        required: true,
      },
    ],
    registeredAt: "2026-01-12T08:00:00Z",
  },
  {
    id: "sk_rag_01",
    name: "knowledge_search",
    description: "基于向量语义相似度检索知识库中的相关文档片段。",
    category: "retrieval",
    status: "active",
    permissionScope: "read",
    timeout: 10,
    parameters: [
      {
        name: "query",
        type: "string",
        description: "搜索查询文本",
        required: true,
      },
      {
        name: "top_k",
        type: "integer",
        description: "返回结果数量",
        required: false,
        default: 5,
      },
    ],
    registeredAt: "2026-01-15T10:30:00Z",
  },
];

const NETWORK_DELAY_MS = 180;

export async function fetchSkills(): Promise<Skill[]> {
  // 模拟后端延时；接真接口时改为 fetch(`${API_BASE}/skills`)
  await new Promise((r) => setTimeout(r, NETWORK_DELAY_MS));
  return BUILTIN;
}

export function getSkillCategoryLabel(c: Skill["category"]): string {
  return { compute: "COMPUTE", retrieval: "RETRIEVAL", system: "SYSTEM" }[c];
}
