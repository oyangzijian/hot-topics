// 日期渲染：全站统一按北京时间（+08:00）渲染，绝不用服务器本地时区。
// 背景：服务器时区是 UTC，之前 fetched_at 用 new Date(iso) + 本地 getHours()
// 渲染，标的却是（+08:00），会把时间写早 8 小时、甚至错一天。

/** 交易日（YYYY-MM-DD）：按 +08:00 取年月日与星期。 */
export function fmtTradeDate(iso: string | null | undefined): string {
  if (!iso) return "未获取";
  const d = new Date(`${iso}T00:00:00+08:00`);
  if (Number.isNaN(d.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    weekday: "long",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  // 星期必须取 +08:00 的 Intl 结果，不能用 d.getDay()（服务器是 UTC，会错一天）。
  const weekday = (get("weekday") || "").replace("星期", "周");
  return `${get("year")}年${get("month")}月${get("day")}日（${weekday}）`;
}

/** 抓取时间（ISO 时间戳）：按 +08:00 渲染，形如 2026年11月7日 15:00（+08:00）。 */
export function fmtFetchedAt(iso: string | null | undefined): string {
  if (!iso) return "未获取";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}年${get("month")}月${get("day")}日 ${get("hour")}:${get("minute")}（+08:00）`;
}
