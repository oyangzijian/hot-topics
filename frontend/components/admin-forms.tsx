"use client";

// 后台表单（客户端组件）：走相对路径 /api/admin/*，经 rewrites 代理到 FastAPI。
import { useRouter } from "next/navigation";
import { useState } from "react";

async function send(path: string, method: string, body: unknown) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${text.slice(0, 200)}`);
  }
  return res.json();
}

export function MappingForm() {
  const router = useRouter();
  const [topicSlug, setTopicSlug] = useState("humanoid-robot");
  const [concept, setConcept] = useState("");
  const [weight, setWeight] = useState("1");
  const [msg, setMsg] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setMsg("");
        try {
          await send("/api/admin/topic-mapping", "POST", {
            topic_slug: topicSlug,
            concept_name: concept,
            weight: parseFloat(weight) || 1,
          });
          setMsg("已保存");
          router.refresh();
        } catch (err) {
          setMsg(err instanceof Error ? `失败：${err.message}` : "失败");
        }
      }}
    >
      <p>
        题材 slug：<input value={topicSlug} onChange={(e) => setTopicSlug(e.target.value)} required />{" "}
        概念板块名：<input value={concept} onChange={(e) => setConcept(e.target.value)} required />{" "}
        权重：<input value={weight} onChange={(e) => setWeight(e.target.value)} size={4} />{" "}
        <button type="submit">新增/更新映射</button>
      </p>
      {msg ? <p className="muted">{msg}</p> : null}
    </form>
  );
}

export function LayeringForm({
  topicId,
  companyId,
  code,
  name,
  current,
}: {
  topicId: string;
  companyId: string;
  code: string;
  name: string;
  current: string;
}) {
  const router = useRouter();
  const [layer, setLayer] = useState(current);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setMsg("");
        try {
          await send(`/api/admin/layering/${topicId}/${companyId}`, "PUT", {
            layer,
            layer_reason: reason || undefined,
          });
          setMsg("已校准");
          router.refresh();
        } catch (err) {
          setMsg(err instanceof Error ? `失败：${err.message}` : "失败");
        }
      }}
    >
      <span>
        {name} {code}：
        <select value={layer} onChange={(e) => setLayer(e.target.value)}>
          <option value="core">核心公司</option>
          <option value="watch">观察公司</option>
        </select>{" "}
        <input
          placeholder="校准理由（可选）"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          size={30}
        />{" "}
        <button type="submit">保存校准</button>
        {msg ? <span className="muted"> {msg}</span> : null}
      </span>
    </form>
  );
}

export function InstitutionForm() {
  const router = useRouter();
  const [institution, setInstitution] = useState("");
  const [title, setTitle] = useState("");
  const [type, setType] = useState("video");
  const [url, setUrl] = useState("");
  const [msg, setMsg] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setMsg("");
        try {
          await send("/api/admin/institutions", "POST", {
            institution,
            title,
            type,
            url: url || undefined,
          });
          setMsg("已添加");
          router.refresh();
        } catch (err) {
          setMsg(err instanceof Error ? `失败：${err.message}` : "失败");
        }
      }}
    >
      <p>
        机构：<input value={institution} onChange={(e) => setInstitution(e.target.value)} required />{" "}
        栏目：<input value={title} onChange={(e) => setTitle(e.target.value)} required />{" "}
        类型：
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="video">每周评论（视频）</option>
          <option value="report">研究报告</option>
        </select>{" "}
        链接：<input value={url} onChange={(e) => setUrl(e.target.value)} size={30} />{" "}
        <button type="submit">添加机构源</button>
      </p>
      {msg ? <p className="muted">{msg}</p> : null}
    </form>
  );
}
