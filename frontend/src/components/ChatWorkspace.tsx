"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  chatStream,
  getSession,
  getSessionMessages,
  listAgents,
  updateSession,
  type AgentInfo,
  type MessageInfo,
  type SSEEvent,
} from "@/lib/api";
import {
  Loader2,
  ArrowUp,
  Bot,
  User,
  Sparkles,
  BookOpen,
  Wrench,
  CheckCircle2,
  AlertCircle,
  ListChecks,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface StreamTag {
  id: string;
  type: string;
  data: Record<string, unknown>;
}

const TAG_CONFIG: Record<string, { label: string; icon: typeof Sparkles; cls: string }> = {
  intent_detected: {
    label: "意图识别",
    icon: Sparkles,
    cls: "bg-accent-dim text-accent border-accent/30",
  },
  plan_generated: {
    label: "任务规划",
    icon: ListChecks,
    cls: "bg-warning-dim text-warning border-warning/30",
  },
  retrieval_started: {
    label: "知识检索",
    icon: BookOpen,
    cls: "bg-bg-surface-2 text-text-dim border-border-bright",
  },
  tool_called: {
    label: "工具调用",
    icon: Wrench,
    cls: "bg-bg-surface-2 text-text-dim border-border-bright",
  },
  tool_result: {
    label: "工具结果",
    icon: CheckCircle2,
    cls: "bg-success-dim text-success border-success/30",
  },
  reflection: {
    label: "结果反思",
    icon: ListChecks,
    cls: "bg-warning-dim text-warning border-warning/30",
  },
  final_answer: {
    label: "最终回答",
    icon: Bot,
    cls: "bg-accent-dim text-accent border-accent/30",
  },
  error: {
    label: "错误",
    icon: AlertCircle,
    cls: "bg-danger-dim text-danger border-danger/30",
  },
};

export default function ChatWorkspace() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [streaming, setStreaming] = useState(false);
  const [streamTags, setStreamTags] = useState<StreamTag[]>([]);
  const [streamAnswer, setStreamAnswer] = useState("");
  const [resetTick, setResetTick] = useState(0);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listAgents().then(setAgents).catch(() => setAgents([]));
  }, []);

  const reset = useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
    setStreamTags([]);
    setStreamAnswer("");
    setInput("");
    setStreaming(false);
    setCurrentAgentId(null);
    setResetTick((t) => t + 1);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  // 加载已有会话的消息
  const loadSession = useCallback(async (sid: string) => {
    try {
      const [msgs, sess] = await Promise.all([
        getSessionMessages(sid),
        getSession(sid).catch(() => null),
      ]);
      setMessages(
        msgs
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m: MessageInfo) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
          })),
      );
      setSessionId(sid);
      setCurrentAgentId(sess?.agent_id ?? null);
      setStreamTags([]);
      setStreamAnswer("");
      setStreaming(false);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    const onNew = () => reset();
    const onActive = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      loadSession(detail);
    };
    window.addEventListener("domainforge:new-chat", onNew);
    window.addEventListener("domainforge:session-active", onActive);
    return () => {
      window.removeEventListener("domainforge:new-chat", onNew);
      window.removeEventListener("domainforge:session-active", onActive);
    };
  }, [reset, loadSession]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamAnswer]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [resetTick]);

  const handleSubmit = async () => {
    const query = input.trim();
    if (!query || streaming) return;

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: query };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    setStreamTags([]);
    setStreamAnswer("");

    let finalAnswer = "";

    try {
      await chatStream(query, sessionId, (event: SSEEvent) => {
        const tracked = [
          "intent_detected",
          "plan_generated",
          "retrieval_started",
          "tool_called",
          "tool_result",
          "reflection",
          "error",
        ];
        if (tracked.includes(event.event)) {
          setStreamTags((prev) => [
            ...prev,
            { id: crypto.randomUUID(), type: event.event, data: event.data },
          ]);
        } else if (event.event === "final_answer" && event.data.answer) {
          finalAnswer = event.data.answer as string;
          setStreamAnswer(finalAnswer);
        }
        if (event.data.session_id && !sessionId) {
          const sid = event.data.session_id as string;
          setSessionId(sid);
          window.dispatchEvent(
            new CustomEvent("domainforge:session-active", { detail: sid }),
          );
        }
      });
    } catch (err) {
      setStreamTags((prev) => [
        ...prev,
        { id: crypto.randomUUID(), type: "error", data: { message: String(err) } },
      ]);
    } finally {
      if (finalAnswer) {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", content: finalAnswer },
        ]);
      }
      setStreaming(false);
      setStreamAnswer("");
      inputRef.current?.focus();
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const hasContent = messages.length > 0 || streaming;

  return (
    <main className="flex-1 flex flex-col min-w-0 relative">
      <div className="absolute inset-0 grid-lines pointer-events-none opacity-40" />

      {/* Header */}
      <header className="relative h-[var(--header-h)] flex items-center justify-between px-6 border-b border-border bg-bg-elevated/80 backdrop-blur-md flex-shrink-0 z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent" />
            <h1 className="text-[14px] font-semibold text-text">
              {sessionId ? `会话 ${sessionId.slice(0, 8)}` : "新会话"}
            </h1>
          </div>
          {streaming && (
            <span className="text-[11px] text-accent bg-accent-dim px-2 py-0.5 rounded-full font-medium">
              处理中…
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-text-muted">
          <select
            className="rounded border border-border bg-bg-surface px-2 py-1 text-[12px] text-text focus-ring disabled:opacity-50"
            value={currentAgentId ?? ""}
            disabled={!sessionId || streaming}
            title={sessionId ? "切换智能体" : "新会话开始后再选择智能体"}
            onChange={async (e) => {
              if (!sessionId) return;
              const val = e.target.value || null;
              try {
                await updateSession(sessionId, { agent_id: val });
                setCurrentAgentId(val);
              } catch {
                // ignore
              }
            }}
          >
            <option value="">默认（无 agent）</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <span>{messages.filter((m) => m.role === "user").length} 条提问</span>
          <span className="text-border-bright">|</span>
          <span>{streaming ? "流式输出" : "空闲"}</span>
        </div>
      </header>

      {/* Messages */}
      <div className="relative flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          {!hasContent ? (
            <EmptyState />
          ) : (
            <div className="space-y-6">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              {streaming && <StreamingBubble tags={streamTags} answer={streamAnswer} />}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="relative flex-shrink-0 border-t border-border bg-bg-elevated/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="relative flex items-end gap-2 p-2 card focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--accent-glow)] transition-all duration-150">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder={streaming ? "Agent 正在处理…" : "输入问题，Enter 发送 · Shift+Enter 换行"}
              rows={1}
              disabled={streaming}
              className="focus-ring flex-1 resize-none bg-transparent text-text placeholder:text-text-faint text-[14px] leading-6 disabled:opacity-50 disabled:cursor-not-allowed py-2 px-1 outline-none"
              style={{ maxHeight: "120px" }}
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || streaming}
              aria-label="发送"
              className="btn-primary focus-ring flex-shrink-0 w-10 h-10 grid place-items-center disabled:hover:shadow-none"
            >
              {streaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
              )}
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-text-faint">
            <span>{streaming ? "运行中" : "就绪"}</span>
            <span>{input.length} 字</span>
          </div>
        </div>
      </div>
    </main>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] fade-up">
      <div className="relative w-16 h-16 grid place-items-center mb-6">
        <div className="absolute inset-0 rounded-2xl bg-accent-dim border border-accent/20" />
        <Sparkles className="w-7 h-7 text-accent" strokeWidth={1.75} />
      </div>

      <h1 className="text-[24px] font-semibold text-text mb-2">DomainForge</h1>
      <p className="text-[13px] text-text-muted mb-10">
        领域定制智能对话 · 知识检索 · 工具调用 · 反思纠错
      </p>

      <div className="grid grid-cols-3 gap-3 mb-10 max-w-md w-full">
        {[
          { k: "意图识别", v: "Intent" },
          { k: "知识检索", v: "Retrieve" },
          { k: "工具调用", v: "Tool" },
          { k: "会话记忆", v: "Memory" },
          { k: "结果反思", v: "Reflect" },
          { k: "流式输出", v: "Stream" },
        ].map((c) => (
          <div key={c.k} className="card px-3 py-2.5 text-center">
            <div className="text-[10px] text-text-faint uppercase tracking-wider font-medium">
              {c.v}
            </div>
            <div className="text-[12px] text-text-dim mt-1 font-medium">{c.k}</div>
          </div>
        ))}
      </div>

      <p className="text-[12px] text-text-faint">在下方输入框开始一次新会话</p>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex gap-3 fade-up ${isUser ? "justify-end" : ""}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 grid place-items-center rounded-full bg-accent-dim border border-accent/20">
          <Bot className="w-4 h-4 text-accent" strokeWidth={1.75} />
        </div>
      )}
      <div
        className={`max-w-[80%] px-4 py-3 text-[14px] leading-relaxed rounded-[12px] shadow-sm
          ${isUser
            ? "bg-accent text-white rounded-tr-sm"
            : "bg-bg-surface border border-border text-text rounded-tl-sm"}`}
      >
        <div
          className={`text-[10px] tracking-wider uppercase mb-1.5 font-medium
            ${isUser ? "text-white/70" : "text-text-faint"}`}
        >
          {isUser ? "用户" : "助手"}
        </div>
        <div className="break-words">
          {isUser ? (
            <div className="whitespace-pre-wrap">{msg.content}</div>
          ) : (
            <div className="md-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 grid place-items-center rounded-full bg-bg-surface-2 border border-border">
          <User className="w-4 h-4 text-text-dim" strokeWidth={1.75} />
        </div>
      )}
    </div>
  );
}

