export const runtime = "edge";

import type { Metadata } from "next";
import { AFDIAN_URL, fetchRank, fetchTopic } from "../../lib/api";
import ExportCsv, { type ExportCompanyRow, type ExportRankRow } from "../../components/export-csv";

export const metadata: Metadata = {
  title: "数据导出",
  description: "导出当前免费可见内容：题材热度榜前 10 与公司清单可见部分（CSV）。",
  alternates: { canonical: "/export" },
};

// 数据导出：CSV 只含当前免费可见内容（榜单前 10、公司清单可见部分）；
// 全量导出走爱发电（外链），站内不设付费墙、不锁内容。
const FREE_LIMIT = 10;
const VERIFIED = ["人形机器人", "TOPCon电池", "绿色电力"];

function layerLabel(layer: string): string {
  return layer === "core" ? "核心公司" : layer === "watch" ? "观察公司" : "待复核";
}

export default async function ExportPage() {
  let rank = null as Awaited<ReturnType<typeof fetchRank>> | null;
  try {
    rank = await fetchRank();
  } catch {
    rank = null;
  }

  const rankRows: ExportRankRow[] = (rank?.topics ?? []).slice(0, FREE_LIMIT).map((r) => ({
    rank: r.rank,
    name: r.name,
    heat_score: r.heat_score,
    change_pct: r.change_pct,
    limit_up_count: r.limit_up_count,
    up_count: r.up_count,
    down_count: r.down_count,
    main_net_inflow: r.main_net_inflow ?? null,
    is_composite: r.is_composite,
  }));

  // 公司清单可见部分：只取已核验三题材的核心/观察公司（待复核不进导出）。
  const companies: ExportCompanyRow[] = [];
  const missingTopics: string[] = [];
  for (const name of VERIFIED) {
    const hit = rank?.items.find((i) => i.name === name);
    if (!hit) {
      missingTopics.push(name);
      continue;
    }
    try {
      const detail = await fetchTopic(hit.slug);
      for (const c of [...detail.companies.core, ...detail.companies.watch]) {
        if (!c.code) continue;
        companies.push({
          topic: detail.name,
          segment: c.segment ?? "未分环节",
          code: c.code,
          name: c.name ?? "",
          layer: layerLabel(c.layer),
        });
      }
    } catch {
      missingTopics.push(name);
    }
  }

  return (
    <>
      <h1>数据导出</h1>
      <p className="muted">
        CSV 只导出当前免费可见内容：题材热度榜前 {FREE_LIMIT} 名，以及已核验题材的公司清单可见部分。
        缺失处标“未获取”，不编数。
      </p>

      {rank === null ? (
        <div className="error">
          <p>榜单接口暂不可用：请确认后端已启动，或稍后刷新重试。本页不导出编造的数据。</p>
        </div>
      ) : (
        <section className="panel">
          <h2 style={{ marginTop: 0 }}>免费导出</h2>
          <p className="muted">
            榜单前 {FREE_LIMIT} 名：{rankRows.length} 行
            {rankRows.length === 0 ? "（暂无快照）" : ""} · 公司清单可见部分：
            {companies.length} 家
            {missingTopics.length > 0
              ? `（${missingTopics.join("、")}暂无已核验数据，未计入）`
              : ""}
          </p>
          <ExportCsv rankRows={rankRows} companies={companies} />
        </section>
      )}

      <div className="afdian-card">
        <h3>需要全量数据？</h3>
        <p>完整 120+ 题材榜、全部公司清单与会员专属内容，在爱发电查看。</p>
        <a className="btn-member" href={AFDIAN_URL} target="_blank" rel="noopener noreferrer">
          去爱发电查看 →
        </a>
      </div>

      <p className="muted">本页内容不是投资建议。</p>
    </>
  );
}
