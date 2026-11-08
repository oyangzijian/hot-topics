
export const runtime = "edge";

import Link from "next/link";
import { cookies } from "next/headers";
import { requireAdminPage } from "../../../lib/admin-guard";
import { fetchAdmin } from "../../../lib/api";
import { ActionButton, DeleteButton } from "../../../components/admin-actions";

// 后台报告审核 /admin/reports：审核通过/驳回 + 重新生成/删除。
// 取数走 /api/admin/reports（不是公开 /api/reports）：要 evidence 里的
// stockreport 摘要和 needs_attention 高亮标记（critical_fail > 0 或报告顶部
// 有红色“关键校验未通过”横幅时置真，提醒审核人不要直接通过）。
export default async function AdminReports() {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const data = await fetchAdmin<{
    items: {
      id: string;
      report_type: string;
      status: string;
      topic: string | null;
      company: string | null;
      has_html_report?: boolean;
      needs_attention?: boolean;
      created_at: string | null;
    }[];
  }>("/api/admin/reports", cookie);
  return (
    <>
      <h1>报告审核</h1>
      <p className="muted">审核硬规则：报告中公司必须在输入清单或图谱中找到，不得引入清单外公司作核心标的；不虚构财务数据，缺失写“未获取”。</p>
      <p className="muted">标红“⚠ 关键校验未通过”的报告：stockreport 关键校验失败，数字与结论必须逐项复核，确认无误后才能通过。</p>
      {data.items.length === 0 ? (
        <p className="muted">暂无报告。</p>
      ) : (
        <table>
          <thead><tr><th>报告</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link href={`/admin/reports/${r.id}`}>{r.topic ?? r.company ?? "—"}</Link>
                  {r.company ? ` · ${r.company}` : ""}
                  {r.has_html_report ? " · HTML" : ""}
                  {r.needs_attention ? (
                    <span style={{ color: "#b91c1c", fontWeight: 700 }}> ⚠ 关键校验未通过</span>
                  ) : null}
                </td>
                <td>{r.report_type === "industry" ? "行业报告" : "公司报告"}</td>
                <td>{r.status}</td>
                <td>
                  <ActionButton label="通过" path={`/api/admin/reports/${r.id}/review`} body={{ action: "approve" }} />
                  {" · "}
                  <ActionButton label="驳回" path={`/api/admin/reports/${r.id}/review`} body={{ action: "reject" }} />
                  {" · "}
                  <ActionButton label="重新生成" path={`/api/admin/reports/${r.id}/regenerate`} />
                  {" · "}
                  <DeleteButton label="删除" path={`/api/admin/reports/${r.id}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
