
export const runtime = "edge";

import Link from "next/link";
import { cookies } from "next/headers";
import { requireAdminPage } from "../../lib/admin-guard";
import { fetchAdmin } from "../../lib/api";

// 后台总览 /admin（骨架 v2）：系统状态 + 快捷入口。
export default async function AdminOverview() {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const [sources, tasks, reports] = await Promise.all([
    fetchAdmin<{
      akshare_concept_board: { status: string; note: string };
      lazy_graph: { status: string; note: string };
      research_digest: { status: string; note: string };
    }>("/api/admin/data-sources", cookie).catch(() => null),
    fetchAdmin<{ items: { status: string }[] }>("/api/admin/tasks", cookie).catch(() => null),
    fetchAdmin<{ items: { status: string }[] }>("/api/reports", cookie).catch(() => null),
  ]);
  const taskRunning = tasks?.items.filter((t) => t.status === "running").length ?? 0;
  const taskDone = tasks?.items.filter((t) => t.status === "done").length ?? 0;
  const reportDone = reports?.items.filter((r) => r.status === "done").length ?? 0;
  const sourceRows: [string, string][] = sources
    ? [
        ["AKShare 概念板块", sources.akshare_concept_board.status],
        ["懒图谱", sources.lazy_graph.status],
        ["研报摘要源", sources.research_digest.status],
      ]
    : [];
  return (
    <>
      <h1>后台总览</h1>
      <p className="muted">
        任务：运行中 {taskRunning} · 已完成 {taskDone} ｜ 报告：已完成 {reportDone} ｜
        数据源：{sourceRows.length || "—"} 个
      </p>
      <div className="card">
        <h2>数据源状态</h2>
        {sourceRows.length > 0 ? (
          sourceRows.map(([name, status]) => (
            <p key={name}>
              {name}：{status}
            </p>
          ))
        ) : (
          <p className="muted">未获取</p>
        )}
      </div>
      <div className="card">
        <h2>快捷入口</h2>
        <p>
          <Link href="/admin/tasks">任务监控</Link> ·{" "}
          <Link href="/admin/data-sources">数据源管理</Link> ·{" "}
          <Link href="/admin/topic-mapping">题材归并</Link> ·{" "}
          <Link href="/admin/layering">分层校准</Link> ·{" "}
          <Link href="/admin/institutions">机构源管理</Link> ·{" "}
          <Link href="/admin/reports">报告审核</Link>
        </p>
      </div>
    </>
  );
}
