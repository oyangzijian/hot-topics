import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { fetchAdmin } from "./api";

// 后台页验权（服务端）：用 Cookie 调一次管理接口，401 即转登录页。
// 注意：不要放在 app/admin/layout.tsx——layout 也会包住 /admin/login，
// 未登录时会在登录页上自循环重定向。middleware 只拦无 Cookie 的访问，
// 这里做第二道（Cookie 是否有效）。
export async function requireAdminPage() {
  const cookie = cookies().toString();
  try {
    await fetchAdmin<{ counts: Record<string, number> }>("/api/admin/data-sources", cookie);
  } catch {
    redirect("/admin/login");
  }
}
