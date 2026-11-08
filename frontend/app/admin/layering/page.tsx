
export const runtime = "edge";

import Link from "next/link";
import { cookies } from "next/headers";
import { requireAdminPage } from "../../../lib/admin-guard";
import { fetchAdmin } from "../../../lib/api";
import { LayeringForm } from "../../../components/admin-forms";

// 后台分层校准 /admin/layering：核心/观察手工校准（人工校准记 manual_override）。
export default async function AdminLayering({
  searchParams,
}: {
  searchParams: { topic_slug?: string };
}) {
  await requireAdminPage();
  const topicSlug = searchParams.topic_slug ?? "humanoid-robot";
  const cookie = `admin_session=${cookies().get("admin_session")?.value ?? ""}`;
  const data = await fetchAdmin<{
    items: {
      topic_id: string;
      topic_slug: string | null;
      company_id: string;
      code: string | null;
      name: string | null;
      segment: string | null;
      layer: string;
      layer_reason: string | null;
      manual_override: boolean;
    }[];
  }>(`/api/admin/layering?topic_slug=${topicSlug}`, cookie);
  return (
    <>
      <h1>分层校准</h1>
      <p>
        题材：
        <Link href="/admin/layering?topic_slug=humanoid-robot">人形机器人</Link>
      </p>
      {data.items.length === 0 ? (
        <p className="muted">该题材暂无分层记录。</p>
      ) : (
        data.items.map((it) => (
          <div className="card" key={it.company_id}>
            <LayeringForm
              topicId={it.topic_id}
              companyId={it.company_id}
              code={it.code ?? ""}
              name={it.name ?? ""}
              current={it.layer}
            />
            <p className="muted">
              环节：{it.segment ?? "—"} · 当前分层：{it.layer === "core" ? "核心公司" : "观察公司"}
              {it.manual_override ? " · 已人工校准" : ""}
              {it.layer_reason ? ` · 理由：${it.layer_reason}` : ""}
            </p>
          </div>
        ))
      )}
    </>
  );
}
