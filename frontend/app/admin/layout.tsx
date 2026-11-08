import Link from "next/link";

// 后台布局：只放导航。验权不在 layout 做（会包住 /admin/login 导致自循环），
// 各后台页开头调 lib/admin-guard 的 requireAdminPage()；middleware 已拦
// 无 Cookie 的 /admin/* 访问。
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <nav>
        <Link href="/admin">总览</Link>
        {" · "}
        <Link href="/admin/tasks">任务监控</Link>
        {" · "}
        <Link href="/admin/data-sources">数据源管理</Link>
        {" · "}
        <Link href="/admin/topic-mapping">题材归并</Link>
        {" · "}
        <Link href="/admin/layering">分层校准</Link>
        {" · "}
        <Link href="/admin/institutions">机构源管理</Link>
        {" · "}
        <Link href="/admin/reports">报告审核</Link>
        {" · "}
        <Link href="/">回前台</Link>
      </nav>
      <hr />
      {children}
    </>
  );
}
