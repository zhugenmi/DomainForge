"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { listAudit, type AuditEntry } from "@/lib/api";
import { ClipboardList, RefreshCw, AlertCircle } from "lucide-react";

export default function AuditView() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listAudit(100);
      setEntries(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="flex-1 flex flex-col min-w-0 relative">
      <div className="absolute inset-0 grid-lines pointer-events-none opacity-30" />
      <PageHeader
        code="AD"
        title="审计日志"
        description="请求链路 · 关键操作留痕"
        actions={
          <button onClick={refresh} className="btn-ghost focus-ring h-8 px-3 flex items-center gap-1.5 text-[12px]">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        }
      />

      <div className="relative flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8">
          <div className="flex items-center gap-2 text-text-muted mb-6">
            <ClipboardList className="w-4 h-4" />
            <span className="text-[13px] font-medium">最近 {entries.length} 条审计记录</span>
          </div>

          {error && (
            <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px] mb-4">
              <AlertCircle className="w-4 h-4 text-danger" />
              <span className="text-[12px] text-danger">{error}</span>
            </div>
          )}

          {loading && <div className="text-center py-12 text-text-muted text-[13px]">加载中…</div>}

          {!loading && entries.length === 0 && !error && (
            <div className="text-center py-16 border border-dashed border-border rounded-[12px]">
              <ClipboardList className="w-8 h-8 mx-auto mb-3 text-text-faint" strokeWidth={1.25} />
              <p className="text-[12px] text-text-muted">暂无审计日志</p>
            </div>
          )}

          {!loading && entries.length > 0 && (
            <div className="card overflow-hidden">
              <table className="w-full text-[12px]">
                <thead className="bg-bg-surface-2 text-text-muted text-[11px] uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">时间</th>
                    <th className="text-left px-4 py-2 font-medium">Trace ID</th>
                    <th className="text-left px-4 py-2 font-medium">动作</th>
                    <th className="text-left px-4 py-2 font-medium">详情</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {entries.map((e) => (
                    <tr key={e.id} className="hover:bg-bg-hover">
                      <td className="px-4 py-2 text-text-muted whitespace-nowrap">
                        {e.created_at ? new Date(e.created_at).toLocaleString("zh-CN") : "-"}
                      </td>
                      <td className="px-4 py-2">
                        <code className="text-accent text-[11px]">{e.trace_id.slice(0, 12)}</code>
                      </td>
                      <td className="px-4 py-2">
                        <span className="px-2 py-0.5 rounded-full bg-accent-dim text-accent text-[11px] font-medium">
                          {e.action}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-text-dim">
                        <code className="text-[11px]">
                          {JSON.stringify(e.payload).slice(0, 100)}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
