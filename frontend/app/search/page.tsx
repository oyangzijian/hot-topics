
export const runtime = "edge";

import Link from "next/link";
import { fetchSearch } from "../../lib/api";

// 搜索页（骨架 v2 §6）：结果分组：题材 / 公司 / 报告 / 机构观点。
export default async function SearchPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = (searchParams.q ?? "").trim();
  const data = q ? await fetchSearch(q).catch(() => null) : null;
  return (
    <>
      <h1>搜索</h1>
      <form method="get" action="/search">
        <input name="q" placeholder="搜题材 / 公司 / 报告" defaultValue={q} size={40} />{" "}
        <button type="submit">搜索</button>
      </form>
      {!q ? (
        <p className="muted">输入关键词后按分组展示结果。</p>
      ) : !data ? (
        <p className="muted">搜索接口暂不可用：请确认后端已启动。</p>
      ) : (
        <>
          <h2>题材（{data.topics.length}）</h2>
          {data.topics.length === 0 ? <p className="muted">无匹配题材。</p> : data.topics.map((t) => (
            <p key={t.slug}><Link href={`/topic/${t.slug}`}>{t.name}</Link></p>
          ))}
          <h2>公司（{data.companies.length}）</h2>
          {data.companies.length === 0 ? <p className="muted">无匹配公司。</p> : data.companies.map((c) => (
            <p key={c.code}><Link href={`/company/${c.code}`}>{c.name}</Link> {c.code}</p>
          ))}
          <h2>报告（{data.reports.length}）</h2>
          {data.reports.length === 0 ? <p className="muted">无匹配报告。</p> : data.reports.map((r) => (
            <p key={r.id}>
              <Link href={`/reports/${r.id}`}>
                {r.report_type === "industry" ? "行业报告" : "公司报告"} · {r.topic ?? r.company ?? ""}
              </Link>
            </p>
          ))}
          <h2>机构观点（{data.institutions.length}）</h2>
          {data.institutions.length === 0 ? <p className="muted">无匹配机构观点。</p> : data.institutions.map((s) => (
            <p key={s.id}>{s.title} <span className="muted">— {s.institution}</span></p>
          ))}
        </>
      )}
    </>
  );
}
