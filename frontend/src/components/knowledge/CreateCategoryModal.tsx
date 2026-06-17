"use client";

import { useState } from "react";
import { X, FolderPlus, Loader2, AlertCircle } from "lucide-react";
import { createCategory } from "@/lib/api";

export default function CreateCategoryModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    const n = name.trim().toLowerCase();
    if (!n) {
      setError("请输入类别名称");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await createCategory(n);
      onCreated();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm fade-in" onClick={onClose}>
      <div className="card w-full max-w-md m-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <FolderPlus className="w-4 h-4 text-accent" />
            <h2 className="text-[15px] font-semibold text-text">新建知识类别</h2>
          </div>
          <button onClick={onClose} className="focus-ring w-8 h-8 grid place-items-center rounded-[6px] text-text-faint hover:bg-bg-hover hover:text-text">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          {error && (
            <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px]">
              <AlertCircle className="w-4 h-4 text-danger flex-shrink-0" />
              <span className="text-[12px] text-danger">{error}</span>
            </div>
          )}
          <div>
            <label className="text-[12px] text-text-dim font-medium mb-1.5 block">类别名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              placeholder="如：medical / insurance / hr"
              className="input focus-ring w-full px-3 py-2 text-[13px]"
              autoFocus
            />
            <p className="text-[11px] text-text-faint mt-1.5">小写字母，将作为知识分区的标识</p>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border bg-bg-surface-2/40">
          <button onClick={onClose} className="btn-ghost focus-ring h-9 px-4 text-[13px]">取消</button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="btn-primary focus-ring h-9 px-4 flex items-center gap-1.5 text-[13px]"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FolderPlus className="w-3.5 h-3.5" />}
            创建
          </button>
        </div>
      </div>
    </div>
  );
}
