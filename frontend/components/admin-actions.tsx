"use client";

// 后台操作按钮（客户端组件）：走相对路径 /api/admin/*，经 Next.js rewrites
// 代理到 FastAPI；Cookie 由浏览器自动携带。失败时如实提示，不编造结果。
import { useRouter } from "next/navigation";
import { useState } from "react";

async function post(path: string, body?: unknown) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${text.slice(0, 200)}`);
  }
  return res.json();
}

async function del(path: string) {
  const res = await fetch(path, { method: "DELETE", credentials: "include" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function ActionButton({
  label,
  path,
  body,
  confirmText,
}: {
  label: string;
  path: string;
  body?: unknown;
  confirmText?: string;
}) {
  const router = useRouter();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <span>
      <button
        disabled={busy}
        onClick={async () => {
          if (confirmText && !window.confirm(confirmText)) return;
          setBusy(true);
          setMsg("");
          try {
            await post(path, body);
            setMsg("已执行");
            router.refresh();
          } catch (e) {
            setMsg(e instanceof Error ? `失败：${e.message}` : "失败");
          } finally {
            setBusy(false);
          }
        }}
      >
        {label}
      </button>
      {msg ? <span className="muted"> {msg}</span> : null}
    </span>
  );
}

export function DeleteButton({ label, path }: { label: string; path: string }) {
  const router = useRouter();
  const [msg, setMsg] = useState("");
  return (
    <span>
      <button
        onClick={async () => {
          if (!window.confirm("确定删除吗？")) return;
          try {
            await del(path);
            setMsg("已删除");
            router.refresh();
          } catch {
            setMsg("删除失败");
          }
        }}
      >
        {label}
      </button>
      {msg ? <span className="muted"> {msg}</span> : null}
    </span>
  );
}
