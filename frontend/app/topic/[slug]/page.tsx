
export const runtime = "edge";

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchInstitutions, fetchReport, fetchTopic, type LayerCompany } from "../../../lib/api";
import { Markdown } from "../../../lib/md";
import humanoid from "../../../data/humanoid.json";

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  try {
    const topic = await fetchTopic(params.slug);
    return {
      title: topic.name,
      description: `${topic.name}：行业概览、产业链与公司清单。`,
      alternates: { canonical: `/topic/${params.slug}` },
    };
  } catch {
    return { title: "题材" };
  }
}

// 题材行业页（骨架 v2 §2）：行业概览 + 产业链图谱（点环节筛公司）+
// 公司清单（核心/观察/待复核）+ 该题材机构观点 + 行业报告 + 相关题材。
// 数据走后端 /api/topics/{slug}；后端不可用且为首期题材时，退回本地夹具
// humanoid.json 并明确标注“夹具数据”，不编造。
function CompanyRow({ c }: { c: LayerCompany }) {
  if (!c.code) return null;
  return (
    <div className="card" key={c.code}>
      <p>
        <Link href={`/company/${c.code}`}>
          <strong>{c.name}</strong>
        </Link>{" "}
        <span className="muted">{c.code}</span>{" "}
        <span className={`tag ${c.layer === "core" ? "core" : ""}`}>
          {c.layer === "core" ? "核心公司" : c.layer === "watch" ? "观察公司" : "待复核"}
        </span>
      </p>
      <p className="muted">环节：{c.segment ?? "—"}</p>
      <p>分层理由：{c.layer_reason ?? "—"}</p>
      <p className="muted">
        来源标注：{c.source_flags?.concept ? "概念命中" : "—"}
        {c.source_flags?.chain ? " / 图谱命中" : ""}
      </p>
    </div>
  );
}

