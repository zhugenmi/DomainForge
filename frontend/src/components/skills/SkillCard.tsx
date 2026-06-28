"use client";

import { Boxes, Download, CheckCircle2, Trash2 } from "lucide-react";
import type { InstalledSkill, SkillPackageInfo } from "@/lib/api";

interface InstalledCardProps {
  mode: "installed";
  skill: InstalledSkill;
  installedNames?: never;
  onClick: () => void;
  onInstall?: never;
}

interface MarketplaceCardProps {
  mode: "marketplace";
  skill: SkillPackageInfo;
  installedNames: Set<string>;
  onClick: () => void;
  onInstall: (id: string) => void;
}

type Props = InstalledCardProps | MarketplaceCardProps;

export function SkillCard(props: Props) {
  if (props.mode === "installed") {
    const s = props.skill;
    return (
      <div className="card card-hover p-4 cursor-pointer" onClick={props.onClick}>
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 grid place-items-center rounded-[8px] bg-accent-dim text-accent flex-shrink-0">
              <Boxes className="w-4 h-4" strokeWidth={1.75} />
            </div>
            <div className="min-w-0">
              <h3 className="text-[13px] font-semibold text-text truncate">{s.name}</h3>
              <span className="text-[10px] text-text-faint">v{s.version || "-"}</span>
            </div>
          </div>
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
            s.enabled ? "bg-success-dim text-success" : "bg-bg-dim text-text-faint"
          }`}>
            {s.enabled ? "已启用" : "已禁用"}
          </span>
        </div>
        <p className="text-[12px] text-text-muted mb-3 leading-relaxed line-clamp-2">{s.description}</p>
        <div className="flex items-center gap-1 text-[10px] text-danger" onClick={(e) => e.stopPropagation()}>
          <Trash2 className="w-3 h-3" />
          <span>点击卡片查看详情/卸载</span>
        </div>
      </div>
    );
  }

  const p = props.skill;
  const installed = props.installedNames.has(p.skill_id);
  return (
    <div className="card card-hover p-4 cursor-pointer" onClick={props.onClick}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 grid place-items-center rounded-[8px] bg-accent-dim text-accent flex-shrink-0">
            <Boxes className="w-4 h-4" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <h3 className="text-[13px] font-semibold text-text truncate">{p.name}</h3>
            <span className="text-[10px] text-text-faint">v{p.version || "-"} · {p.author || "-"}</span>
          </div>
        </div>
      </div>
      <p className="text-[12px] text-text-muted mb-3 leading-relaxed line-clamp-2">{p.description}</p>
      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        {installed ? (
          <span className="flex items-center gap-1 text-[11px] text-success">
            <CheckCircle2 className="w-3.5 h-3.5" /> 已安装
          </span>
        ) : (
          <button
            onClick={() => props.onInstall(p.skill_id)}
            className="flex items-center gap-1 text-[11px] px-3 py-1 rounded-[6px] bg-[#2563EB] text-white hover:opacity-90"
          >
            <Download className="w-3 h-3" /> 安装
          </button>
        )}
      </div>
    </div>
  );
}
