"use client";

import { Scale, TrendingUp, HeartPulse, Shield, Building2, Folder, FileText } from "lucide-react";
import type { CategoryStats } from "@/lib/api";

const ICON_MAP: Record<string, typeof Scale> = {
  legal: Scale,
  finance: TrendingUp,
  medical: HeartPulse,
  insurance: Shield,
  enterprise: Building2,
};

function formatWordCount(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)} 万字`;
  return `${n} 字`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return "—";
  }
}

export default function CategoryCard({
  category,
  onClick,
}: {
  category: CategoryStats;
  onClick: () => void;
}) {
  const Icon = ICON_MAP[category.name] ?? Folder;
  return (
    <button
      onClick={onClick}
      className="card card-hover focus-ring p-5 text-left w-full group"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="w-11 h-11 grid place-items-center rounded-[12px] bg-accent-dim border border-accent/20 group-hover:bg-accent group-hover:border-accent transition-colors">
          <Icon className="w-5 h-5 text-accent group-hover:text-white transition-colors" strokeWidth={1.75} />
        </div>
        {category.is_builtin ? (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-bg-surface-2 text-text-faint font-medium">
            内置
          </span>
        ) : (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-warning-dim text-warning font-medium">
            自定义
          </span>
        )}
      </div>

      <h3 className="text-[15px] font-semibold text-text mb-3 capitalize">{category.name}</h3>

      <div className="space-y-1.5 text-[12px]">
        <div className="flex items-center justify-between">
          <span className="text-text-muted flex items-center gap-1.5">
            <FileText className="w-3 h-3" /> 文档
          </span>
          <span className="text-text font-medium">{category.file_count}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-muted">字数</span>
          <span className="text-text font-medium">{formatWordCount(category.word_count)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-muted">更新</span>
          <span className="text-text-dim">{formatDate(category.last_updated)}</span>
        </div>
      </div>
    </button>
  );
}
