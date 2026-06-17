"use client";

import { useState, type KeyboardEvent } from "react";
import { searchKnowledge, type ChunkResult } from "@/lib/api";
import { Search, Loader2, BookOpen, FileText, ArrowUp, Hash } from "lucide-react";

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [mode, setMode] = useState<"vector" | "bm25" | "hybrid">("hybrid");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ChunkResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setSearched(true);
    setError("");
    try {
      const res = await searchKnowledge(q, topK, mode);
      setResults(res.results);
    } catch (err) {
      setError(String(err));
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div className="space-y-5 fade-up">
      <div className="flex items-center gap-2 text-text-muted">
        <Search className="w-4 h-4" />
        <span className="text-[13px] font-medium">知识检索测试</span>
      </div>

      {/* 模式切换 */}
      <div className="flex items-center gap-2 text-[12px]">
        <span className="text-text-muted">检索模式：</span>
        {(["hybrid", "vector", "bm25"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`focus-ring px-2.5 py-1 rounded-full font-medium transition-colors
              ${mode === m ? "bg-accent text-white" : "bg-bg-surface-2 text-text-dim hover:bg-bg-hover"}`}
          >
            {m === "hybrid" ? "混合召回" : m === "vector" ? "向量" : "BM25"}
          </button>
        ))}
      </div>

      {/* 搜索框 */}
      <div className="flex items-stretch card overflow-hidden">
        <div className="flex items-center px-3 border-r border-border text-accent">
          <Search className="w-4 h-4" strokeWidth={2} />
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKey}
          placeholder="输入检索查询…"
          className="focus-ring flex-1 bg-transparent px-3 py-2.5 text-[13px] text-text placeholder:text-text-faint outline-none"
        />
        <div className="flex items-center border-l border-border">
          <span className="px-3 text-[10px] text-text-faint tracking-wider uppercase">TOP_K</span>
          <input
            type="number"
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            min={1}
            max={20}
            className="focus-ring w-14 bg-transparent px-2 py-2.5 text-[13px] text-text text-center outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={!query.trim() || loading}
          className="btn-primary focus-ring flex items-center gap-2 px-4 border-l border-border text-[12px] font-medium"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowUp className="w-3.5 h-3.5" strokeWidth={2.5} />}
          {loading ? "检索中" : "检索"}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px]">
          <Hash className="w-3.5 h-3.5 text-danger" strokeWidth={2} />
          <span className="text-[12px] text-danger">{error}</span>
        </div>
      )}

      {searched && results.length === 0 && !loading && !error && (
        <div className="text-center py-16 border border-dashed border-border rounded-[12px]">
          <BookOpen className="w-8 h-8 mx-auto mb-3 text-text-faint" strokeWidth={1.25} />
          <p className="text-[12px] text-text-muted">未找到相关结果</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[11px] text-text-faint">命中</span>
          <span className="text-[12px] text-accent font-semibold">{results.length}</span>
        </div>
      )}

      <div className="space-y-2 stagger">
        {results.map((chunk, i) => (
          <ResultCard key={chunk.id} chunk={chunk} rank={i + 1} />
        ))}
      </div>
    </div>
  );
}

function ResultCard({ chunk, rank }: { chunk: ChunkResult; rank: number }) {
  const domain = chunk.metadata?.domain;
  const score = chunk.score;
  return (
    <div className="card card-hover overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-bg-surface-2/60">
        <span className="text-[10px] text-accent font-semibold w-6">#{String(rank).padStart(2, "0")}</span>
        <FileText className="w-3.5 h-3.5 text-text-faint" strokeWidth={1.75} />
        <span className="text-[11px] text-text-dim truncate">{chunk.document_id.slice(0, 16)}</span>
        {domain != null && (
          <span className="text-[10px] text-accent bg-accent-dim px-1.5 py-0.5 rounded font-medium">
            {String(domain)}
          </span>
        )}
        <div className="flex-1" />
        {score != null && (
          <span className="text-[11px] text-text-muted">
            score: <span className="text-accent font-semibold">{Number(score).toFixed(4)}</span>
          </span>
        )}
      </div>
      <p className="px-4 py-3 text-[13px] text-text leading-relaxed">{chunk.content}</p>
    </div>
  );
}
