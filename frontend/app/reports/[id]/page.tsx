
export const runtime = "edge";

import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchReport } from "../../../lib/api";
import { Markdown } from "../../../lib/md";

// 报告详情页：Markdown 阅读 + 下载。
export default async function ReportDetailPage({ params }: { params: { id: string } }) {
  let report: Awaited<ReturnType<typeof fetchReport>> | null = null;
  try {
    report = await fetchReport(params.id);
  } catch {
    notFound();
  }
  if (!report) notFound();
  return (
    <>
      <p className="muted">
        <Link href="/reports">← 报告中心</Link>
      </p>
      <h1>
        {report.topic?.name ?? report.company?.name ?? "报告"}
        {report.company ? ` · ${report.company.name}` : ""}
      </h1>
      <p className="muted">
        类型：{report.report_type === "industry" ? "行业报告" : "公司报告"} · 状态：{report.status} ·{" "}
        {report.created_at ?? ""}
        {!(report.evidence as Record<string, unknown> | null)?.report_html ? (
          <>
            {" · "}
            <a href={`/api/reports/${report.id}/download`}>下载 Markdown</a>
          </>
        ) : null}
      </p>
      {(report.evidence as Record<string, unknown> | null)?.report_html ? (
        <>
          {(() => {
            const s = (report.evidence as Record<string, unknown>).stockreport_summary as
              | Record<string, unknown>
              | undefined;
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
          {/* stockreport 报告是完整 HTML（含内联样式与 SVG 图表、无脚本）：
              前端 Markdown 渲染器不渲染 HTML，改用无脚本沙箱 iframe 展示。
              sandbox 不给 allow-scripts/allow-same-origin：HTML 无脚本也能正常显示，
              且 iframe 内容无法触及本站页面。
              高度无法按内容自适应——无脚本的沙箱 iframe 无法向父页面报高度，
              父页面也读不到它的 contentDocument；因此用视口相对高度（85vh，
              下限 600px），内容在框内滚动。 */}
          <iframe
            srcDoc={String((report.evidence as Record<string, unknown>).report_html)}
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
      {report.evidence &&
      ((report.evidence as Record<string, unknown>).review_score != null ||
        (report.evidence as Record<string, unknown>).rewrites != null) ? (
        <p className="muted">
          审核：评分 {String((report.evidence as Record<string, unknown>).review_score ?? "—")}
          ；重写次数 {String((report.evidence as Record<string, unknown>).rewrites ?? 0)}
        </p>
      ) : null}
    </>
  );
}
