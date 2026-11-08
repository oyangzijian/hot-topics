// 站点头部（客户端组件，只为按当前路由高亮导航）。
// 导航：题材热度 / 产业链图谱 / 数据导出 / 方法论；不放用户登录按钮
// （本站无账号体系）；管理员入口在页脚。会员按钮外链爱发电创作者主页。
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AFDIAN_URL } from "../lib/api";

const NAV = [
  { href: "/", label: "题材热度" },
  { href: "/chains", label: "产业链图谱" },
  { href: "/export", label: "数据导出" },
  { href: "/method", label: "方法论" },
];

export default function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a className="logo" href="/">
          <b>978</b>智能数据中心
        </a>
        <nav>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "active" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <form className="search" method="get" action="/search">
          <input name="q" placeholder="搜索股票代码、简称或题材" aria-label="搜索股票代码、简称或题材" />
          <button type="submit">搜索</button>
        </form>
        <a
          className="btn-member"
          href={AFDIAN_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          爱发电
        </a>
      </div>
    </header>
  );
}
