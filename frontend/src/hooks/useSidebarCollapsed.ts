"use client";

import { useCallback, useSyncExternalStore } from "react";

const KEY = "domainforge:sidebar-collapsed";

const subscribe = (cb: () => void) => {
  window.addEventListener("storage", cb);
  return () => window.removeEventListener("storage", cb);
};

const getSnapshot = () =>
  localStorage.getItem(KEY) === "1" ? "1" : "0";

const getServerSnapshot = () => "0";

export function useSidebarCollapsed() {
  const raw = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const collapsed = raw === "1";

  const setCollapsed = useCallback((next: boolean) => {
    localStorage.setItem(KEY, next ? "1" : "0");
    window.dispatchEvent(new StorageEvent("storage", { key: KEY }));
  }, []);

  return [collapsed, setCollapsed] as const;
}
