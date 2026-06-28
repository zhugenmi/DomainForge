const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export interface ChatStreamRequest {
  query: string;
  session_id?: string;
  agent_id?: string | null;
  web_search?: boolean;
  deep_think?: boolean;
  attachment_ids?: string[];
  model_name?: string;
}

export interface ChatRequest {
  query: string;
  session_id?: string;
  agent_id?: string | null;
  web_search?: boolean;
  deep_think?: boolean;
  attachment_ids?: string[];
  model_name?: string;
}

export interface ChatModelsInfo {
  default: string;
  models: string[];
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  intent?: string;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface DocumentUpload {
  domain: string;
  title: string;
  content: string;
  source?: string;
}

export interface ChunkResult {
  id: string;
  document_id: string;
  content: string;
  metadata: Record<string, unknown>;
  score?: number;
}

export interface SearchResponse {
  results: ChunkResult[];
}

export interface SessionInfo {
  id: string;
  user_id: string;
  title: string;
  created_at: string | null;
  agent_id?: string | null;
}

export interface Citation {
  index: number;
  title: string;
  chapter?: string;
  locator: string;
  snippet: string;
  document_id: string;
  chunk_id: string;
}

export interface MessageInfo {
  id: string;
  role: string;
  content: string;
  created_at: string | null;
  citations?: Citation[] | null;
}

export interface AuditEntry {
  id: string;
  trace_id: string;
  action: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface EvalResultEntry {
  id: string;
  dataset_name: string;
  metric: string;
  score: number;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  permission_scope: string;
  timeout: number;
  parameters: Array<{
    name: string;
    type: string;
    description: string;
    required: boolean;
    default?: unknown;
  }>;
}

export interface MetricsSnapshot {
  counters: Record<string, number>;
  timers: Record<string, {
    count: number;
    avg_ms: number;
    p50_ms: number;
    max_ms: number;
  }>;
}

async function getJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export async function chat(req: ChatRequest): Promise<ChatResponse> {
  return getJSON<ChatResponse>(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function chatStream(
  req: ChatStreamRequest,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Stream request failed: ${res.status}`);

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No reader available");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const match = line.match(/^data:\s*(.+)$/m);
      if (match) {
        try {
          const event: SSEEvent = JSON.parse(match[1]);
          onEvent(event);
        } catch {
          // skip malformed
        }
      }
    }
  }
}

export interface AttachmentPreview {
  filename: string;
  size: number;
  chars: number;
}

export async function uploadChatAttachments(
  files: File[],
): Promise<{ attachment_ids: string[]; previews: AttachmentPreview[] }> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const res = await fetch(`${API_BASE}/chat/uploads`, { method: "POST", body: fd });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Upload failed: ${res.status} ${detail}`);
  }
  return res.json();
}

export async function indexDocument(
  doc: DocumentUpload,
): Promise<{ document_id: string; chunks: number }> {
  return getJSON(`${API_BASE}/knowledge/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
}

export async function searchKnowledge(
  query: string,
  topK = 5,
  mode = "hybrid",
): Promise<SearchResponse> {
  const url = `${API_BASE}/knowledge/search?query=${encodeURIComponent(query)}&top_k=${topK}&mode=${mode}`;
  return getJSON<SearchResponse>(url);
}

// ---- 知识库重构：类别 / 文档 / 两阶段导入 ----

export interface CategoryStats {
  name: string;
  is_builtin: boolean;
  file_count: number;
  word_count: number;
  last_updated: string | null;
}

export interface DocumentInfo {
  id: string;
  domain: string;
  title: string;
  source: string;
  file_type: string | null;
  file_size_bytes: number | null;
  word_count: number | null;
  chunk_count: number | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface FilePreview {
  filename: string;
  file_type: string;
  file_size_bytes: number;
  char_count: number;
  word_count: number;
  chunk_count: number;
  sample_chunks: string[];
}

export interface PreviewSession {
  session_id: string;
  domain: string;
  chunk_strategy: string;
  chunk_size: number;
  chunk_overlap: number;
  embedding_dimension: number;
  expires_in: number;
  files: FilePreview[];
}

export async function listCategories(): Promise<CategoryStats[]> {
  return getJSON<CategoryStats[]>(`${API_BASE}/knowledge/categories`);
}

export async function listDocuments(domain: string): Promise<DocumentInfo[]> {
  return getJSON<DocumentInfo[]>(
    `${API_BASE}/knowledge/categories/${encodeURIComponent(domain)}/documents`,
  );
}

export async function createCategory(
  name: string,
): Promise<{ id: string; name: string; is_builtin: boolean }> {
  return getJSON(`${API_BASE}/knowledge/categories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function uploadFiles(
  files: File[],
  domain: string,
  strategy: string,
  chunkSize: number,
  chunkOverlap: number,
): Promise<PreviewSession> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("domain", domain);
  fd.append("chunk_strategy", strategy);
  fd.append("chunk_size", String(chunkSize));
  fd.append("chunk_overlap", String(chunkOverlap));
  const res = await fetch(`${API_BASE}/knowledge/upload`, { method: "POST", body: fd });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Upload failed: ${res.status} ${detail}`);
  }
  return res.json();
}

export interface ImportJobStatus {
  job_id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  total_files: number;
  processed_files: number;
  total_chunks: number;
  processed_chunks: number;
  document_ids: string[];
  error: string | null;
}

export async function confirmImport(
  sessionId: string,
): Promise<{ job_id: string; status: string }> {
  return getJSON(`${API_BASE}/knowledge/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function getImportStatus(jobId: string): Promise<ImportJobStatus> {
  return getJSON<ImportJobStatus>(`${API_BASE}/knowledge/import/${jobId}/status`);
}

export async function deleteDocument(id: string): Promise<{ deleted: string }> {
  return getJSON<{ deleted: string }>(`${API_BASE}/knowledge/documents/${id}`, {
    method: "DELETE",
  });
}

export async function healthCheck(): Promise<{ status: string }> {
  return getJSON(`${API_BASE}/health`);
}

export async function listSessions(): Promise<SessionInfo[]> {
  return getJSON<SessionInfo[]>(`${API_BASE}/sessions`);
}

export async function getSession(sessionId: string): Promise<SessionInfo> {
  return getJSON<SessionInfo>(`${API_BASE}/sessions/${sessionId}`);
}

export async function getSessionMessages(sessionId: string): Promise<MessageInfo[]> {
  return getJSON<MessageInfo[]>(`${API_BASE}/sessions/${sessionId}/messages`);
}

export async function deleteSession(sessionId: string): Promise<{ deleted: string }> {
  return getJSON<{ deleted: string }>(`${API_BASE}/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function listAudit(limit = 50): Promise<AuditEntry[]> {
  return getJSON<AuditEntry[]>(`${API_BASE}/audit?limit=${limit}`);
}

export async function getAuditTrace(traceId: string): Promise<AuditEntry[]> {
  return getJSON<AuditEntry[]>(`${API_BASE}/audit/${traceId}`);
}

export async function runEvals(dataset: string): Promise<{
  dataset: string;
  total: number;
  results: Array<{
    case_id: string;
    correctness: number;
    groundedness: number;
    retrieval_recall: number;
    context_precision: number;
    latency_ms: number;
  }>;
}> {
  return getJSON(`${API_BASE}/evals/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset }),
  });
}

export async function listEvalResults(dataset?: string): Promise<EvalResultEntry[]> {
  const q = dataset ? `?dataset=${encodeURIComponent(dataset)}` : "";
  return getJSON<EvalResultEntry[]>(`${API_BASE}/evals/results${q}`);
}

export async function listTools(): Promise<ToolInfo[]> {
  return getJSON<ToolInfo[]>(`${API_BASE}/admin/tools`);
}

export async function getMetrics(): Promise<MetricsSnapshot> {
  return getJSON<MetricsSnapshot>(`${API_BASE}/admin/metrics`);
}

// ---------- Agents ----------

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  model_name: string;
  temperature: number;
  domain: string | null;
  is_builtin: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentCreateInput {
  name: string;
  description?: string;
  system_prompt?: string;
  model_name: string;
  temperature?: number;
  domain?: string | null;
}

export interface AgentUpdateInput {
  name?: string;
  description?: string;
  system_prompt?: string;
  model_name?: string;
  temperature?: number;
  domain?: string | null;
}

export async function listAgents(): Promise<AgentInfo[]> {
  return getJSON<AgentInfo[]>(`${API_BASE}/agents`);
}

export async function listAgentModels(): Promise<string[]> {
  return getJSON<string[]>(`${API_BASE}/agents/models`);
}

export async function listChatModels(): Promise<ChatModelsInfo> {
  return getJSON<ChatModelsInfo>(`${API_BASE}/chat/models`);
}

export async function getAgent(id: string): Promise<AgentInfo> {
  return getJSON<AgentInfo>(`${API_BASE}/agents/${id}`);
}

export async function createAgent(input: AgentCreateInput): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error((await res.text()) || "createAgent failed");
  return res.json();
}

export async function updateAgent(id: string, input: AgentUpdateInput): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error((await res.text()) || "updateAgent failed");
  return res.json();
}

export async function deleteAgent(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/agents/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error("deleteAgent failed");
}

// ---------- Session agent binding ----------

export interface SessionUpdateInput {
  agent_id?: string | null;
}

export async function updateSession(id: string, input: SessionUpdateInput): Promise<SessionInfo> {
  const res = await fetch(`${API_BASE}/sessions/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error((await res.text()) || "updateSession failed");
  return res.json();
}

export async function createSessionWithAgent(agentId: string | null): Promise<SessionInfo> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId }),
  });
  if (!res.ok) throw new Error("createSession failed");
  return res.json();
}
