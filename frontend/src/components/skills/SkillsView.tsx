"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { listTools, type ToolInfo } from "@/lib/api";
import { Boxes, Wrench, Shield, Clock, CheckCircle2, AlertCircle } from "lucide-react";

export default function SkillsView() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listTools()
      .then((t) => !cancelled && setTools(t))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex-1 flex flex-col min-w-0 relative">
      <div className="absolute inset-0 grid-lines pointer-events-none opacity-30" />
      <PageHeader code="SK" title="技能管理" description="工具注册中心 · 内置 Skill 与 MCP 适配" />

      <div className="relative flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8">
          <div className="flex items-center gap-2 text-text-muted mb-6">
            <Boxes className="w-4 h-4" />
            <span className="text-[13px] font-medium">已注册工具 ({tools.length})</span>
          </div>

          {loading && (
            <div className="text-center py-16 text-text-muted text-[13px]">加载中…</div>
          )}

          {error && (
            <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px] mb-4">
              <AlertCircle className="w-4 h-4 text-danger" />
              <span className="text-[12px] text-danger">{error}</span>
            </div>
          )}

          {!loading && !error && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 stagger">
              {tools.map((t) => (
                <ToolCard key={t.name} tool={t} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolCard({ tool }: { tool: ToolInfo }) {
  const sensitive = tool.permission_scope === "sensitive";
  return (
    <div className="card card-hover p-4">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={`w-8 h-8 grid place-items-center rounded-[8px] flex-shrink-0
            ${sensitive ? "bg-warning-dim text-warning" : "bg-accent-dim text-accent"}`}>
            <Wrench className="w-4 h-4" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <h3 className="text-[13px] font-semibold text-text truncate">{tool.name}</h3>
            <span className="text-[10px] text-text-faint">{tool.parameters.length} 个参数</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium
            ${sensitive ? "bg-warning-dim text-warning" : "bg-success-dim text-success"}`}>
            {sensitive ? "敏感" : "可用"}
          </span>
        </div>
      </div>

      <p className="text-[12px] text-text-muted mb-3 leading-relaxed">{tool.description}</p>

      <div className="flex items-center gap-3 text-[11px] text-text-faint mb-3">
        <span className="flex items-center gap-1">
          <Shield className="w-3 h-3" /> {tool.permission_scope}
        </span>
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" /> {tool.timeout}s
        </span>
      </div>

      {tool.parameters.length > 0 && (
        <div className="border-t border-border pt-2 space-y-1">
          {tool.parameters.map((p) => (
            <div key={p.name} className="flex items-center gap-2 text-[11px]">
              <code className="text-accent font-mono">{p.name}</code>
              <span className="text-text-faint">: {p.type}</span>
              {p.required ? (
                <span className="text-[9px] text-danger">必填</span>
              ) : (
                <span className="text-[9px] text-text-faint">可选</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1 mt-3 text-[10px] text-success">
        <CheckCircle2 className="w-3 h-3" />
        <span>已注册</span>
      </div>
    </div>
  );
}
