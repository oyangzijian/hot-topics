// 极简 Markdown 渲染（只处理报告正文用到的结构：# / ## / - 列表 / 段落）。
// 不引入 marked 等依赖；原始文本原样呈现，不做 HTML 注入。
export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flushList = () => {
    if (list.length > 0) {
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {list.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
      list = [];
    }
  };
  lines.forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith("# ")) {
      flushList();
      blocks.push(<h2 key={i}>{t.slice(2)}</h2>);
    } else if (t.startsWith("## ")) {
      flushList();
      blocks.push(<h3 key={i}>{t.slice(3)}</h3>);
    } else if (t.startsWith("- ")) {
      list.push(t.slice(2));
    } else if (t === "") {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={i}>{t}</p>);
    }
  });
  flushList();
  return <div className="md">{blocks}</div>;
}