export default async function TopicPage({
  params,
  searchParams,
}: {
  params: { slug: string };
  searchParams: { segment?: string; layer?: string };
}) {
  const slug = params.slug;
  let topic = null as Awaited<ReturnType<typeof fetchTopic>> | null;
  let backendDown = false;
  try {
    topic = await fetchTopic(slug);
  } catch {
    backendDown = true;
  }
  if (!topic) {
    if (slug === "humanoid-robot" && backendDown) {
      // 夹具退路：只对首期题材，且明确标注
      const core = humanoid.companies.filter((c) => c.layer === "core");
      const watch = humanoid.companies.filter((c) => c.layer === "watch");
      const review = humanoid.companies.filter((c) => c.layer === "review");
      return (
        <>
          <h1>人形机器人</h1>
          <p className="muted">后端暂不可用，显示本地夹具数据（scored_26.csv 修正后，2026-11-07 实测）。</p>
          <h2>核心公司（{core.length} 家）</h2>
          {core.map((c) => (
            <p key={c.code}>
              <Link href={`/company/${c.code}`}>{c.name}</Link> {c.code} · {c.segment}
            </p>
          ))}
          <h2>观察公司（{watch.length} 家）</h2>
          {watch.map((c) => (
            <p key={c.code}>
              <Link href={`/company/${c.code}`}>{c.name}</Link> {c.code} · {c.segment}
            </p>
          ))}
          <h2>待复核（{review.length} 家）</h2>
          {review.map((c) => (
            <p key={c.code}>{c.name} {c.code} · {c.segment}</p>
          ))}
        </>
      );
    }
    notFound();
  }

  const segmentFilter = searchParams.segment;
  const layerFilter = searchParams.layer;
  const filterCompanies = (items: LayerCompany[]) =>
    items.filter(
      (c) =>
        (!segmentFilter || (c.segment ?? "").split("、")[0] === segmentFilter) &&
        (!layerFilter || c.layer === layerFilter)
    );
  const core = filterCompanies(topic.companies.core);
  const watch = filterCompanies(topic.companies.watch);
  const review = filterCompanies(topic.companies.review);
  let industryReport: Awaited<ReturnType<typeof fetchReport>> | null = null;
  if (topic.industry_report) {
    try {
      industryReport = await fetchReport(topic.industry_report.id);
    } catch {
      industryReport = null;
    }
  }
  let institutions: Awaited<ReturnType<typeof fetchInstitutions>> | null = null;
  try {
    institutions = await fetchInstitutions();
  } catch {
    institutions = null;
  }
  const overview = topic.overview;

  return (
    <>
      <h1>{topic.name}</h1>
      <p className="muted">
        {topic.rank ? `当前排名 ${topic.rank} · ` : ""}
        {topic.heat_score != null ? `热度分 ${topic.heat_score.toFixed(2)} · ` : ""}
        {topic.change_pct != null ? `涨跌幅 ${topic.change_pct.toFixed(2)}% · ` : ""}
        {topic.updated_at ? `更新时间：${topic.updated_at}` : "暂无快照"}
        {topic.industry_report ? (
          <>
            {" · "}
            <a href={`/api/reports/${topic.industry_report.id}/download`}>下载行业报告</a>
          </>
        ) : null}
      </p>
      <p className="muted">概念映射：{topic.concept_names.join("、") || "—"}</p>

      <h2>行业概览</h2>
      {overview ? (
        <>
          <p>{overview.definition}</p>
          <h3>驱动因素</h3>
          <ul>{overview.drivers.map((d, i) => <li key={i}>{d}</li>)}</ul>
          <h3>市场规模</h3>
          <ul>
            {overview.market_size.map((m, i) => (
              <li key={i}>{m.label}：{m.value}（来源：{m.source}）</li>
            ))}
          </ul>
          <h3>技术趋势</h3>
          <ul>{overview.tech_trends.map((t, i) => <li key={i}>{t}</li>)}</ul>
          <h3>政策环境</h3>
          <p>{overview.policy}</p>
          <h3>竞争格局</h3>
          <p>{overview.competition}</p>
          <h3>产业链图谱</h3>
          <p className="muted">上游 → 中游 → 下游，点击环节筛选下方公司清单。</p>
          {Object.entries(overview.chain).map(([stage, items]) => (
            <div className="card" key={stage}>
              <p><strong>{stage}</strong></p>
              <p>{items.join("、")}</p>
            </div>
          ))}
        </>
      ) : (
        <p className="muted">{topic.description ?? "暂无已核验的行业概览：未获取。"}</p>
      )}
      <p>
        筛选：
        <Link href={`/topic/${slug}`}> 全部</Link>
        {Object.keys(topic.segments).map((seg) => (
          <span key={seg}>
            {" · "}
            <Link href={`/topic/${slug}?segment=${encodeURIComponent(seg)}`}>{seg}</Link>
          </span>
        ))}
        {segmentFilter ? <span className="muted">（当前环节：{segmentFilter}）</span> : null}
      </p>

      <h2>公司清单</h2>
      <p>
        分层筛选：
        <Link href={`/topic/${slug}`}> 全部</Link>
        {" · "}
        <Link href={`/topic/${slug}?layer=core`}>核心公司</Link>
        {" · "}
        <Link href={`/topic/${slug}?layer=watch`}>观察公司</Link>
      </p>
      <h3>核心公司（{core.length} 家）</h3>
      {core.length === 0 ? <p className="muted">该筛选下暂无核心公司。</p> : core.map((c) => <CompanyRow key={c.code} c={c} />)}
      <h3>观察公司（{watch.length} 家）</h3>
      {watch.length === 0 ? <p className="muted">该筛选下暂无观察公司。</p> : watch.map((c) => <CompanyRow key={c.code} c={c} />)}
      {review.length > 0 ? (
        <p className="muted">
          待复核（{review.length} 家，不进核心/观察两组，待人工复核后再定）：
          {review.map((c) => `${c.name} ${c.code}`).join("、")}。
        </p>
      ) : null}
      <p className="muted">本页内容不是投资建议。</p>

      <h2>该题材机构观点</h2>
      {institutions && institutions.digests.length > 0 ? (
        institutions.digests.slice(0, 5).map((d) => (
          <p key={d.id}>
            {d.title} <span className="muted">— {d.institution} · {d.published_at ?? ""}</span>
          </p>
        ))
      ) : (
        <p className="muted">研报摘要源尚未配置，暂无该题材机构观点：未获取。<Link href="/institutions">去机构观点页 →</Link></p>
      )}

      <h2>行业研究报告</h2>
      {industryReport?.content_md ? (
        <>
          <Markdown text={industryReport.content_md} />
          <p>
            <a href={`/api/reports/${industryReport.id}/download`}>下载 Markdown</a>
          </p>
        </>
      ) : (
        <p className="muted">行业报告尚未生成：未获取。</p>
      )}

    </>
  );
}
