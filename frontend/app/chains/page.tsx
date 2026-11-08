export const runtime = "edge";

import type { Metadata } from "next";
import Link from "next/link";
import { fetchRank, fetchTopic, type LayerCompany, type TopicDetail } from "../../lib/api";
import humanoid from "../../data/humanoid.json";

export const metadata: Metadata = {
  title: "产业链图谱",
  description: "已核验题材的环节—公司分层结构：人形机器人、TOPCon电池、绿色电力。",
  alternates: { canonical: "/chains" },
};

// 产业链图谱（简版）：只画已核验的三个题材，数据走现有题材 API
// （/api/topics/rank 发现 slug → /api/topics/{slug} 取环节与公司分层）。
// 未核验题材不画、不编；某题材在 API 里不存在时只显示诚实空态。
// 人形机器人后端不可用时退回本地已核验夹具 humanoid.json 并明确标注。
const VERIFIED = ["人形机器人", "TOPCon电池", "绿色电力"];

type ChainTopic = {
  name: string;
  slug: string | null;
  stages: { stage: string; nodes: string[] }[];
  segments: { segment: string; companies: LayerCompany[] }[];
  source: string;
  fixture?: boolean;
};

function groupBySegment(companies: LayerCompany[]): { segment: string; companies: LayerCompany[] }[] {
  const map = new Map<string, LayerCompany[]>();
  for (const c of companies) {
    const segs = (c.segment ?? "未分环节").split(/[、/]/).map((s) => s.trim()).filter(Boolean);
    for (const s of segs.length ? segs : ["未分环节"]) {
      const list = map.get(s) ?? [];
      if (!list.some((x) => x.code === c.code)) list.push(c);
      map.set(s, list);
    }
  }
  return Array.from(map.entries())
    .map(([segment, list]) => ({ segment, companies: list }))
    .sort((a, b) => b.companies.length - a.companies.length);
}

function fromTopicDetail(t: TopicDetail): ChainTopic {
  const stages = t.overview
    ? Object.entries(t.overview.chain).map(([stage, nodes]) => ({ stage, nodes }))
    : [];
  const all = [...t.companies.core, ...t.companies.watch];
  return {
    name: t.name,
    slug: t.slug,
    stages,
    segments: groupBySegment(all),
    source: "题材 API（主营核验分层）",
  };
}

function fromHumanoidFixture(): ChainTopic {
  const companies: LayerCompany[] = humanoid.companies.map((c) => ({
    code: c.code,
    name: c.name,
    segment: c.segment,
    layer: c.layer,
    layer_reason: c.reason,
    source_flags: null,
    main_products: null,
  }));
  return {
    name: "人形机器人",
    slug: "humanoid-robot",
    stages: [
      { stage: "上游", nodes: ["减速器", "传感器", "伺服电机", "丝杠", "结构件"] },
      { stage: "中游", nodes: ["执行器", "控制系统", "整机"] },
      { stage: "下游", nodes: ["工业制造", "物流仓储", "服务陪伴"] },
    ],
    segments: groupBySegment(companies),
    source: "本地夹具（scored_26.csv 修正后，2026-11-07 实测）",
    fixture: true,
  };
}

function layerLabel(layer: string): string {
  return layer === "core" ? "核心公司" : layer === "watch" ? "观察公司" : "待复核";
}

export default async function ChainsPage() {
  let rank = null as Awaited<ReturnType<typeof fetchRank>> | null;
  try {
    rank = await fetchRank();
  } catch {
    rank = null;
  }

  const topics: ChainTopic[] = [];
  const missing: string[] = [];
  for (const name of VERIFIED) {
    const hit = rank?.items.find((i) => i.name === name);
    if (!hit) {
      if (name === "人形机器人") {
        topics.push(fromHumanoidFixture());
      } else {
        missing.push(name);
      }
      continue;
    }
    try {
      const detail = await fetchTopic(hit.slug);
      topics.push(fromTopicDetail(detail));
    } catch {
      if (name === "人形机器人") {
        topics.push(fromHumanoidFixture());
      } else {
        missing.push(name);
      }
    }
  }

  return (
    <>
      <h1>产业链图谱</h1>
      <p className="muted">
        只展示已核验题材的环节—公司分层结构。未核验题材不画、不编；公司分层以主营产品核验为准。
      </p>
      {rank === null && !topics.some((t) => t.fixture) ? (
        <div className="error">
          <p>题材接口暂不可用：请确认后端已启动，或稍后刷新重试。本页不展示编造的图谱。</p>
        </div>
      ) : null}

      {topics.map((t) => (
        <section className="panel" key={t.name} aria-label={`${t.name}产业链`}>
          <h2 style={{ marginTop: 0 }}>
            {t.slug ? <Link href={`/topic/${t.slug}`}>{t.name}</Link> : t.name}
          </h2>
          <p className="muted">
            数据来源：{t.source}
            {t.fixture ? "（后端暂不可用，显示本地夹具）" : ""}
          </p>
          {t.stages.length > 0 ? (
            <>
              <h3>环节结构</h3>
              {t.stages.map((s) => (
                <div className="chain-stage" key={s.stage}>
                  <strong>{s.stage}</strong>
                  <div className="chain-nodes">
                    {s.nodes.map((n) => (
                      <span className="chain-node" key={n}>{n}</span>
                    ))}
                  </div>
                </div>
              ))}
            </>
          ) : null}
          <h3>环节—公司分层</h3>
          {t.segments.length === 0 ? (
            <p className="muted">该题材暂无已核验的公司分层：未获取。</p>
          ) : (
            t.segments.map((seg) => (
              <div key={seg.segment} style={{ marginBottom: 12 }}>
                <p>
                  <b>{seg.segment}</b>{" "}
                  <span className="muted">（{seg.companies.length} 家）</span>
                </p>
                <p>
                  {seg.companies.map((c) => (
                    <span key={c.code ?? c.name} style={{ marginRight: 12 }}>
                      {c.code ? (
                        <Link href={`/company/${c.code}`}>{c.name}</Link>
                      ) : (
                        c.name
                      )}{" "}
                      <span className={`tag ${c.layer === "core" ? "core" : ""}`}>
                        {layerLabel(c.layer)}
                      </span>
                    </span>
                  ))}
                </p>
              </div>
            ))
          )}
        </section>
      ))}

      {missing.map((name) => (
        <section className="panel" key={name}>
          <h2 style={{ marginTop: 0 }}>{name}</h2>
          <p className="muted">暂无已核验数据：该题材尚未进入题材 API，图谱待核验完成后展示，不编内容。</p>
        </section>
      ))}

      <p className="muted">本页内容不是投资建议。</p>
    </>
  );
}
