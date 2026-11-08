export const runtime = "edge";

import type { Metadata } from "next";
import Link from "next/link";
import { Fragment } from "react";
import {
  AFDIAN_URL,
  fetchMarketOverview,
  fetchRank,
  type MarketOverview,
  type RankItem,
} from "../lib/api";
import { fmtFetchedAt, fmtTradeDate } from "../lib/format";

export const metadata: Metadata = {
  title: "热门题材榜",
  description:
    "题材热度榜与风格/行为榜：只提供数据与规则计算结果，不推荐股票。",
  alternates: { canonical: "/" },
};

// 首页 = 深色仪表盘：指数条 + 题材热度榜（左主卡）+ 右栏。
// 诚实原则：后端不可用不编假榜单；只有一个快照时变化类内容一律空态；
// 缺失数字一律标“未获取”。

const FREE_LIMIT = 10;

type RangeKey = "today" | "3d" | "5d" | "week";
const RANGES: { key: RangeKey; label: string }[] = [
  { key: "today", label: "今日" },
  { key: "3d", label: "3日" },
  { key: "5d", label: "5日" },
  { key: "week", label: "本周" },
];

function pctClass(v: number | null | undefined): string {
  if (v == null) return "num";
  return v > 0 ? "num up" : v < 0 ? "num down" : "num";
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "未获取";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtNum(v: number | null | undefined): string {
  return v == null ? "未获取" : v.toLocaleString("zh-CN");
}

// ---- 指数条 ----
function pickIndex(m: MarketOverview | null, keys: string[], codes: string[]) {
  if (!m?.indices) return null;
  return (
    m.indices.find((i) => keys.some((k) => i.name.includes(k))) ??
    m.indices.find((i) => codes.includes(i.code)) ??
    null
  );
}

function MarketStrip({ m }: { m: MarketOverview | null }) {
  const sh = pickIndex(m, ["上证"], ["000001"]);
  const sz = pickIndex(m, ["深证"], ["399001"]);
  const cy = pickIndex(m, ["创业板"], ["399006"]);
  const cells: { label: string; value: string; sub: string; cls: string }[] = [
    {
      label: sh?.name ?? "上证指数",
      value: sh?.value == null ? "未获取" : sh.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }),
      sub: sh?.change_pct == null ? "涨跌幅未获取" : fmtPct(sh.change_pct),
      cls: pctClass(sh?.change_pct),
    },
    {
      label: sz?.name ?? "深证成指",
      value: sz?.value == null ? "未获取" : sz.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }),
      sub: sz?.change_pct == null ? "涨跌幅未获取" : fmtPct(sz.change_pct),
      cls: pctClass(sz?.change_pct),
    },
    {
      label: cy?.name ?? "创业板指",
      value: cy?.value == null ? "未获取" : cy.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }),
      sub: cy?.change_pct == null ? "涨跌幅未获取" : fmtPct(cy.change_pct),
      cls: pctClass(cy?.change_pct),
    },
    {
      label: "两市成交额",
      value:
        m?.turnover_amount == null
          ? "未获取"
          : m.turnover_amount >= 10000
            ? `${(m.turnover_amount / 10000).toFixed(2)}万亿`
            : `${m.turnover_amount.toLocaleString("zh-CN")}亿元`,
      sub:
        m?.turnover_change_pct == null
          ? "较昨日未获取"
          : `${fmtPct(m.turnover_change_pct)}（较昨日）`,
      cls: pctClass(m?.turnover_change_pct),
    },
    {
      label: "涨 / 跌家数",
      value:
        m?.up_count == null || m?.down_count == null
          ? "未获取"
          : `${m.up_count.toLocaleString("zh-CN")} / ${m.down_count.toLocaleString("zh-CN")}`,
      sub:
        m?.limit_up_count == null || m?.limit_down_count == null
          ? "涨停 / 跌停未获取"
          : `涨停 ${m.limit_up_count} · 跌停 ${m.limit_down_count}`,
      cls: "",
    },
  ];
  return (
    <>
      <div className="market-strip">
        {cells.map((c) => (
          <div className="market-cell" key={c.label}>
            <div className="label">{c.label}</div>
            <div className={`value num ${c.cls}`}>{c.value}</div>
            <div className={`sub ${c.cls}`}>{c.sub}</div>
          </div>
        ))}
      </div>
      <p className="market-note">
        {m
          ? `交易日：${fmtTradeDate(m.trade_date)} · 抓取时间：${fmtFetchedAt(m.fetched_at)}${m.stale ? " · 指数数据为上一快照" : ""}`
          : "指数数据未获取：指数接口暂不可用，缺失处不编数。"}
      </p>
    </>
  );
}

