// 前端 API 层：公开接口 + 管理接口（服务端用 cookies() 转发 Cookie）。
// 同站部署时走 Next.js rewrites（/api/* -> FastAPI），本地开发走
// NEXT_PUBLIC_API_BASE_URL（默认 http://localhost:8000）。
export interface RankItem {
  slug: string;
  name: string;
  rank: number;
  heat_score: number;
  change_pct: number | null;
  up_ratio: number | null;
  turnover_rate: number | null; // 换手率(%)，不是成交额
  leading_company: string | null;
  leading_code: string | null;
  leading_change: number | null;
  up_count: number | null;
  down_count: number | null;
  limit_up_count: number | null;
  turnover_amount: number | null;
  // 主力净流入（亿元）：后端目前不返回该字段；只有当榜单 API 返回非 null
  // 时首页才渲染这一列，否则整列不渲染，绝不编数。
  main_net_inflow?: number | null;
  trend: number[];
  is_composite: boolean;
  snapshot_at: string | null;
}

export interface RankResponse {
  items: RankItem[];
  topics: RankItem[];
  styles: RankItem[];
  updated_at: string | null;
  stale: boolean;
  last_success_at: string | null;
  trade_date: string | null;
  fetched_at: string | null;
  market_status: string;
  stale_reason: string | null;
  heat_formula: string;
  source: string;
  note: string;
}

export interface LayerCompany {
  code: string | null;
  name: string | null;
  segment: string | null;
  layer: string;
  layer_reason: string | null;
  source_flags: Record<string, boolean> | null;
  main_products: string[] | null;
}

export interface TopicDetail {
  slug: string;
  name: string;
  description: string | null;
  rank: number | null;
  heat_score: number | null;
  change_pct: number | null;
  updated_at: string | null;
  concept_names: string[];
  overview: {
    definition: string;
    drivers: string[];
    policy: string;
    tech_trends: string[];
    market_size: { label: string; value: string; source: string }[];
    competition: string;
    chain: Record<string, string[]>;
  } | null;
  segments: Record<string, string[]>;
  companies: { core: LayerCompany[]; watch: LayerCompany[]; review: LayerCompany[] };
  industry_report: { id: string; status: string } | null;
  related_topics: { slug: string; name: string }[];
}

export interface CompanyDetail {
  code: string;
  name: string;
  industry: string | null;
  main_products: string[] | null;
  layers: {
    topic_slug: string | null;
    topic_name: string | null;
    segment: string | null;
    layer: string;
    layer_reason: string | null;
    source_flags: Record<string, boolean> | null;
    manual_override: boolean;
  }[];
  report: { id: string; status: string; content_md: string; report_html?: boolean } | null;
  has_deep_report: boolean;
  revenue_share: { product: string; share: number; report_date: string; source: string } | null;
  same_segment: { code: string; name: string; segment: string | null }[];
  evidence_note: string;
}

export interface ReportListItem {
  id: string;
  report_type: string;
  status: string;
  topic: { slug: string; name: string } | null;
  company: { code: string; name: string } | null;
  created_at: string | null;
  updated_at: string | null;
}

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function getJSON<T>(path: string, cookie?: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: cookie ? { Cookie: cookie } : {},
  });
  if (!res.ok) {
    throw new Error(`接口失败：${path} HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

// 爱发电创作者主页：全站唯一的付费/会员入口，一律外链（新标签页打开），
// 不做站内付费、不做服务端核验。
export const AFDIAN_URL = "https://afdian.com/a/978datacenter";

// ---- 大盘指数条：GET /api/market/overview（后端实现中）。
// 数字字段可能为 null；接口失败返回 null，由调用方展示“未获取”，绝不编数。 ----
export interface MarketIndex {
  name: string;
  code: string;
  value: number | null;
  change_pct: number | null;
}

export interface MarketOverview {
  trade_date: string | null;
  fetched_at: string | null;
  stale: boolean;
  indices: MarketIndex[];
  turnover_amount: number | null; // 两市成交额（亿元）
  turnover_change_pct: number | null; // 较昨日（%）
  up_count: number | null;
  down_count: number | null;
  limit_up_count: number | null;
  limit_down_count: number | null;
}

export async function fetchMarketOverview(): Promise<MarketOverview | null> {
  try {
    return await getJSON<MarketOverview>("/api/market/overview");
  } catch {
    return null;
  }
}

export async function fetchRank(): Promise<RankResponse> {
  return getJSON<RankResponse>("/api/topics/rank");
}

export async function fetchTopic(slug: string): Promise<TopicDetail> {
  return getJSON<TopicDetail>(`/api/topics/${slug}`);
}

export async function fetchCompany(code: string): Promise<CompanyDetail> {
  return getJSON<CompanyDetail>(`/api/companies/${code}`);
}

export async function fetchInstitutions(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return getJSON<{
    configured: boolean;
    note: string;
    weekly: { id: string; institution: string; title: string; type: string; language: string | null; frequency: string | null; url: string | null; keywords: string[] | null }[];
    digests: { id: string; institution: string; title: string; published_at: string | null; summary: string | null; source_url: string | null; keywords: string[] | null }[];
    sources: unknown[];
  }>(`/api/institutions${qs ? `?${qs}` : ""}`);
}

export async function fetchReports(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return getJSON<{ items: ReportListItem[] }>(`/api/reports${qs ? `?${qs}` : ""}`);
}

export async function fetchReportsAdmin(params: Record<string, string> = {}, cookie = "") {
  const qs = new URLSearchParams(params).toString();
  return getJSON<{ items: ReportListItem[] }>(`/api/reports${qs ? `?${qs}` : ""}`, cookie);
}

export async function fetchReport(id: string) {
  return getJSON<{
    id: string;
    report_type: string;
    status: string;
    topic: { slug: string; name: string } | null;
    company: { code: string; name: string } | null;
    content_md: string | null;
    evidence: Record<string, unknown> | null;
    created_at: string | null;
  }>(`/api/reports/${id}`);
}

export async function fetchSearch(q: string) {
  return getJSON<{
    q: string;
    topics: { slug: string; name: string }[];
    companies: { code: string; name: string }[];
    reports: { id: string; report_type: string; topic: string | null; company: string | null }[];
    institutions: { id: string; institution: string; title: string; type: string }[];
  }>(`/api/search?q=${encodeURIComponent(q)}`);
}

// ---- 管理接口（服务端调用，带 Cookie；401 时抛错由调用方转登录页） ----
export async function fetchAdmin<T>(path: string, cookie: string): Promise<T> {
  return getJSON<T>(path, cookie);
}
