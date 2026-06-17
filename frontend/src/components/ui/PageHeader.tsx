"use client";

import type { ReactNode } from "react";

export function PageHeader({
  code,
  title,
  description,
  actions,
}: {
  code: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="h-[var(--header-h)] flex items-center justify-between px-6 border-b border-border bg-bg-elevated/80 backdrop-blur-md flex-shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-[10px] font-semibold text-accent bg-accent-dim px-2 py-0.5 rounded-full">
          {code}
        </span>
        <h1 className="text-[14px] font-semibold text-text">{title}</h1>
      </div>
      <div className="flex items-center gap-3">
        {description && (
          <span className="text-[12px] text-text-muted truncate max-w-md hidden md:block">
            {description}
          </span>
        )}
        {actions}
      </div>
    </header>
  );
}

export function TabSwitcher<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: string; code?: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex border border-border bg-bg-surface p-0.5 rounded-[10px]">
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            onClick={() => onChange(t.value)}
            className={`focus-ring flex items-center gap-1.5 px-3 h-8 text-[12px] rounded-[8px] font-medium transition-colors duration-150
              ${active ? "bg-accent text-white" : "text-text-dim hover:text-text hover:bg-bg-hover"}`}
          >
            <span>{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}
