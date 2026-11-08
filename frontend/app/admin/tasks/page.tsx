
export const runtime = "edge";

import Link from "next/link";
import { cookies } from "next/headers";
import { requireAdminPage } from "../../../lib/admin-guard";
import { fetchAdmin } from "../../../lib/api";
import { ActionButton } from "../../../components/admin-actions";

// 后台任务监控 /admin/tasks：任务列表 + 重试 + SSE 进度流链接。
export default async function AdminTasks() {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const data = await fetchAdmin<{
    items: { id: string; kind: string; status: string; progress: number | null; error: string | null; created_at: string | null }[];
  }>("/api/admin/tasks", cookie);
  return (
    <>
      <h1>任务监控</h1>
      {data.items.length === 0 ? (
        <p className="muted">暂无任务。</p>
      ) : (
        <table>
          <thead><tr><th>任务</th><th>状态</th><th>进度</th><th>错误</th><th>操作</th></tr></thead>
          <tbody>
            {data.items.map((t) => (
              <tr key={t.id}>
                <td>{t.kind}<br /><span className="muted">{t.created_at ?? ""}</span></td>
                <td>{t.status}</td>
                <td>{t.progress == null ? "—" : `${t.progress}%`}</td>
                <td className="muted">{t.error ?? "—"}</td>
                <td>
                  <Link href={`/api/tasks/${t.id}/stream`}>进度流</Link>
                  {" · "}
                  <ActionButton label="重试" path={`/api/admin/tasks/${t.id}/retry`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
