export const runtime = "edge";

import type { Metadata } from "next";
import Link from "next/link";
import { fetchRank, type RankItem } from "../lib/api";

export const metadata: Metadata = {
  title: "热门题材榜",
  description:
    "题材热度榜与风格/行为榜：只提供数据与规则计算结果，不推荐股票。",
  alternates: { canonical: "/" },
};

// 首页 = 热门题材榜（题材榜 / 风格·行为榜两个页签）。
// 后端不可用时不编假榜单：如实展示“榜单暂不可用”，并提示刷新/检查后端。
const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function fmtTradeDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00+08:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日（${WEEKDAYS[d.getDay()]}）`;
}

function fmtFetchedAt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}（+08:00）`;
}

function pctClass(v: number | null): string {
  if (v == null) return "num";
  return v > 0 ? "num up" : v < 0 ? "num down" : "num";
}

function trendDelta(t: number[]): string {
  if (!t || t.length < 2) return "—";
  const d = t[t.length - 1] - t[0];
  if (Math.abs(d) < 0.005) return "—";
  return `${d > 0 ? "↑" : "↓"} ${Math.abs(d).toFixed(2)}`;
}

function RankTable({ rows }: { rows: RankItem[] }) {
  if (rows.length === 0) return <p className="muted">本榜暂无内容。</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>排名</th><th>题材</th><th>热度分</th><th>涨跌幅</th><th>上涨家数</th><th>涨停数</th><th>领涨公司</th><th>近5次热度变化</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((item) => (
          <tr key={item.slug}>
            <td className="num">{item.rank}</td>
            <td>
              <Link href={`/topic/${item.slug}`}>{item.name}</Link>
              {item.is_composite ? (
                <span className="tag" title="由多个概念板块取均值，与单板块行的口径不同，详见方法说明页">组合题材</span>
              ) : null}
            </td>
            <td className="num">{item.heat_score.toFixed(2)}</td>
            <td className={pctClass(item.change_pct)}>
              {item.change_pct == null ? "—" : `${item.change_pct > 0 ? "+" : ""}${item.change_pct.toFixed(2)}%`}
            </td>
            <td className="num">
              {item.up_count == null || item.down_count == null
                ? "—"
                : `${item.up_count} / ${item.up_count + item.down_count}`}
            </td>
            <td className="num">{item.limit_up_count == null ? "—" : item.limit_up_count}</td>
            <td>
              {item.leading_company ? (
                item.leading_code ? (
                  <Link href={`/company/${item.leading_code}`}>{item.leading_company}</Link>
                ) : (
                  item.leading_company
                )
              ) : (
                "—"
              )}
            </td>
            <td className="num">{trendDelta(item.trend)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams: { tab?: string; sort?: string };
}) {
  let rank = null as Awaited<ReturnType<typeof fetchRank>> | null;
  let error: string | null = null;
  try {
    rank = await fetchRank();
  } catch (e) {
    error = e instanceof Error ? e.message : "榜单接口失败";
  }

  const tab = searchParams.tab === "styles" ? "styles" : "topics";
  const sort = searchParams.sort === "change" ? "change" : "heat";
  const sortRows = (rows: RankItem[]) =>
    sort === "change"
      ? [...rows].sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity))
      : rows;
  const shown = rank ? sortRows(tab === "styles" ? rank.styles : rank.topics) : [];

  return (
    <>
      <h1>热门题材榜</h1>
      {rank ? (
        <p className="muted">
          数据所属交易日：{fmtTradeDate(rank.trade_date)}
          {" · "}抓取时间：{fmtFetchedAt(rank.fetched_at)}
          {rank.market_status === "market_closed" ? (
            <span className="tag">休市，展示最近交易日收盘</span>
          ) : rank.market_status === "closed" ? (
            <span className="tag">已收盘</span>
          ) : null}
          {rank.stale ? (
            <span className="stale">刷新失败：{rank.stale_reason ?? "展示上一快照"}</span>
          ) : null}
        </p>
      ) : null}
      <p className="muted">
        热度分按当前公式计算，刷新频率为交易时段每 30 分钟一次；详细口径见
        <Link href="/method">方法说明</Link>。
      </p>
      {error ? (
        <div className="error">
          <p>榜单暂不可用：{error}</p>
          <p className="muted">请确认后端已启动（本地默认 http://localhost:8000），或稍后刷新重试。本页不展示编造的榜单。</p>
        </div>
      ) : rank && rank.items.length === 0 ? (
        <p className="muted">暂无快照：请先在后端跑种子（backend/seed_fixture.py）或等交易时段刷新。</p>
      ) : rank ? (
        <>
          <p>
            <Link href="/?tab=topics" className={tab === "topics" ? "tag core" : "tag"}>
              题材榜（{rank.topics.length}）
            </Link>{" "}
            <Link href="/?tab=styles" className={tab === "styles" ? "tag core" : "tag"}>
              风格/行为榜（{rank.styles.length}）
            </Link>
            <span className="muted">
              {" · "}排序：
              <Link href={`/?tab=${tab}&sort=heat`}>按热度分</Link>
              {" / "}
              <Link href={`/?tab=${tab}&sort=change`}>按涨跌幅</Link>
            </span>
          </p>
          <RankTable rows={shown} />
          <p className="muted">
            {tab === "topics"
              ? "题材榜：产业题材（如人形机器人、TOPCon电池）。“组合题材”由多个概念板块取均值，与单板块行的口径不同，详见方法说明页。"
              : "风格/行为榜：昨日涨停、近期新高、红利股这类行为/风格标签，不是产业题材，单独列出。"}
            上涨家数取领涨板块口径；涨停数为成分股近似计数，不是交易所官方口径；缺失处标“—”，不编数。
          </p>
        </>
      ) : null}
      {rank ? <p className="muted">{rank.note}</p> : null}
    </>
  );
}
