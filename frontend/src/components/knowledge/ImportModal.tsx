"use client";

import { useRef, useState } from "react";
import {
  X,
  Upload,
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Settings2,
} from "lucide-react";
import {
  confirmImport,
  getImportStatus,
  listCategories,
  uploadFiles,
  type CategoryStats,
  type ImportJobStatus,
  type PreviewSession,
} from "@/lib/api";

type Phase = "config" | "preview" | "done";

const STRATEGIES = [
  { value: "semantic", label: "语义分块（默认）", desc: "按段落+句子边界，通用场景" },
  { value: "legal", label: "法律分块", desc: "按第X条切分，适合法条/判决" },
  { value: "finance", label: "金融分块", desc: "按标题层级切分，适合研报/公告" },
];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function ImportModal({
  domain,
  categories,
  onClose,
  onSuccess,
}: {
  domain: string;
  categories: CategoryStats[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("config");
  const [files, setFiles] = useState<File[]>([]);
  const [selectedDomain, setSelectedDomain] = useState(domain);
  const [strategy, setStrategy] = useState("semantic");
  const [chunkSize, setChunkSize] = useState(500);
  const [chunkOverlap, setChunkOverlap] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<PreviewSession | null>(null);
  const [result, setResult] = useState<{ total_chunks: number; document_ids: string[] } | null>(null);
  const [jobStatus, setJobStatus] = useState<ImportJobStatus | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = Array.from(e.target.files ?? []);
    setFiles(list);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const list = Array.from(e.dataTransfer.files ?? []);
    setFiles(list);
  };

  const handleParse = async () => {
    if (files.length === 0 || !selectedDomain) return;
    setLoading(true);
    setError("");
    try {
      const session = await uploadFiles(files, selectedDomain, strategy, chunkSize, chunkOverlap);
      setPreview(session);
      setPhase("preview");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setLoading(true);
    setError("");
    setJobStatus(null);
    try {
      const { job_id } = await confirmImport(preview.session_id);
      // 轮询 job 状态直到终态
      const deadline = Date.now() + 10 * 60 * 1000; // 10 分钟上限
      while (Date.now() < deadline) {
        const s = await getImportStatus(job_id);
        setJobStatus(s);
        if (s.status === "succeeded") {
          setResult({ total_chunks: s.total_chunks, document_ids: s.document_ids });
          setPhase("done");
          return;
        }
        if (s.status === "failed") {
          throw new Error(s.error || "导入失败");
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
      throw new Error("导入超时");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleDone = () => {
    onSuccess();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm fade-in" onClick={onClose}>
      <div
        className="card w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Upload className="w-4 h-4 text-accent" />
            <h2 className="text-[15px] font-semibold text-text">
              {phase === "config" && "导入知识到类别"}
              {phase === "preview" && "预览解析结果"}
              {phase === "done" && "导入完成"}
            </h2>
          </div>
          <button onClick={onClose} className="focus-ring w-8 h-8 grid place-items-center rounded-[6px] text-text-faint hover:bg-bg-hover hover:text-text">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {error && (
            <div className="flex items-center gap-3 px-4 py-3 mb-4 border border-danger/30 bg-danger-dim rounded-[10px]">
              <AlertCircle className="w-4 h-4 text-danger flex-shrink-0" />
              <span className="text-[12px] text-danger">{error}</span>
            </div>
          )}

          {phase === "config" && (
            <div className="space-y-5">
              {/* 目标类别 */}
              <div>
                <label className="text-[12px] text-text-dim font-medium mb-1.5 block">目标类别</label>
                <select
                  value={selectedDomain}
                  onChange={(e) => setSelectedDomain(e.target.value)}
                  className="input focus-ring w-full px-3 py-2 text-[13px]"
                >
                  {categories.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name} {c.is_builtin ? "（内置）" : "（自定义）"}
                    </option>
                  ))}
                </select>
              </div>

              {/* 文件选择 */}
              <div>
                <label className="text-[12px] text-text-dim font-medium mb-1.5 block">选择文件（支持 PDF / Word / Excel / Markdown / TXT）</label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  className="border-2 border-dashed border-border-bright rounded-[12px] py-10 px-4 text-center cursor-pointer hover:border-accent hover:bg-accent-soft transition-colors"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.docx,.xlsx,.xls,.md,.markdown,.html,.htm,.txt,.text"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <Upload className="w-7 h-7 mx-auto mb-2 text-text-faint" strokeWidth={1.5} />
                  <p className="text-[13px] text-text-dim mb-1">
                    {files.length === 0 ? "点击或拖拽文件到此处" : `已选择 ${files.length} 个文件`}
                  </p>
                  <p className="text-[11px] text-text-faint">单文件最大 20MB，单批最多 10 个</p>
                </div>
                {files.length > 0 && (
                  <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
                    {files.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-bg-surface-2 rounded-[6px] text-[12px]">
                        <FileText className="w-3 h-3 text-accent flex-shrink-0" />
                        <span className="flex-1 truncate text-text-dim">{f.name}</span>
                        <span className="text-text-faint">{formatSize(f.size)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 分块策略 */}
              <div>
                <label className="text-[12px] text-text-dim font-medium mb-1.5 block flex items-center gap-1.5">
                  <Settings2 className="w-3 h-3" /> 知识组织策略
                </label>
                <div className="space-y-2">
                  {STRATEGIES.map((s) => (
                    <label
                      key={s.value}
                      className={`flex items-start gap-2.5 p-3 rounded-[10px] border cursor-pointer transition-colors
                        ${strategy === s.value
                          ? "border-accent bg-accent-dim"
                          : "border-border hover:bg-bg-hover"}`}
                    >
                      <input
                        type="radio"
                        name="strategy"
                        value={s.value}
                        checked={strategy === s.value}
                        onChange={() => setStrategy(s.value)}
                        className="mt-0.5 accent-accent"
                      />
                      <div className="flex-1">
                        <div className="text-[13px] text-text font-medium">{s.label}</div>
                        <div className="text-[11px] text-text-muted mt-0.5">{s.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* 高级参数 */}
              {strategy === "semantic" && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[12px] text-text-dim font-medium mb-1.5 block">分块大小（字符）</label>
                    <input
                      type="number"
                      value={chunkSize}
                      onChange={(e) => setChunkSize(Number(e.target.value))}
                      min={100}
                      max={2000}
                      className="input focus-ring w-full px-3 py-2 text-[13px]"
                    />
                  </div>
                  <div>
                    <label className="text-[12px] text-text-dim font-medium mb-1.5 block">重叠（字符）</label>
                    <input
                      type="number"
                      value={chunkOverlap}
                      onChange={(e) => setChunkOverlap(Number(e.target.value))}
                      min={0}
                      max={500}
                      className="input focus-ring w-full px-3 py-2 text-[13px]"
                    />
                  </div>
                </div>
              )}

              {/* 只读 embedding 维度 */}
              <div className="flex items-center gap-2 px-3 py-2 bg-bg-surface-2 rounded-[8px]">
                <span className="text-[11px] text-text-faint">嵌入向量维度</span>
                <span className="text-[11px] text-text-dim font-mono">1024</span>
                <span className="text-[10px] text-text-faint ml-auto">系统级固定</span>
              </div>
            </div>
          )}

          {phase === "preview" && preview && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 px-3 py-2 bg-accent-dim rounded-[8px]">
                <FileText className="w-3.5 h-3.5 text-accent" />
                <span className="text-[12px] text-accent font-medium">
                  {preview.files.length} 个文件 · 策略 {preview.chunk_strategy} · 维度 {preview.embedding_dimension}
                </span>
                <span className="text-[10px] text-accent/70 ml-auto">
                  预览会话 {preview.expires_in}s 内有效
                </span>
              </div>

              {preview.files.map((f, i) => (
                <div key={i} className="border border-border rounded-[10px] p-3 bg-bg-surface-2/40">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                      <span className="text-[13px] text-text font-medium truncate">{f.filename}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-dim text-accent">
                        {f.file_type}
                      </span>
                    </div>
                    <span className="text-[11px] text-text-faint flex-shrink-0">{formatSize(f.file_size_bytes)}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[11px] mb-2">
                    <div>
                      <div className="text-text-faint">字符数</div>
                      <div className="text-text font-semibold">{f.char_count}</div>
                    </div>
                    <div>
                      <div className="text-text-faint">分块数</div>
                      <div className="text-accent font-semibold">{f.chunk_count}</div>
                    </div>
                    <div>
                      <div className="text-text-faint">字数</div>
                      <div className="text-text font-semibold">{f.word_count}</div>
                    </div>
                  </div>
                  {f.sample_chunks.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border">
                      <div className="text-[10px] text-text-faint uppercase tracking-wider mb-1">前 3 个分块预览</div>
                      <div className="space-y-1">
                        {f.sample_chunks.map((s, j) => (
                          <div key={j} className="text-[11px] text-text-dim bg-bg-surface px-2 py-1 rounded line-clamp-2">
                            {s}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {phase === "preview" && loading && jobStatus && (
            <div className="mt-4 px-4 py-3 border border-border rounded-[10px] bg-bg-surface-2/60">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[12px] text-text-dim font-medium flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
                  正在生成嵌入向量…
                </span>
                <span className="text-[11px] text-text-faint font-mono">
                  {jobStatus.processed_chunks} / {jobStatus.total_chunks} 分块
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-bg-hover overflow-hidden">
                <div
                  className="h-full bg-accent transition-all duration-300"
                  style={{
                    width: `${
                      jobStatus.total_chunks > 0
                        ? Math.min(100, (jobStatus.processed_chunks / jobStatus.total_chunks) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
              <p className="text-[10px] text-text-faint mt-1.5">
                大文件导入可能需要数分钟，遇到速率限制会自动退避重试，请勿关闭窗口。
              </p>
            </div>
          )}

          {phase === "done" && result && (
            <div className="text-center py-8">
              <div className="w-14 h-14 mx-auto mb-4 grid place-items-center rounded-full bg-success-dim">
                <CheckCircle2 className="w-7 h-7 text-success" />
              </div>
              <h3 className="text-[16px] font-semibold text-text mb-2">导入成功</h3>
              <p className="text-[13px] text-text-muted">
                已导入 {result.document_ids.length} 个文档，共 {result.total_chunks} 个分块
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-bg-surface-2/40">
          {phase === "config" && (
            <>
              <span className="text-[11px] text-text-faint">解析阶段不会写入数据库</span>
              <button
                onClick={handleParse}
                disabled={files.length === 0 || !selectedDomain || loading}
                className="btn-primary focus-ring h-9 px-4 flex items-center gap-1.5 text-[13px]"
              >
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowRight className="w-3.5 h-3.5" />}
                {loading ? "解析中…" : "开始解析"}
              </button>
            </>
          )}
          {phase === "preview" && (
            <>
              <button
                onClick={() => {
                  setPhase("config");
                  setPreview(null);
                }}
                disabled={loading}
                className="btn-ghost focus-ring h-9 px-4 flex items-center gap-1.5 text-[13px]"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> 返回修改
              </button>
              <button
                onClick={handleConfirm}
                disabled={loading}
                className="btn-primary focus-ring h-9 px-4 flex items-center gap-1.5 text-[13px]"
              >
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                {loading ? "导入中…" : "确认导入"}
              </button>
            </>
          )}
          {phase === "done" && (
            <button onClick={handleDone} className="btn-primary focus-ring h-9 px-4 ml-auto flex items-center gap-1.5 text-[13px]">
              完成
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
