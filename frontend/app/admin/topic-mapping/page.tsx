
export const runtime = "edge";

import { cookies } from "next/headers";
import { requireAdminPage } from "../../../lib/admin-guard";
import { fetchAdmin } from "../../../lib/api";
import { DeleteButton } from "../../../components/admin-actions";
import { MappingForm } from "../../../components/admin-forms";

// 后台题材归并 /admin/topic-mapping：题材 ↔ 概念板块映射维护。
export default async function AdminTopicMapping() {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const data = await fetchAdmin<{
    items: { id: string; topic_slug: string; concept_name: string; weight: number }[];
  }>("/api/admin/topic-mapping", cookie);
  return (
    <>
      <h1>题材归并</h1>
      <MappingForm />
      {data.items.length === 0 ? (
        <p className="muted">暂无映射。</p>
      ) : (
        <table>
          <thead><tr><th>题材</th><th>概念板块</th><th>权重</th><th>操作</th></tr></thead>
          <tbody>
            {data.items.map((m) => (
              <tr key={`${m.topic_slug}-${m.concept_name}`}>
                <td>{m.topic_slug}</td>
                <td>{m.concept_name}</td>
                <td>{m.weight}</td>
                <td>
                  <DeleteButton label="删除" path={`/api/admin/topic-mapping/${m.id}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
