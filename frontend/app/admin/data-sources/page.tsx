
export const runtime = "edge";

import { cookies } from "next/headers";
import { requireAdminPage } from "../../../lib/admin-guard";
import { fetchAdmin } from "../../../lib/api";

// 后台数据源管理 /admin/data-sources：各数据源状态与说明。
export default async function AdminDataSources() {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const data = await fetchAdmin<{
    akshare_concept_board: { status: string; note: string; last_success_at: string | null };
    lazy_graph: { status: string; note: string };
    research_digest: { status: string; note: string };
    counts: Record<string, number>;
  }>("/api/admin/data-sources", cookie);
  const rows: [string, { status: string; note: string }][] = [
    ["AKShare 概念板块", data.akshare_concept_board],
    ["懒图谱", data.lazy_graph],
    ["研报摘要源", data.research_digest],
  ];
  return (
    <>
      <h1>数据源管理</h1>
      {rows.map(([name, s]) => (
        <div className="card" key={name}>
          <p><strong>{name}</strong>：{s.status}</p>
          <p className="muted">{s.note}</p>
        </div>
      ))}
      <p className="muted">
        数量：题材 {data.counts.topics} · 公司 {data.counts.companies} · 分层 {data.counts.layers} ·
        报告 {data.counts.reports} · 任务 {data.counts.tasks}。主力净流入接口未验证通过，未接入；
        研报摘要源需 Tushare token，尚未配置。
      </p>
    </>
  );
}
