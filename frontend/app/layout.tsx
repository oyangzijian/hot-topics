import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import SiteHeader from "../components/site-header";

const SITE_URL = "https://tcs.999777888.xyz";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "978智能数据中心",
    template: "%s · 978智能数据中心",
  },
  description:
    "题材热度榜、行业页与公司深度报告：只提供数据与规则计算结果，不推荐股票。",
  openGraph: {
    type: "website",
    siteName: "978智能数据中心",
    url: SITE_URL,
    title: "978智能数据中心",
    description:
      "题材热度榜、行业页与公司深度报告：只提供数据与规则计算结果，不推荐股票。",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <SiteHeader />
        <main>{children}</main>
        <footer>
          <nav>
            <Link href="/reports">报告中心</Link>
            <Link href="/institutions">机构观点</Link>
            <Link href="/search">搜索</Link>
            <Link href="/admin/login">管理员登录</Link>
          </nav>
          <p>
            数据来源：东方财富概念板块（经 AKShare）、同花顺主营产品与收入占比；
            热度分与分层规则见<Link href="/method">方法说明</Link>。
          </p>
          <p>
            免责声明：本站只提供数据与规则计算结果，不推荐股票，不构成任何证券投资建议。
            行情数据有延迟与缺失可能，缺失处标注“—”或“未获取”，不做推测填补；
            引用数据请以原始披露为准。会员专属内容通过爱发电提供（见方法说明页）。
          </p>
          <p>
            <Link href="/method">方法说明</Link>
            {" · "}
            <a href="https://tcs.999777888.xyz">978智能数据中心</a>
          </p>
        </footer>
      </body>
    </html>
  );
}
