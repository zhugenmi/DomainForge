"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Plus,
  Database,
  Boxes,
  PanelLeftClose,
  PanelLeftOpen,
  Activity,
  ClipboardList,
  Cpu,
  MessageSquare,
  Trash2,
  Bot,
} from "lucide-react";
import { deleteSession, healthCheck, listSessions, type SessionInfo } from "@/lib/api";

type Health = "loading" | "ok" | "error";

const NAV_ITEMS = [
  { href: "/agents" as const, label: "领域智能体", icon: Bot, code: "AG" },
  { href: "/knowledge" as const, label: "知识库管理", icon: Database, code: "KB" },
  { href: "/skills" as const, label: "技能管理", icon: Boxes, code: "SK" },
  { href: "/audit" as const, label: "审计日志", icon: ClipboardList, code: "AD" },
  { href: "/evals" as const, label: "评测中心", icon: Activity, code: "EV" },
];

export default function Sidebar({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [health, setHealth] = useState<Health>("loading");
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeSession, setActiveSession] = useState<string | undefined>();

  const refreshSessions = async () => {
    try {
      const list = await listSessions();
      setSessions(list.slice(0, 8));
    } catch {
      setSessions([]);
    }
  };

  useEffect(() => {
    let cancelled = false;
    healthCheck()
      .then(() => !cancelled && setHealth("ok"))
      .catch(() => !cancelled && setHealth("error"));
    refreshSessions();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onChange = () => {
      refreshSessions();
      setActiveSession(undefined);
    };
    const onActive = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      setActiveSession(detail);
      refreshSessions();
    };
    window.addEventListener("domainforge:new-chat", onChange);
    window.addEventListener("domainforge:session-active", onActive);
    return () => {
      window.removeEventListener("domainforge:new-chat", onChange);
      window.removeEventListener("domainforge:session-active", onActive);
    };
  }, []);

  const handleNewChat = () => {
    setActiveSession(undefined);
    window.dispatchEvent(new CustomEvent("domainforge:new-chat"));
    if (pathname !== "/") router.push("/");
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "j") {
        e.preventDefault();
        handleNewChat();
      } else if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        onToggleCollapsed();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <aside
      className={`
        sidebar-transition h-full flex flex-col flex-shrink-0
        bg-bg-elevated border-r border-border
        ${collapsed ? "w-[64px]" : "w-[248px]"}
      `}
    >
      {/* Brand */}
      <div
        className={`flex items-center h-[var(--header-h)] border-b border-border ${
          collapsed ? "justify-center px-2" : "px-4"
        }`}
      >
        <div className="flex items-center gap-2.5 min-w-0" title="DomainForge">
          <div className="relative w-7 h-7 flex-shrink-0 grid place-items-center rounded-[8px] bg-accent-dim border border-accent/30">
            <div className="w-2 h-2 rounded-full bg-accent" />
          </div>
          {!collapsed && (
            <div className="min-w-0 flex flex-col">
              <span className="text-[13px] font-semibold text-text leading-none tracking-tight">
                DomainForge
              </span>
              <span className="text-[10px] text-text-muted mt-1">领域智能体控制台</span>
            </div>
          )}
        </div>
      </div>

      {/* New chat */}
      <div className={`p-3 ${collapsed ? "px-2" : ""}`}>
        <button
          onClick={handleNewChat}
          title="开启新会话 (Ctrl+J)"
          aria-label="开启新会话"
          className={`btn-primary focus-ring group relative w-full flex items-center gap-2.5
            ${collapsed ? "h-10 justify-center" : "h-10 px-3"}`}
        >
          <Plus
            className="w-4 h-4 flex-shrink-0 transition-transform duration-200 group-hover:rotate-90"
            strokeWidth={2.25}
          />
          {!collapsed && (
            <>
              <span className="text-[13px] font-medium">开启新会话</span>
              <span className="ml-auto text-[10px] text-white/70">⌘J</span>
            </>
          )}
        </button>
      </div>

      {/* 会话历史 */}
      {!collapsed && sessions.length > 0 && (
        <div className="px-3 pb-2">
          <div className="flex items-center gap-2 px-1.5 mb-1.5">
            <span className="text-[10px] text-text-faint uppercase tracking-wider font-medium">
              最近会话
            </span>
            <div className="flex-1 h-px bg-border" />
          </div>
          <div className="space-y-0.5 max-h-[200px] overflow-y-auto">
            {sessions.map((s) => {
              const isActive = activeSession === s.id;
              return (
                <div
                  key={s.id}
                  className={`group relative flex items-center gap-2 px-2 h-8 rounded-[6px]
                    text-[12px] transition-colors
                    ${isActive ? "bg-accent-dim text-accent" : "text-text-dim hover:bg-bg-hover hover:text-text"}`}
                >
                  <button
                    onClick={() => {
                      setActiveSession(s.id);
                      window.dispatchEvent(
                        new CustomEvent("domainforge:session-active", { detail: s.id }),
                      );
                      if (pathname !== "/") router.push("/");
                    }}
                    className="focus-ring flex items-center gap-2 flex-1 min-w-0 h-full text-left"
                  >
                    <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" strokeWidth={1.75} />
                    <span className="flex-1 truncate">{s.title || s.id.slice(0, 8)}</span>
                  </button>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!confirm(`删除会话「${s.title || s.id.slice(0, 8)}」？此操作不可撤销。`)) return;
                      try {
                        await deleteSession(s.id);
                        if (activeSession === s.id) {
                          setActiveSession(undefined);
                          window.dispatchEvent(new CustomEvent("domainforge:new-chat"));
                          if (pathname !== "/") router.push("/");
                        }
                        await refreshSessions();
                      } catch (err) {
                        alert(`删除失败：${err}`);
                      }
                    }}
                    title="删除会话"
                    aria-label="删除会话"
                    className="focus-ring flex-shrink-0 w-6 h-6 grid place-items-center rounded-[4px]
                      text-text-faint opacity-0 group-hover:opacity-100
                      hover:bg-danger-dim hover:text-danger transition-all"
                  >
                    <Trash2 className="w-3 h-3" strokeWidth={2} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Nav */}
      {!collapsed && (
        <div className="px-3 pt-2 pb-1">
          <div className="flex items-center gap-2 px-1.5 mb-1.5">
            <span className="text-[10px] text-text-faint uppercase tracking-wider font-medium">
              模块
            </span>
            <div className="flex-1 h-px bg-border" />
          </div>
        </div>
      )}
      <nav className={`flex-1 space-y-0.5 ${collapsed ? "px-2" : "px-3"}`}>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`focus-ring relative group flex items-center rounded-[8px]
                ${collapsed ? "h-10 justify-center" : "h-9 gap-2.5 px-2.5"}
                text-[13px] transition-colors duration-150
                ${isActive ? "text-accent bg-accent-dim" : "text-text-dim hover:text-text hover:bg-bg-hover"}`}
            >
              {isActive && !collapsed && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-[2.5px] bg-accent rounded-full" />
              )}
              <Icon
                className={`w-[16px] h-[16px] flex-shrink-0 ${isActive ? "text-accent" : ""}`}
                strokeWidth={1.75}
              />
              {!collapsed && (
                <>
                  <span className="flex-1 truncate">{item.label}</span>
                  <span
                    className={`text-[10px] tracking-wider ${
                      isActive ? "text-accent/70" : "text-text-faint group-hover:text-text-muted"
                    }`}
                  >
                    {item.code}
                  </span>
                </>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-2 space-y-1">
        {!collapsed && (
          <div className="flex items-center gap-2.5 px-2.5 py-2">
            <Cpu className="w-3.5 h-3.5 text-text-muted" strokeWidth={1.75} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full
                    ${health === "ok" ? "bg-success pulse-dot" : ""}
                    ${health === "error" ? "bg-danger" : ""}
                    ${health === "loading" ? "bg-text-faint pulse-dot" : ""}`}
                />
                <span className="text-[11px] text-text-dim font-medium">
                  {health === "ok" ? "服务在线" : health === "error" ? "服务离线" : "检测中…"}
                </span>
              </div>
              <p className="text-[10px] text-text-faint mt-0.5 truncate">/api/v1</p>
            </div>
          </div>
        )}
        <button
          onClick={onToggleCollapsed}
          title={collapsed ? "展开侧栏" : "收起侧栏"}
          aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          className={`btn-ghost focus-ring w-full flex items-center
            ${collapsed ? "h-9 justify-center" : "h-7 px-2.5 gap-2"}`}
        >
          {collapsed ? (
            <PanelLeftOpen className="w-4 h-4" strokeWidth={1.75} />
          ) : (
            <>
              <PanelLeftClose className="w-3.5 h-3.5" strokeWidth={1.75} />
              <span className="text-[11px]">收起</span>
              <span className="ml-auto text-[10px] text-text-faint">⌘B</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