function StreamingBubble({ tags, answer }: { tags: StreamTag[]; answer: string }) {
  return (
    <div className="space-y-3 fade-in">
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => {
            const config = TAG_CONFIG[tag.type] || TAG_CONFIG.error;
            const Icon = config.icon;
            return (
              <span
                key={tag.id}
                className={`tag-in inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] rounded-full border font-medium ${config.cls}`}
              >
                <Icon className="w-3 h-3" strokeWidth={2} />
                {config.label}
                {tag.type === "tool_called" && tag.data.tool ? (
                  <span className="opacity-70">·{String(tag.data.tool)}</span>
                ) : null}
              </span>
            );
          })}
        </div>
      )}

      <div className="flex gap-3">
        <div className="flex-shrink-0 w-8 h-8 grid place-items-center rounded-full bg-accent-dim border border-accent/20">
          <Bot className="w-4 h-4 text-accent pulse-dot" strokeWidth={1.75} />
        </div>
        <div className="max-w-[80%] px-4 py-3 text-[14px] leading-relaxed rounded-[12px] rounded-tl-sm bg-bg-surface border border-border text-text shadow-sm">
          <div className="text-[10px] tracking-wider uppercase mb-1.5 text-accent font-medium">
            助手 · 实时
          </div>
          {answer ? (
            <div className="md-body break-words">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 py-0.5">
              <span className="typing-dot w-1.5 h-1.5 rounded-full bg-accent" />
              <span className="typing-dot w-1.5 h-1.5 rounded-full bg-accent" />
              <span className="typing-dot w-1.5 h-1.5 rounded-full bg-accent" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
