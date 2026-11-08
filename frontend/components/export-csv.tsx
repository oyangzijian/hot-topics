// CSV 导出（客户端组件）：把服务端传来的“当前免费可见内容”拼成 CSV
// 在浏览器里下载，不经过后端。数值一律取自榜单/题材 API，不编数。
"use client";

export type ExportRankRow = {
  rank: number;
  name: string;
  heat_score: number;
  change_pct: number | null;
  limit_up_count: number | null;
  up_count: number | null;
  down_count: number | null;
  main_net_inflow: number | null;
  is_composite: boolean;
};

export type ExportCompanyRow = {
  topic: string;
  segment: string;
  code: string;
  name: string;
  layer: string;
};

function csvCell(v: string | number | null): string {
  if (v == null) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function download(filename: string, text: string) {
  const blob = new Blob(["\uFEFF" + text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportCsv({
  rankRows,
  companies,
}: {
  rankRows: ExportRankRow[];
  companies: ExportCompanyRow[];
}) {
  const downloadRank = () => {
    const head = ["排名", "题材", "热度指数", "涨跌幅(%)", "涨停数", "成分股上涨家数", "成分股总数", "主力净流入(亿元)", "组合题材"];
    const lines = rankRows.map((r) =>
      [
        r.rank,
        r.name,
        r.heat_score.toFixed(2),
        r.change_pct == null ? "未获取" : r.change_pct.toFixed(2),
        r.limit_up_count == null ? "未获取" : r.limit_up_count,
        r.up_count == null ? "未获取" : r.up_count,
        r.up_count == null || r.down_count == null ? "未获取" : r.up_count + r.down_count,
        r.main_net_inflow == null ? "未获取" : r.main_net_inflow.toFixed(2),
        r.is_composite ? "是" : "否",
      ]
        .map(csvCell)
        .join(","),
    );
    download("题材热度榜-前10.csv", [head.join(","), ...lines].join("\n"));
  };

  const downloadCompanies = () => {
    const head = ["题材", "环节", "公司代码", "公司名称", "分层"];
    const lines = companies.map((c) =>
      [c.topic, c.segment, c.code, c.name, c.layer].map(csvCell).join(","),
    );
    download("公司清单-可见部分.csv", [head.join(","), ...lines].join("\n"));
  };

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      <button onClick={downloadRank} disabled={rankRows.length === 0}>
        下载榜单前 10 CSV{rankRows.length === 0 ? "（暂无数据）" : ""}
      </button>
      <button onClick={downloadCompanies} disabled={companies.length === 0}>
        下载公司清单 CSV（可见部分）{companies.length === 0 ? "（暂无数据）" : ""}
      </button>
    </div>
  );
}
