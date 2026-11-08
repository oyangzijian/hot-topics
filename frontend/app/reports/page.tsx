
export const runtime = "edge";

import Link from "next/link";
import { fetchReports } from "../../lib/api";
import { ActionButton, DeleteButton } from "../../components/admin-actions";

// 报告中心页（骨架 v3 §报告中心页，2 个单元）：
// 1 筛选区（状态、类型、时间）→ 2 报告列表（题材/公司名、类型、状态、
// 时间、操作：查看/下载/重新生成/删除）。重新生成与删除是管理操作，
// 未登录时按钮会返回 401 提示；已登录管理员可直接操作。
export default async function ReportsPage({
  searchParams,
}: {
  searchParams: { status?: string; type?: string; since?: string };
}) {
  const data = await fetchReports({
    ...(searchParams.status ? { status: searchParams.status } : {}),
    ...(searchParams.type ? { type: searchParams.type } : {}),
    ...(searchParams.since ? { since: searchParams.since } : {}),
  }).catch(() => null);
  const base = (over: Record<string, string>) => {
    const p = new URLSearchParams({ ...searchParams, ...over });
    return `/reports?${p.toString()}`;
  };

  return (
    <>
      <h1>报告中心</h1>
      <p>
        状态：
        <Link href="/reports"> 全部</Link>
        {" · "}
        <Link href={base({ status: "done" })}>已完成</Link>
        {" · "}
        <Link href={base({ status: "running" })}>生成中</Link>
        {" · "}
        <Link href={base({ status: "failed" })}>失败</Link>
        {" · "}
        类型：
        <Link href={base({ type: "industry" })}>行业报告</Link>
        {" · "}
        <Link href={base({ type: "company" })}>公司报告</Link>
      </p>
      <form method="get" action="/reports">
        {searchParams.status ? <input type="hidden" name="status" value={searchParams.status} /> : null}
        {searchParams.type ? <input type="hidden" name="type" value={searchParams.type} /> : null}
        <label>
          时间（自）：<input type="date" name="since" defaultValue={searchParams.since ?? ""} />
        </label>{" "}
        <button type="submit">筛选</button>
      </form>
      {!data ? (
        <p className="muted">报告接口暂不可用：请确认后端已启动。</p>
      ) : data.items.length === 0 ? (
        <p className="muted">暂无报告。</p>
      ) : (
        <table>
          <thead>
            <tr><th>报告</th><th>类型</th><th>状态</th><th>时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.topic?.name ?? r.company?.name ?? "—"}
                  {r.company ? ` · ${r.company.name}` : ""}
                </td>
                <td>{r.report_type === "industry" ? "行业报告" : "公司报告"}</td>
                <td>{r.status}</td>
                <td className="muted">{r.created_at ?? "—"}</td>
                <td>
                  <Link href={`/reports/${r.id}`}>查看</Link>
                  {" · "}
                  <a href={`/api/reports/${r.id}/download`}>下载</a>
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
