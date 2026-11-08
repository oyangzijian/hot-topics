
export const runtime = "edge";

import Link from "next/link";
import { fetchInstitutions } from "../../lib/api";

// 机构观点页（骨架 v2 §4）：每周评论（视频导航）+ 研报摘要两页签，
// 筛选 + 免责声明。研报摘要源未配置时如实显示空态，不编造摘要。
export default async function InstitutionsPage({
  searchParams,
}: {
  searchParams: { tab?: string; institution?: string; keyword?: string };
}) {
  const tab = searchParams.tab === "digests" ? "digests" : "weekly";
  const data = await fetchInstitutions({
    ...(searchParams.institution ? { institution: searchParams.institution } : {}),
    ...(searchParams.keyword ? { keyword: searchParams.keyword } : {}),
  }).catch(() => null);

  return (
    <>
      <h1>机构观点</h1>
      <p>
        <Link href="/institutions?tab=weekly">每周评论（视频导航）</Link>
        {" · "}
        <Link href="/institutions?tab=digests">研报摘要</Link>
      </p>
      <form method="get" action="/institutions">
        <input type="hidden" name="tab" value={tab} />
        <input name="institution" placeholder="机构筛选" defaultValue={searchParams.institution ?? ""} />{" "}
        <input name="keyword" placeholder="关键词" defaultValue={searchParams.keyword ?? ""} />{" "}
        <button type="submit">筛选</button>
      </form>
      {!data ? (
        <p className="muted">机构观点接口暂不可用：请确认后端已启动。</p>
      ) : tab === "weekly" ? (
        <>
          <h2>每周评论（视频导航）</h2>
          {data.weekly.length === 0 ? (
            <p className="muted">
              暂无已配置的每周评论栏目。机构源需在后台添加（/admin/institutions），
              本页不展示编造的栏目与链接。
            </p>
          ) : (
            data.weekly.map((s) => (
              <div className="card" key={s.id}>
                <p>
                  <strong>{s.title}</strong> <span className="muted">{s.institution}</span>
                </p>
                <p className="muted">
                  语言：{s.language ?? "—"} · 更新频率：{s.frequency ?? "—"}
                </p>
                {s.url ? (
                  <p><a href={s.url} target="_blank" rel="noreferrer">跳转官方页面 →</a></p>
                ) : null}
              </div>
            ))
          )}
        </>
      ) : (
        <>
          <h2>研报摘要</h2>
          {data.digests.length === 0 ? (
            <p className="muted">
              暂无研报摘要。研报摘要源尚未配置（无 Tushare token、无 MCP），
              本页不展示编造的摘要；请在后台添加机构源。
            </p>
          ) : (
            data.digests.map((d) => (
              <div className="card" key={d.id}>
                <p>
                  <strong>{d.title}</strong> <span className="muted">{d.institution} · {d.published_at ?? ""}</span>
                </p>
                <p>{d.summary ?? ""}</p>
                {d.source_url ? (
                  <p><a href={d.source_url} target="_blank" rel="noreferrer">来源链接 →</a></p>
                ) : null}
              </div>
            ))
          )}
        </>
      )}
      <p className="muted">
        免责声明：本站内容来自公开信息整理与已核验数据，不构成证券投资建议；
        研报摘要以原文链接为准，请以机构原文为准。
      </p>
    </>
  );
}
