"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listAgents, deleteAgent, createSessionWithAgent, AgentInfo } from "@/lib/api";
import { AgentFormDialog } from "@/components/agents/AgentFormDialog";

interface CategoryInfo {
  name: string;
  is_builtin: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

async function listCategories(): Promise<CategoryInfo[]> {
  const res = await fetch(`${API_BASE}/knowledge/categories`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.map((c: { name: string; is_builtin?: boolean }) => ({
    name: c.name,
    is_builtin: !!c.is_builtin,
  }));
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AgentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [a, c] = await Promise.all([listAgents(), listCategories()]);
      setAgents(a);
      setCategories(c);
    } catch {
      setError("加载失败");
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleDelete = async (agent: AgentInfo) => {
    if (agent.is_builtin) return;
    if (!confirm(`确认删除智能体「${agent.name}」？`)) return;
    try {
      await deleteAgent(agent.id);
      await refresh();
    } catch {
      setError("删除失败");
    }
  };

  const router = useRouter();

  const handleAccess = async (agent: AgentInfo) => {
    setError(null);
    try {
      const session = await createSessionWithAgent(agent.id);
      window.dispatchEvent(
        new CustomEvent("domainforge:session-active", { detail: session.id }),
      );
      router.push("/");
    } catch {
      setError("创建会话失败");
    }
  };

  return (
    <div className="flex-1 w-full min-w-0 overflow-y-auto">
      <div className="mx-auto max-w-7xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">智能体</h1>
        <button
          className="rounded bg-[#2563EB] px-3 py-1.5 text-sm text-white"
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          新建智能体
        </button>
      </div>
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="font-medium">{agent.name}</h3>
                {agent.is_builtin && (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                    内置
                  </span>
                )}
                {agent.domain && (
                  <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-[#2563EB]">
                    {agent.domain}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  className="text-sm text-[#2563EB]"
                  onClick={() => handleAccess(agent)}
                >
                  访问
                </button>
                <button
                  className="text-sm text-[#2563EB]"
                  onClick={() => {
                    setEditing(agent);
                    setDialogOpen(true);
                  }}
                >
                  编辑
                </button>
                <button
                  className="text-sm text-gray-400 disabled:cursor-not-allowed"
                  disabled={agent.is_builtin}
                  title={agent.is_builtin ? "内置不可删" : ""}
                  onClick={() => handleDelete(agent)}
                >
                  删除
                </button>
              </div>
            </div>
            <p className="mb-2 text-sm text-gray-600">
              {agent.description || "（无简介）"}
            </p>
            <p className="text-xs text-gray-400">
              {agent.model_name || "默认模型"} · temp {agent.temperature}
            </p>
          </div>
        ))}
        {agents.length === 0 && (
          <p className="text-sm text-gray-500">暂无智能体，点击右上角新建。</p>
        )}
      </div>
        <AgentFormDialog
          open={dialogOpen}
          agent={editing}
          categories={categories}
          onClose={() => setDialogOpen(false)}
          onSaved={refresh}
        />
      </div>
    </div>
  );
}
