"use client";

// 后台登录页：POST /api/admin/login（经 rewrites 到 FastAPI），
// 成功后由后端写 HttpOnly Cookie，再跳 /admin。
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <h1>后台登录</h1>
      <p className="muted">仅管理员登录。账号由环境变量 ADMIN_EMAIL 配置，密码哈希存 ADMIN_PASSWORD_HASH。</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setMsg("");
          try {
            const res = await fetch("/api/admin/login", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email, password }),
              credentials: "include",
            });
            if (!res.ok) {
              setMsg("登录失败：邮箱或密码错误，或未配置管理员账号。");
              return;
            }
            router.push("/admin");
            router.refresh();
          } catch {
            setMsg("登录失败：后端不可用。");
          } finally {
            setBusy(false);
          }
        }}
      >
        <p>
          邮箱：{" "}
          <input value={email} onChange={(e) => setEmail(e.target.value)} required />
        </p>
        <p>
          密码：{" "}
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </p>
        <button type="submit" disabled={busy}>登录</button>
      </form>
      {msg ? <p className="error">{msg}</p> : null}
    </>
  );
}
