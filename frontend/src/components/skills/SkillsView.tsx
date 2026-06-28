"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  listTools,
  listInstalledSkills,
  searchMarketplace,
  installSkill,
  type ToolInfo,
  type InstalledSkill,
  type SkillPackageInfo,
} from "@/lib/api";
import { Boxes, Wrench, Shield, Clock, CheckCircle2, AlertCircle, Search } from "lucide-react";
import { TabSwitch } from "./TabSwitch";
import { SkillCard } from "./SkillCard";
import { SkillDetailDrawer } from "./SkillDetailDrawer";

type TabKey = "installed" | "marketplace";

export default function SkillsView() {
  const [tab, setTab] = useState<TabKey>("installed");
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [marketplace, setMarketplace] = useState<SkillPackageInfo[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [drawerMode, setDrawerMode] = useState<"installed" | "marketplace" | null>(null);
  const [drawerId, setDrawerId] = useState("");

  const refreshInstalled = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [t, s] = await Promise.all([listTools(), listInstalledSkills()]);
      setTools(t);
      setSkills(s);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshMarketplace = useCallback(async (q: string) => {
    setLoading(true);
    setError("");
    try {
      setMarketplace(await searchMarketplace(q));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "installed") refreshInstalled();
    else refreshMarketplace(query);
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  function openDrawer(mode: "installed" | "marketplace", id: string) {
    setDrawerMode(mode);
    setDrawerId(id);
  }

  async function handleInstall(id: string) {
    try {
      await installSkill(id);
      await refreshMarketplace(query);
    } catch (e) {
      setError(String(e));
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    refreshMarketplace(query);
  }

  const installedNames = new Set(skills.map((s) => s.name));

  return (
    <div className="flex-1 flex flex-col min-w-0 relative">
      <div className="absolute inset-0 grid-lines pointer-events-none opacity-30" />
      <PageHeader code="SK" title="技能管理" description="工具注册中心 · 内置 Skill 与 MCP 适配" />

      <div className="relative flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between mb-6">
            <TabSwitch
              tabs={[
                { key: "installed", label: "已安装" },
                { key: "marketplace", label: "市场" },
              ]}
              active={tab}
              onChange={(k) => setTab(k as TabKey)}
            />
            {tab === "marketplace" && (
              <form onSubmit={handleSearch} className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-text-faint absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="搜索 skill…"
                    className="pl-8 pr-3 py-1.5 text-[12px] border border-border rounded-[6px] bg-bg-panel text-text focus:outline-none focus:border-[#2563EB]"
                  />
                </div>
              </form>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px] mb-4">
              <AlertCircle className="w-4 h-4 text-danger" />
              <span className="text-[12px] text-danger">{error}</span>
            </div>
          )}

          {tab === "installed" ? (
            <>
              <Section title="内置工具" count={tools.length} icon={<Wrench className="w-3.5 h-3.5" />}>
                {loading ? (
                  <div className="text-text-muted text-[13px]">加载中…</div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 stagger">
                    {tools.map((t) => <ToolCard key={t.name} tool={t} />)}
                  </div>
                )}
              </Section>

              <Section title="已安装 Skill" count={skills.length} icon={<Boxes className="w-3.5 h-3.5" />}>
                {loading ? (
                  <div className="text-text-muted text-[13px]">加载中…</div>
                ) : skills.length === 0 ? (
                  <div className="text-text-muted text-[13px]">尚未安装任何 skill。去「市场」tab 搜索安装。</div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 stagger">
                    {skills.map((s) => (
                      <SkillCard
                        key={s.name}
                        mode="installed"
                        skill={s}
                        onClick={() => openDrawer("installed", s.name)}
                      />
                    ))}
                  </div>
                )}
              </Section>
            </>
          ) : (
            <Section title="市场 Skill" count={marketplace.length} icon={<Boxes className="w-3.5 h-3.5" />}>
              {loading ? (
                <div className="text-text-muted text-[13px]">加载中…</div>
              ) : marketplace.length === 0 ? (
                <div className="text-text-muted text-[13px]">未找到匹配的 skill。</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 stagger">
                  {marketplace.map((p) => (
                    <SkillCard
                      key={p.skill_id}
                      mode="marketplace"
                      skill={p}
                      installedNames={installedNames}
                      onClick={() => openDrawer("marketplace", p.skill_id)}
                      onInstall={handleInstall}
                    />
                  ))}
                </div>
              )}
            </Section>
          )}
        </div>
      </div>

      {drawerMode && (
        <SkillDetailDrawer
          mode={drawerMode}
          identifier={drawerId}
          open={true}
          onClose={() => setDrawerMode(null)}
          onChanged={() => {
            refreshInstalled();
            if (tab === "marketplace") refreshMarketplace(query);
          }}
        />
      )}
    </div>
  );
}

function Section({ title, count, icon, children }: { title: string; count: number; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 text-text-muted mb-4">
        {icon}
        <span className="text-[13px] font-medium">{title} ({count})</span>
      </div>
      {children}
    </div>
  );
}

function ToolCard({ tool }: { tool: ToolInfo }) {
  const sensitive = tool.permission_scope === "sensitive";
  return (
    <div className="card p-4 opacity-90">
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
        <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-bg-dim text-text-faint">内置</span>
      </div>
      <p className="text-[12px] text-text-muted mb-3 leading-relaxed">{tool.description}</p>
      <div className="flex items-center gap-3 text-[11px] text-text-faint mb-3">
        <span className="flex items-center gap-1"><Shield className="w-3 h-3" /> {tool.permission_scope}</span>
        <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {tool.timeout}s</span>
      </div>
      <div className="flex items-center gap-1 text-[10px] text-success">
        <CheckCircle2 className="w-3 h-3" /><span>内置工具（只读）</span>
      </div>
    </div>
  );
}
