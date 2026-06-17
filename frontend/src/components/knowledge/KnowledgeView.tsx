"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import CategoryCard from "./CategoryCard";
import DocumentList from "./DocumentList";
import ImportModal from "./ImportModal";
import CreateCategoryModal from "./CreateCategoryModal";
import SearchPanel from "./SearchPanel";
import { listCategories, type CategoryStats } from "@/lib/api";
import { Plus, Upload, Search, Grid3x3, Loader2, AlertCircle, RefreshCw } from "lucide-react";

type View = "grid" | "category" | "search";

export default function KnowledgeView() {
  const [view, setView] = useState<View>("grid");
  const [categories, setCategories] = useState<CategoryStats[]>([]);
  const [activeDomain, setActiveDomain] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [createCatOpen, setCreateCatOpen] = useState(false);

  const refreshCategories = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listCategories();
      setCategories(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshCategories();
  }, [refreshCategories]);

  const openCategory = (domain: string) => {
    setActiveDomain(domain);
    setView("category");
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 relative">
      <div className="absolute inset-0 grid-lines pointer-events-none opacity-30" />
      <PageHeader
        code="KB"
        title="知识库管理"
        description="按领域分类的知识资产 · 多格式文档导入 · 两阶段确认"
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setView(view === "search" ? "grid" : "search")}
              className={`btn-ghost focus-ring h-8 px-3 flex items-center gap-1.5 text-[12px]
                ${view === "search" ? "bg-accent-dim text-accent border-accent/30" : ""}`}
            >
              <Search className="w-3.5 h-3.5" />
              {view === "search" ? "返回类别" : "检索测试"}
            </button>
            <button
              onClick={() => setCreateCatOpen(true)}
              className="btn-ghost focus-ring h-8 px-3 flex items-center gap-1.5 text-[12px]"
            >
              <Plus className="w-3.5 h-3.5" /> 新建类别
            </button>
            <button
              onClick={() => {
                if (view !== "grid") setView("grid");
                setImportOpen(true);
              }}
              className="btn-primary focus-ring h-8 px-3 flex items-center gap-1.5 text-[12px]"
            >
              <Upload className="w-3.5 h-3.5" /> 导入知识
            </button>
          </div>
        }
      />

      <div className="relative flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8">
          {error && (
            <div className="flex items-center gap-3 px-4 py-3 border border-danger/30 bg-danger-dim rounded-[10px] mb-6">
              <AlertCircle className="w-4 h-4 text-danger" />
              <span className="text-[12px] text-danger">{error}</span>
              <button onClick={refreshCategories} className="ml-auto text-[11px] text-accent underline">
                重试
              </button>
            </div>
          )}

          {view === "grid" && (
            <div className="space-y-6 fade-up">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Grid3x3 className="w-4 h-4 text-text-muted" />
                  <h2 className="text-[15px] font-semibold text-text">知识类别</h2>
                  <span className="text-[12px] text-text-muted">{categories.length} 个</span>
                </div>
                <button onClick={refreshCategories} className="btn-ghost focus-ring h-8 px-3 flex items-center gap-1.5 text-[12px]">
                  <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> 刷新
                </button>
              </div>

              {loading ? (
                <div className="text-center py-20 text-text-muted text-[13px]">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                  加载类别中…
                </div>
              ) : categories.length === 0 ? (
                <div className="text-center py-20 border border-dashed border-border rounded-[12px]">
                  <Grid3x3 className="w-8 h-8 mx-auto mb-3 text-text-faint" strokeWidth={1.25} />
                  <p className="text-[13px] text-text-muted mb-4">暂无知识类别</p>
                  <button
                    onClick={() => setCreateCatOpen(true)}
                    className="btn-primary focus-ring h-9 px-4 inline-flex items-center gap-1.5 text-[13px]"
                  >
                    <Plus className="w-3.5 h-3.5" /> 新建第一个类别
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {categories.map((c) => (
                    <CategoryCard
                      key={c.name}
                      category={c}
                      onClick={() => openCategory(c.name)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {view === "category" && (
            <DocumentList
              domain={activeDomain}
              onBack={() => setView("grid")}
              onImport={() => setImportOpen(true)}
            />
          )}

          {view === "search" && <SearchPanel />}
        </div>
      </div>

      {importOpen && (
        <ImportModal
          domain={activeDomain || (categories[0]?.name ?? "")}
          categories={categories}
          onClose={() => setImportOpen(false)}
          onSuccess={() => {
            refreshCategories();
            if (view === "category") {
              const d = activeDomain;
              setView("grid");
              setTimeout(() => {
                setActiveDomain(d);
                setView("category");
              }, 0);
            }
          }}
        />
      )}

      {createCatOpen && (
        <CreateCategoryModal
          onClose={() => setCreateCatOpen(false)}
          onCreated={refreshCategories}
        />
      )}
    </div>
  );
}
