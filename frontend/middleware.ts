// Next.js middleware：保护 /admin（除 /admin/login）。
// 只检查会话 Cookie 是否存在；真正鉴权由后端 require_admin 在每次
// 管理 API 调用时做（无有效 Cookie 返回 401，前端再转登录页）。
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;
  if (path.startsWith("/admin") && path !== "/admin/login") {
    const session = req.cookies.get("admin_session");
    if (!session?.value) {
      const url = req.nextUrl.clone();
      url.pathname = "/admin/login";
      return NextResponse.redirect(url);
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
