"use client";

import { useEffect, useState } from "react";
import {
  AgentInfo,
  AgentCreateInput,
  AgentUpdateInput,
  createAgent,
  listAgentModels,
  updateAgent,
} from "@/lib/api";

interface CategoryInfo {
  name: string;
  is_builtin: boolean;
}

export function AgentFormDialog({
  open,
  agent,
  categories,
  onClose,
  onSaved,
}: {
  open: boolean;
  agent: AgentInfo | null;
  categories: CategoryInfo[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [modelName, setModelName] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [domain, setDomain] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      listAgentModels().then(setModels).catch(() => setModels([]));
    }
  }, [open]);

  useEffect(() => {
    if (agent) {
      setName(agent.name);
      setDescription(agent.description);
      setSystemPrompt(agent.system_prompt);
      setModelName(agent.model_name);
      setTemperature(agent.temperature);
      setDomain(agent.domain ?? "");
    } else {
      setName("");
      setDescription("");
      setSystemPrompt("");
      setModelName("");
      setTemperature(0.7);
      setDomain("");
    }
    setError(null);
  }, [agent, open]);

  if (!open) return null;

  const submit = async () => {
    setError(null);
    try {
      const domainVal = domain === "" ? null : domain;
      if (agent) {
        const input: AgentUpdateInput = {
          name,
          description,
          system_prompt: systemPrompt,
          model_name: modelName,
          temperature,
          domain: domainVal,
        };
        await updateAgent(agent.id, input);
      } else {
        const input: AgentCreateInput = {
          name,
          description,
          system_prompt: systemPrompt,
          model_name: modelName,
          temperature,
          domain: domainVal,
        };
        await createAgent(input);
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">
          {agent ? "编辑智能体" : "新建智能体"}
        </h2>
        <div className="space-y-3">
          <label className="block">
            <span className="text-sm text-gray-600">名称</span>
            <input
              className="mt-1 w-full rounded border px-2 py-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm text-gray-600">简介</span>
            <input
              className="mt-1 w-full rounded border px-2 py-1"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm text-gray-600">说明（system prompt）</span>
            <textarea
              className="mt-1 h-28 w-full rounded border px-2 py-1"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </label>
          <div className="flex gap-3">
            <label className="block flex-1">
              <span className="text-sm text-gray-600">模型</span>
              <select
                className="mt-1 w-full rounded border px-2 py-1"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
              >
                <option value="">默认（跟随系统配置）</option>
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label className="block w-24">
              <span className="text-sm text-gray-600">温度</span>
              <input
                type="number"
                step="0.1"
                min={0}
                max={2}
                className="mt-1 w-full rounded border px-2 py-1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
              />
            </label>
          </div>
          <label className="block">
            <span className="text-sm text-gray-600">绑定知识库</span>
            <select
              className="mt-1 w-full rounded border px-2 py-1"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            >
              <option value="">（无）</option>
              {categories.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                  {c.is_builtin ? "（内置）" : ""}
                </option>
              ))}
            </select>
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            className="rounded border px-3 py-1 text-sm"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="rounded bg-[#2563EB] px-3 py-1 text-sm text-white"
            onClick={submit}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
