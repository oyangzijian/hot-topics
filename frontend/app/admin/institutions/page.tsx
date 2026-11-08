
export const runtime = "edge";

import { cookies } from "next/headers";
import { requireAdminPage } from "../../../lib/admin-guard";
import { fetchAdmin } from "../../../lib/api";
import { DeleteButton } from "../../../components/admin-actions";
import { InstitutionForm } from "../../../components/admin-forms";

// 后台机构源管理 /admin/institutions：每周评论栏目 + 研报摘要源维护。
export default async function AdminInstitutions() {
  await requireAdminPage();
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const data = await fetchAdmin<{
    sources: { id: string; institution: string; title: string; type: string; url: string | null }[];
    digests: { id: string; institution: string; title: string; published_at: string | null }[];
  }>("/api/admin/institutions", cookie);
  return (
    <>
      <h1>机构源管理</h1>
      <InstitutionForm />
      <h2>机构源（{data.sources.length}）</h2>
      {data.sources.length === 0 ? (
        <p className="muted">暂无机构源：每周评论与研报摘要均未配置，不展示假内容。</p>
      ) : (
        data.sources.map((s) => (
          <p key={s.id}>
            {s.institution} · {s.title}（{s.type === "video" ? "每周评论" : "研究报告"}）{" "}
            {s.url ? <a href={s.url}>链接</a> : null}{" "}
            <DeleteButton label="删除" path={`/api/admin/institutions/${s.id}`} />
          </p>
        ))
      )}
      <h2>研报摘要（{data.digests.length}）</h2>
      {data.digests.length === 0 ? (
        <p className="muted">暂无研报摘要。</p>
      ) : (
        data.digests.map((d) => (
          <p key={d.id}>
            {d.title} <span className="muted">{d.institution} · {d.published_at ?? ""}</span>{" "}
            <DeleteButton label="删除" path={`/api/admin/institutions/digest/${d.id}`} />
          </p>
        ))
      )}
    </>
  );
}