// ---- 近 8 日热度折线：只画已有快照点；只有一个点就画一个点，不补假数据 ----
function Sparkline({ trend }: { trend: number[] }) {
  if (!trend || trend.length === 0) return <span className="muted">未获取</span>;
  const w = 96;
  const h = 28;
  const min = Math.min(...trend);
  const max = Math.max(...trend);
  const span = max - min || 1;
  const x = (i: number) => (trend.length === 1 ? w / 2 : 6 + (i * (w - 12)) / (trend.length - 1));
  const y = (v: number) => 4 + (1 - (v - min) / span) * (h - 8);
  const last = trend[trend.length - 1];
  const up = trend.length >= 2 && last >= trend[0];
  const color = up ? "#f87171" : "#34d399";
  if (trend.length === 1) {
    return (
      <svg width={w} height={h} role="img" aria-label={`热度 ${last.toFixed(2)}（仅 1 个快照点）`}>
        <circle cx={w / 2} cy={h / 2} r="3.5" fill={color} />
      </svg>
    );
  }
  const points = trend.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  return (
    <svg width={w} height={h} role="img" aria-label={`近 ${trend.length} 次热度走势`}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.8" />
      <circle cx={x(trend.length - 1)} cy={y(last)} r="3" fill={color} />
    </svg>
  );
}

// ---- 热度榜 ----
function AfdianRow({ colSpan }: { colSpan: number }) {
  return (
    <tr className="afdian-row">
      <td colSpan={colSpan}>
        <div className="afdian-card">
          <h3>查看完整 120+ 题材与会员专属内容</h3>
          <p>榜单前 10 名免费查看；完整 120+ 题材、会员专属报告与数据导出全量在爱发电查看。</p>
          <a className="btn-member" href={AFDIAN_URL} target="_blank" rel="noopener noreferrer">
            去爱发电查看 →
          </a>
        </div>
      </td>
    </tr>
  );
}

