"use client";

import { useState } from "react";
import { indexDocument } from "@/lib/api";
import { Loader2, CheckCircle2, AlertCircle, ArrowUp, FileText } from "lucide-react";

export default function IndexPanel() {
  const [domain, setDomain] = useState("");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ document_id: string; chunks: number } | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!domain || !title || !content) return;
    setLoading(true);
    setResult(null);
    setError("");
    try {
      const res = await indexDocument({ domain, title, content, source: source || undefined });
      setResult(res);
      setTitle("");
      setSource("");
      setContent("");
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = !!domain && !!title && !!content && !loading;

  return (
    <div className="space-y-5 fade-up">
      <div className="flex items-center gap-2 text-text-muted">
        <FileText className="w-4 h-4" />
        <span className="text-[13px] font-medium">导入文档到知识库</span>
      </div>

      <div className="card overflow-hidden">
        <div className="grid grid-cols-2 border-b border-border">
          <Field
            label="领域 domain"
            required
            value={domain}
            onChange={setDomain}
            placeholder="legal / finance / ..."
          />
          <Field
            label="来源 source"
            value={source}
            onChange={setSource}
            placeholder="民法典.pdf"
            lastInRow
          />
        </div>
        <div className="border-b border-border">
          <Field
            label="标题 title"
            required
            value={title}
            onChange={setTitle}
            placeholder="文档标题"
          />
        </div>
        <div className="p-4">
          <div className="flex items-center justify-between mb-2">
            <FieldLabel label="正文 content" required />
            <span className="text-[11px] text-text-faint">{content.length} 字</span>
          </div>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="粘贴文档正文内容…"
            rows={10}
            className="input focus-ring w-full px-3 py-2 text-[13px] resize-none leading-relaxed"
          />
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-bg-surface-2">
          <span className="text-[11px] text-text-faint">
            {canSubmit ? "已就绪" : "请填写必填字段"}
          </span>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="btn-primary focus-ring flex items-center gap-2 px-4 h-9 text-[12px] font-medium"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowUp className="w-3.5 h-3.5" strokeWidth={2.5} />}
            {loading ? "处理中…" : "导入"}
          </button>
        </div>
      </div>

      {result && (
        <div className="flex items-center gap-3 px-4 py-3 border border-success/30 bg-success-dim rounded-[10px] fade-up">
          <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" strokeWidth={2} />
          <span className="text-[12px] text-success font-medium">
            已导入 · doc={result.document_id.slice(0, 12)} · chunks={result.chunks}
          </span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px] fade-up">
          <AlertCircle className="w-4 h-4 text-danger flex-shrink-0" strokeWidth={2} />
          <span className="text-[12px] text-danger">{error}</span>
        </div>
      )}
    </div>
  );
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] text-text-dim font-medium">{label}</span>
      {required && <span className="text-[11px] text-accent">*</span>}
    </div>
  );
}

function Field({
  label,
  required,
  value,
  onChange,
  placeholder,
  lastInRow,
}: {
  label: string;
  required?: boolean;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  lastInRow?: boolean;
}) {
  return (
    <div className={`p-4 ${lastInRow ? "" : "border-r border-border"}`}>
      <div className="mb-2">
        <FieldLabel label={label} required={required} />
      </div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input focus-ring w-full px-3 py-2 text-[13px]"
      />
    </div>
  );
}
