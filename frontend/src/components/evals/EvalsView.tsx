"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { listEvalResults, runEvals, type EvalResultEntry } from "@/lib/api";
import { Activity, Play, AlertCircle, Loader2, TrendingUp } from "lucide-react";

const DATASETS = [
  { value: "legal/legal_basic", label: "法律 · 基础" },
  { value: "finance/finance_basic", label: "金融 · 基础" },
];

interface RunSummary {
  dataset: string;
  total: number;
  results: Array<{
    case_id: string;
    correctness: number;
    groundedness: number;
    retrieval_recall: number;
    context_precision: number;
    latency_ms: number;
  }>;
}

export default function EvalsView() {
  const [dataset, setDataset] = useState(DATASETS[0].value);
  const [running, setRunning] = useState(false);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<EvalResultEntry[]>([]);

  const refreshHistory = async () => {
    try {
      const list = await listEvalResults();
      setHistory(list.slice(0, 50));
    } catch {
      setHistory([]);
    }
  };

  useEffect(() => {
    refreshHistory();
  }, []);

  const handleRun = async () => {
    setRunning(true);
    setError("");
    setSummary(null);
    try {
      const res = await runEvals(dataset);
      setSummary(res);
      refreshHistory();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 relative">
      <div className="absolute inset-0 grid-lines pointer-events-none opacity-30" />
      <PageHeader code="EV" title="评测中心" description="领域评测集 · 指标计算 · Bad Case 分析" />

      <div className="relative flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
          {/* 运行评测 */}
          <div className="card p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Activity className="w-4 h-4" />
              <span className="text-[13px] font-medium">运行评测</span>
            </div>

            <div className="flex items-center gap-3">
              <label className="text-[12px] text-text-dim">数据集</label>
              <select
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
                className="input focus-ring px-3 py-2 text-[13px] min-w-[200px]"
              >
                {DATASETS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
              <button
                onClick={handleRun}
                disabled={running}
                className="btn-primary focus-ring flex items-center gap-2 px-4 h-9 text-[12px] font-medium"
              >
                {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                {running ? "运行中…" : "运行"}
              </button>
            </div>

            {error && (
              <div className="flex items-center gap-3 px-4 py-3 mt-4 border border-danger/30 bg-danger-dim rounded-[10px]">
                <AlertCircle className="w-4 h-4 text-danger" />
                <span className="text-[12px] text-danger">{error}</span>
              </div>
            )}
          </div>

          {/* 当前结果 */}
          {summary && (
            <div className="card p-5 fade-up">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="w-4 h-4 text-accent" />
                <h3 className="text-[14px] font-semibold text-text">
                  {summary.dataset} · {summary.total} 条用例
                </h3>
              </div>
              <div className="space-y-2">
                {summary.results.map((r) => (
                  <div key={r.case_id} className="border border-border rounded-[10px] p-3 bg-bg-surface-2/40">
                    <div className="flex items-center justify-between mb-2">
                      <code className="text-[12px] text-accent font-mono">{r.case_id}</code>
                      <span className="text-[11px] text-text-faint">{r.latency_ms.toFixed(0)} ms</span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-[11px]">
                      <Metric label="正确性" value={r.correctness} />
                      <Metric label="忠实度" value={r.groundedness} />
                      <Metric label="召回率" value={r.retrieval_recall} />
                      <Metric label="精确率" value={r.context_precision} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 历史结果 */}
          <div className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-border bg-bg-surface-2/40">
              <h3 className="text-[13px] font-semibold text-text">历史结果</h3>
            </div>
            {history.length === 0 ? (
              <div className="text-center py-10 text-[12px] text-text-muted">暂无历史评测记录</div>
            ) : (
              <table className="w-full text-[12px]">
                <thead className="bg-bg-surface-2 text-text-muted text-[11px] uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">时间</th>
                    <th className="text-left px-4 py-2 font-medium">数据集</th>
                    <th className="text-left px-4 py-2 font-medium">指标</th>
                    <th className="text-right px-4 py-2 font-medium">分数</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {history.map((h) => (
                    <tr key={h.id} className="hover:bg-bg-hover">
                      <td className="px-4 py-2 text-text-muted whitespace-nowrap">
                        {h.created_at ? new Date(h.created_at).toLocaleString("zh-CN") : "-"}
                      </td>
                      <td className="px-4 py-2 text-text-dim">{h.dataset_name}</td>
                      <td className="px-4 py-2">
                        <code className="text-[11px] text-accent">{h.metric}</code>
                      </td>
                      <td className="px-4 py-2 text-right text-text font-semibold">
                        {h.score.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "text-success" : pct >= 40 ? "text-warning" : "text-danger";
  return (
    <div>
      <div className="text-text-faint mb-1">{label}</div>
      <div className={`font-semibold ${color}`}>{pct}%</div>
    </div>
  );
}