function RankTable({ rows }: { rows: RankItem[] }) {
  if (rows.length === 0) return <p className="muted">本榜暂无内容。</p>;
  // 主力净流入列：只有当榜单返回的项里带非 null 的 main_net_inflow 时才渲染整列。
  const showInflow = rows.some((r) => r.main_net_inflow != null);
  const colSpan = showInflow ? 7 : 6;
  return (
    <table>
      <thead>
        <tr>
          <th>排名</th>
          <th>题材</th>
          <th>热度指数</th>
          <th>涨跌幅</th>
          <th>涨停数</th>
          <th>成分股</th>
          {showInflow ? <th>主力净流入</th> : null}
          <th>近 8 日热度</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((item, i) => (
          <Fragment key={item.slug}>
            <tr>
              <td className="num">{item.rank}</td>
              <td>
                <Link href={`/topic/${item.slug}`}>{item.name}</Link>
                {item.is_composite ? (
                  <span
                    className="tag"
                    title="由多个概念板块取均值，与单板块行的口径不同，详见方法说明页"
                  >
                    组合题材
                  </span>
                ) : null}
              </td>
              <td>
                <span className="heat-cell">
                  <span className="heat-bar">
                    <i style={{ width: `${Math.max(0, Math.min(100, item.heat_score))}%` }} />
                  </span>
                  <span className="heat-num num">{item.heat_score.toFixed(2)}</span>
                </span>
              </td>
              <td className={pctClass(item.change_pct)}>{fmtPct(item.change_pct)}</td>
              <td className="num">{item.limit_up_count == null ? "未获取" : item.limit_up_count}</td>
              <td className="num">
                {item.up_count == null || item.down_count == null
                  ? "未获取"
                  : `上涨 ${item.up_count} / 共 ${item.up_count + item.down_count} 家`}
              </td>
              {showInflow ? (
                <td className="num">
                  {item.main_net_inflow == null
                    ? "未获取"
                    : `${item.main_net_inflow > 0 ? "+" : ""}${item.main_net_inflow.toFixed(2)}亿`}
                </td>
              ) : null}
              <td>
                <Sparkline trend={item.trend} />
              </td>
            </tr>
            {i === FREE_LIMIT - 1 && rows.length > FREE_LIMIT ? (
              <AfdianRow colSpan={colSpan} />
            ) : null}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}

// ---- 右栏：热度变化（只有一个快照时算不出变化，诚实空态） ----
function Movers({ rows, direction }: { rows: RankItem[]; direction: "up" | "down" }) {
  const deltas = rows
    .filter((r) => r.trend && r.trend.length >= 2)
    .map((r) => ({ item: r, delta: r.trend[r.trend.length - 1] - r.trend[0] }))
    .filter((d) => (direction === "up" ? d.delta > 0 : d.delta < 0))
    .sort((a, b) =>
      direction === "up" ? b.delta - a.delta : a.delta - b.delta,
    )
    .slice(0, 5);
  if (deltas.length === 0) {
    return (
      <p className="muted">
        暂无变化数据：榜单目前只有一个快照，算不出热度变化，待榜单刷新积累后这里会显示
        {direction === "up" ? "热度上升最快" : "热度下降最快"}的题材。
      </p>
    );
  }
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {deltas.map(({ item, delta }) => (
        <li key={item.slug}>
          <Link href={`/topic/${item.slug}`}>{item.name}</Link>{" "}
          <span className={delta > 0 ? "up num" : "down num"}>
            {delta > 0 ? "+" : ""}
            {delta.toFixed(2)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams: { tab?: string; sort?: string; range?: string };
}) {
  const [rankResult, market] = await Promise.allSettled([fetchRank(), fetchMarketOverview()]);
  const rank = rankResult.status === "fulfilled" ? rankResult.value : null;
  const rankError =
    rankResult.status === "rejected"
      ? rankResult.reason instanceof Error
        ? rankResult.reason.message
        : "榜单接口失败"
      : null;
  const marketOverview = market.status === "fulfilled" ? market.value : null;

  const tab = searchParams.tab === "styles" ? "styles" : "topics";
  const sort = searchParams.sort === "change" ? "change" : "heat";
  const range: RangeKey = (
    ["today", "3d", "5d", "week"] as const
  ).includes(searchParams.range as RangeKey)
    ? (searchParams.range as RangeKey)
    : "today";
  const sortRows = (rows: RankItem[]) =>
    sort === "change"
      ? [...rows].sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity))
      : rows;
  const shown = rank ? sortRows(tab === "styles" ? rank.styles : rank.topics) : [];
  const qs = (extra: Record<string, string>) => {
    const p = new URLSearchParams({ tab, sort, range, ...extra });
    return `/?${p.toString()}`;
  };

  return (
    <>
      <h1>题材热度榜</h1>
      <MarketStrip m={marketOverview} />

      <div className="dash">
        <section className="panel" aria-label="题材热度榜">
          <p className="muted" style={{ marginTop: 0 }}>
            {rank
              ? `更新于 ${fmtFetchedAt(rank.fetched_at)} · 交易时段每 30 分钟刷新 · `
              : "交易时段每 30 分钟刷新 · "}
            <Link href="/method">热度指数如何计算</Link>
            {rank?.market_status === "market_closed" ? (
              <span className="tag">休市，展示最近交易日收盘</span>
            ) : rank?.market_status === "closed" ? (
              <span className="tag">已收盘</span>
            ) : null}
            {rank?.stale ? (
              <span className="stale">刷新失败：{rank.stale_reason ?? "展示上一快照"}</span>
            ) : null}
          </p>

          <div className="tabs">
            {RANGES.map((r) => (
              <Link key={r.key} href={qs({ range: r.key })} className={`pill${range === r.key ? " active" : ""}`}>
                {r.label}
              </Link>
            ))}
          </div>

          {range !== "today" ? (
            <div className="empty">
              <p style={{ marginTop: 0 }}>
                暂无{RANGES.find((r) => r.key === range)?.label}历史数据。
              </p>
              <p>
                榜单目前只有一个快照
                {rank?.trade_date ? `（${fmtTradeDate(rank.trade_date)}）` : ""}，
                {RANGES.find((r) => r.key === range)?.label}视图随榜单刷新积累后开放，不展示编造的历史曲线。
              </p>
            </div>
          ) : rankError ? (
            <div className="error">
              <p>榜单暂不可用：{rankError}</p>
              <p className="muted">请确认后端已启动（本地默认 http://localhost:8000），或稍后刷新重试。本页不展示编造的榜单。</p>
            </div>
          ) : rank && rank.items.length === 0 ? (
            <p className="muted">暂无快照：请先在后端跑种子（backend/seed_fixture.py）或等交易时段刷新。</p>
          ) : rank ? (
            <>
              <div className="tabs">
                <Link href={qs({ tab: "topics" })} className={`pill${tab === "topics" ? " active" : ""}`}>
                  题材榜（{rank.topics.length}）
                </Link>
                <Link href={qs({ tab: "styles" })} className={`pill${tab === "styles" ? " active" : ""}`}>
                  风格/行为榜（{rank.styles.length}）
                </Link>
                <span className="muted">
                  {" · "}排序：
                  <Link href={qs({ sort: "heat" })}>按热度分</Link>
                  {" / "}
                  <Link href={qs({ sort: "change" })}>按涨跌幅</Link>
                </span>
              </div>
              <RankTable rows={shown} />
              <p className="muted">
                {tab === "topics"
                  ? "题材榜：产业题材（如人形机器人、TOPCon电池）。“组合题材”由多个概念板块取均值，与单板块行的口径不同，详见方法说明页。"
                  : "风格/行为榜：昨日涨停、近期新高、红利股这类行为/风格标签，不是产业题材，单独列出。"}
                榜单免费查看前 {FREE_LIMIT} 名；涨停数为成分股近似计数，不是交易所官方口径；缺失处标“未获取”，不编数。
              </p>
              <p className="muted">{rank.note}</p>
            </>
          ) : null}
        </section>

        <aside className="rail" aria-label="侧栏">
          <div className="panel">
            <h3>🔥 热度上升最快</h3>
            <Movers rows={shown} direction="up" />
          </div>
          <div className="panel">
            <h3>📉 热度下降最快</h3>
            <Movers rows={shown} direction="down" />
          </div>
          <div className="panel">
            <h3>会员可获得</h3>
            <p className="muted" style={{ margin: "0 0 12px" }}>
              完整 120+ 题材榜、会员专属报告与数据导出全量，在爱发电查看。
            </p>
            <a className="btn-member" href={AFDIAN_URL} target="_blank" rel="noopener noreferrer">
              爱发电 →
            </a>
          </div>
        </aside>
      </div>
    </>
  );
}
