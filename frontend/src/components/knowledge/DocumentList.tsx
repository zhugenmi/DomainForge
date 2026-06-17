"use client";

import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Upload,
  Trash2,
  FileText,
  Loader2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { deleteDocument, listDocuments, type DocumentInfo } from "@/lib/api";

function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

const FILE_TYPE_LABEL: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
  xlsx: "Excel",
  md: "Markdown",
  html: "HTML",
  txt: "文本",
  other: "文件",
};

export default function DocumentList({
  domain,
  onBack,
  onImport,
}: {
  domain: string;
  onBack: () => void;
  onImport: () => void;
}) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listDocuments(domain);
      setDocs(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`删除文档「${title}」？关联的 chunks 也会被删除。`)) return;
    try {
      await deleteDocument(id);
      await refresh();
    } catch (e) {
      alert(`删除失败：${e}`);
    }
  };

  return (
    <div className="space-y-5 fade-up">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="btn-ghost focus-ring h-9 px-3 flex items-center gap-1.5 text-[13px]">
            <ArrowLeft className="w-3.5 h-3.5" /> 返回
          </button>
          <h2 className="text-[18px] font-semibold text-text capitalize">{domain}</h2>
          <span className="text-[12px] text-text-muted">{docs.length} 个文档</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={refresh} className="btn-ghost focus-ring h-9 px-3 flex items-center gap-1.5 text-[13px]">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> 刷新
          </button>
          <button onClick={onImport} className="btn-primary focus-ring h-9 px-4 flex items-center gap-1.5 text-[13px]">
            <Upload className="w-3.5 h-3.5" /> 导入文档
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px]">
          <AlertCircle className="w-4 h-4 text-danger" />
          <span className="text-[12px] text-danger">{error}</span>
        </div>
      )}

      {loading ? (
        <div className="text-center py-16 text-text-muted text-[13px]">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
          加载中…
        </div>
      ) : docs.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-border rounded-[12px]">
          <FileText className="w-8 h-8 mx-auto mb-3 text-text-faint" strokeWidth={1.25} />
          <p className="text-[13px] text-text-muted mb-4">该类别暂无文档</p>
          <button onClick={onImport} className="btn-primary focus-ring h-9 px-4 inline-flex items-center gap-1.5 text-[13px]">
            <Upload className="w-3.5 h-3.5" /> 导入第一个文档
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-bg-surface-2 text-text-muted text-[11px] uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">文档名</th>
                <th className="text-left px-4 py-2.5 font-medium">类型</th>
                <th className="text-right px-4 py-2.5 font-medium">大小</th>
                <th className="text-right px-4 py-2.5 font-medium">字数</th>
                <th className="text-right px-4 py-2.5 font-medium">分块</th>
                <th className="text-left px-4 py-2.5 font-medium">更新时间</th>
                <th className="text-right px-4 py-2.5 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {docs.map((d) => (
                <tr key={d.id} className="hover:bg-bg-hover">
                  <td className="px-4 py-2.5 text-text font-medium truncate max-w-xs">
                    {d.title}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-dim text-accent font-medium">
                      {FILE_TYPE_LABEL[d.file_type ?? "other"] ?? d.file_type}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-text-dim">{formatSize(d.file_size_bytes)}</td>
                  <td className="px-4 py-2.5 text-right text-text-dim">{d.word_count ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right text-text-dim">{d.chunk_count ?? "—"}</td>
                  <td className="px-4 py-2.5 text-text-muted text-[12px]">{formatDate(d.updated_at)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => handleDelete(d.id, d.title)}
                      title="删除"
                      className="focus-ring w-7 h-7 grid place-items-center rounded-[6px] text-text-faint hover:bg-danger-dim hover:text-danger transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
