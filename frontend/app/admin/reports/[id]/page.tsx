export const runtime = "edge";

import Link from "next/link";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { requireAdminPage } from "../../../../lib/admin-guard";
import { fetchAdmin } from "../../../../lib/api";
import { Markdown } from "../../../../lib/md";

// 后台报告详情 /admin/reports/[id]：管理员读全文（含 pending 报告），用于审核。
// 公开端 GET /api/reports/{id} 只返回 done 的报告，所以这里走
// GET /api/admin/reports/{id}（带 admin_session），渲染逻辑与公开详情页一致。
export default async function AdminReportDetailPage({ params }: { params: { id: string } }) {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  type Report = {
    id: string;
    report_type: string;
    status: string;
    topic: { slug: string; name: string } | null;
    company: { code: string; name: string } | null;
    content_md: string | null;
    evidence: Record<string, unknown> | null;
    created_at: string | null;
  };
  let report: Report | null = null;
  try {
    report = await fetchAdmin<Report>(`/api/admin/reports/${params.id}`, cookie);
  } catch {
    notFound();
  }
  if (!report) notFound();
  const html = report.evidence?.report_html;
  return (
    <>
      <p className="muted">
        <Link href="/admin/reports">← 报告审核</Link>
      </p>
      <h1>
        {report.topic?.name ?? report.company?.name ?? "报告"}
        {report.company ? ` · ${report.company.name}` : ""}
      </h1>
      <p className="muted">
        类型：{report.report_type === "industry" ? "行业报告" : "公司报告"} · 状态：{report.status} ·{" "}
        {report.created_at ?? ""}
      </p>
      {html ? (
        <>
          {(() => {
            const s = report.evidence?.stockreport_summary as Record<string, unknown> | undefined;
            if (!s) return null;
            const gm = typeof s.gm === "number" ? `${Math.round(s.gm * 1000) / 10}%` : "—";
            const cf = typeof s.critical_fail === "number" ? s.critical_fail : 0;
            return (
              <>
                {cf > 0 ? (
                  <p style={{ color: "#b91c1c", fontWeight: 700 }}>
                    ⚠ 注意：本报告关键校验未通过（{cf} 项），数字与结论需仔细复核后再审核。
                  </p>
                ) : null}
                <p className="muted">
                  stockreport 摘要：{String(s.label ?? "—")} · 归母{" "}
                  {s.np != null ? `${s.np} 亿` : "—"} · 毛利率 {gm}
                </p>
              </>
            );
          })()}
          <iframe
            srcDoc={String(html)}
            sandbox=""
            title="公司深度报告"
            style={{ width: "100%", height: "85vh", minHeight: "600px", border: "1px solid #ddd" }}
          />
        </>
      ) : report.content_md ? (
        <Markdown text={report.content_md} />
      ) : (
        <p className="muted">报告暂无内容。</p>
      )}
    </>
  );
}
