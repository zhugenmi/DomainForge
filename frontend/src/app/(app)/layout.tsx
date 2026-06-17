"use client";

import { type ReactNode } from "react";
import Sidebar from "@/components/Sidebar";
import { useSidebarCollapsed } from "@/hooks/useSidebarCollapsed";

export default function AppLayout({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useSidebarCollapsed();

  return (
    <div className="flex h-full w-full">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
      />
      {children}
    </div>
  );
}
