"use client";

interface Props {
  tabs: { key: string; label: string }[];
  active: string;
  onChange: (key: string) => void;
}

export function TabSwitch({ tabs, active, onChange }: Props) {
  return (
    <div className="inline-flex border border-border rounded-[8px] overflow-hidden">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`px-4 py-1.5 text-[12px] font-medium transition-colors ${
            active === t.key
              ? "bg-[#2563EB] text-white"
              : "bg-bg-elevated text-text-muted hover:text-text"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
