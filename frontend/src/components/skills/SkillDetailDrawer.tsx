"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { X, Trash2, Package, User, Tag, Calendar, FileCode } from "lucide-react";
import {
  getInstalledSkill,
  getMarketplaceSkill,
  uninstallSkill,
  setSkillEnabled,
  type InstalledSkill,
  type SkillDetail,
  type SkillPackageInfo,
} from "@/lib/api";

type Mode = "installed" | "marketplace";

interface Props {
  mode: Mode;
  identifier: string; // installed: name; marketplace: skill_id
  open: boolean;
  onClose: () => void;
  onChanged?: () => void; // 安装/卸载/enable 变化后通知父刷新
}

export function SkillDetailDrawer({ mode, identifier, open, onClose, onChanged }: Props) {
  const [installed, setInstalled] = useState<InstalledSkill | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [pkg, setPkg] = useState<SkillPackageInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError("");
    setInstalled(null);
    setDetail(null);
    setPkg(null);
    setConfirmingDelete(false);
    (mode === "installed"
      ? getInstalledSkill(identifier)
      : getMarketplaceSkill(identifier)
    )
      .then((d) => {
        if (mode === "installed") {
          setInstalled(d as InstalledSkill);
          setDetail(d as SkillDetail);
        } else {
          setPkg(d as SkillPackageInfo);
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [open, mode, identifier]);

  async function handleDelete() {
    if (!installed) return;
    try {
      await uninstallSkill(installed.name);
      onChanged?.();
      onClose();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleToggleEnabled(next: boolean) {
    if (!installed) return;
    try {
      const updated = await setSkillEnabled(installed.name, next);
      setInstalled(updated);
      onChanged?.();
    } catch (e) {
      setError(String(e));
    }
  }

  if (!open) return null;

  const name = installed?.name ?? pkg?.name ?? "";
  const description = installed?.description ?? pkg?.description ?? "";
  const version = installed?.version ?? pkg?.version ?? "";
  const author = installed?.author ?? pkg?.author ?? "";
  const license = installed?.license ?? pkg?.license ?? "";
  const body = detail?.body_md ?? pkg?.body_preview ?? "";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-bg-elevated border-l border-border h-full overflow-y-auto shadow-xl">
        <div className="sticky top-0 bg-bg-elevated/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold text-text truncate">{name}</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5">
          {loading && <div className="text-text-muted text-[13px]">加载中…</div>}
          {error && (
            <div className="text-danger text-[12px] mb-3">{error}</div>
          )}

          {!loading && (
            <>
              <p className="text-[13px] text-text-muted mb-4 leading-relaxed">{description}</p>

              <div className="grid grid-cols-2 gap-3 mb-5 text-[12px]">
                <Meta icon={<Tag className="w-3 h-3" />} label="版本" value={version || "-"} />
                <Meta icon={<User className="w-3 h-3" />} label="作者" value={author || "-"} />
                <Meta icon={<Package className="w-3 h-3" />} label="许可证" value={license || "-"} />
                {installed && (
                  <Meta
                    icon={<Calendar className="w-3 h-3" />}
                    label="安装于"
                    value={installed.installed_at ? new Date(installed.installed_at).toLocaleString() : "-"}
                  />
                )}
              </div>

              {installed && (
                <div className="flex items-center gap-4 mb-5 pb-4 border-b border-border">
                  <label className="flex items-center gap-2 text-[12px] text-text-muted cursor-pointer">
                    <input
                      type="checkbox"
                      checked={installed.enabled}
                      onChange={(e) => handleToggleEnabled(e.target.checked)}
                      className="accent-[#2563EB]"
                    />
                    启用（注入对话上下文）
                  </label>
                </div>
              )}

              <h3 className="text-[12px] font-semibold text-text mb-2">SKILL.md 正文</h3>
              <div className="prose prose-sm max-w-none text-text-muted mb-5">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
              </div>

              {detail && detail.files.length > 0 && (
                <>
                  <h3 className="text-[12px] font-semibold text-text mb-2 flex items-center gap-1">
                    <FileCode className="w-3 h-3" /> 文件
                  </h3>
                  <ul className="text-[11px] font-mono text-text-faint mb-5 space-y-1">
                    {detail.files.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </>
              )}

              {installed && (
                <div className="pt-4 border-t border-border">
                  {confirmingDelete ? (
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] text-danger">确认卸载？</span>
                      <button
                        onClick={handleDelete}
                        className="text-[12px] px-3 py-1 rounded-[6px] bg-danger text-white hover:opacity-90"
                      >
                        确认卸载
                      </button>
                      <button
                        onClick={() => setConfirmingDelete(false)}
                        className="text-[12px] px-3 py-1 rounded-[6px] border border-border text-text-muted"
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmingDelete(true)}
                      className="flex items-center gap-1 text-[12px] text-danger hover:opacity-80"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> 卸载 Skill
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Meta({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-text-faint">{icon}</span>
      <span className="text-text-faint">{label}:</span>
      <span className="text-text truncate">{value}</span>
    </div>
  );
}
