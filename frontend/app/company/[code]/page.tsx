
export const runtime = "edge";

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchCompany } from "../../../lib/api";
import { Markdown } from "../../../lib/md";

export async function generateMetadata({ params }: { params: { code: string } }): Promise<Metadata> {
  try {
    const company = await fetchCompany(params.code);
    return {
      title: `${company.name}（${company.code}）`,
      description: `${company.name}：分层依据与深度报告。`,
      alternates: { canonical: `/company/${params.code}` },
    };
  } catch {
    return { title: "公司" };
  }
}

// 公司详情页（骨架 v3 §公司页，4 个单元）：
// 1 标题区 → 2 深度报告正文 → 3 分层依据（基本信息、产业链定位、
// 证据与来源均在本区内，缺失写“未获取”）→ 4 同环节其他公司推荐。
// 只有绿的谐波、兆威机电有定位级样本报告；其余公司明确写“只有定位卡片”。
export default async function CompanyPage({ params }: { params: { code: string } }) {
  let company: Awaited<ReturnType<typeof fetchCompany>> | null = null;
  try {
    company = await fetchCompany(params.code);
  } catch {
    notFound();
  }
  if (!company) notFound();

  return (
    <>
      <h1>{company.name}</h1>
      <p className="muted">
        {company.code}
        {company.layers.length > 0 ? ` · 环节：${company.layers[0].segment ?? "—"}` : ""}
        {company.layers.length > 0 ? ` · ${company.layers[0].layer === "core" ? "核心公司" : "观察公司"}` : ""}
      </p>

      <h2>公司深度报告</h2>
      {company.report ? (
        company.report.report_html ? (
          <p>
            <Link href={`/reports/${company.report.id}`}>查看完整 HTML 深度报告 →</Link>
          </p>
        ) : company.report.content_md ? (
          <>
            <Markdown text={company.report.content_md} />
            <p className="muted">
              <Link href={`/reports/${company.report.id}`}>查看报告详情 →</Link>
            </p>
          </>
        ) : (
          <p className="muted">
            本公司暂无完整深度报告，只有定位卡片与分层依据。收入占比、客户验证进度、
            量产时间等缺失项见分层依据：未获取。
          </p>
        )
      ) : (
        <p className="muted">
          本公司暂无完整深度报告，只有定位卡片与分层依据。收入占比、客户验证进度、
          量产时间等缺失项见分层依据：未获取。
        </p>
      )}

      <h2>分层依据</h2>
      {company.layers.length === 0 ? (
        <p className="muted">暂无分层记录：该公司在当前题材下待复核。</p>
      ) : (
        company.layers.map((layer, i) => (
          <div className="card" key={i}>
            <p>
              为什么是{layer.layer === "core" ? "核心公司" : "观察公司"}：
              {layer.layer_reason ?? "—"}
            </p>
            <p className="muted">
              所属题材：
              {layer.topic_slug ? (
                <Link href={`/topic/${layer.topic_slug}`}>{layer.topic_name}</Link>
              ) : (
                layer.topic_name
              )}{" "}
              · 环节：{layer.segment ?? "—"}
              {layer.manual_override ? " · 人工校准" : ""}
            </p>
          </div>
        ))
      )}
      <h3>基本信息</h3>
      <p className="muted">所属行业：{company.industry ?? "未获取"}</p>
      <p>主营产品：{company.main_products ? company.main_products.join("、") : "未获取"}</p>
      {company.revenue_share ? (
        <p>
          题材相关业务营收占比：{company.revenue_share.product} {Math.round(company.revenue_share.share * 10000) / 100}%
          （{company.revenue_share.report_date}，来源：{company.revenue_share.source}）
        </p>
      ) : (
        <p className="muted">题材相关业务营收占比：未获取（产品分类太粗拆不出来，或未核验）。</p>
      )}
      <h3>产业链定位</h3>
      <p>
        {company.layers.length > 0
          ? `所属环节：${company.layers[0].segment ?? "—"}；同环节公司见下。`
          : "产业链定位：未获取。"}
      </p>
      <h3>证据与来源</h3>
      <p className="muted">{company.evidence_note}</p>
      <ul>
        <li>概念板块命中与主营产品原文：见分层理由。</li>
        <li>收入占比：{company.revenue_share ? company.revenue_share.source : "未获取"}。</li>
      </ul>

      <h2>同环节其他公司推荐</h2>
      {company.same_segment.length === 0 ? (
        <p className="muted">暂无同环节公司。</p>
      ) : (
        company.same_segment.map((c) => (
          <p key={c.code}>
            <Link href={`/company/${c.code}`}>{c.name}</Link> {c.code} · {c.segment ?? ""}
          </p>
        ))
      )}
    </>
  );
}
