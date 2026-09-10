function renderInline(text, keyPrefix) {
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);

  return tokens.map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    if (token.startsWith("**") && token.endsWith("**")) {
      return <strong key={key}>{token.slice(2, -2)}</strong>;
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return <code key={key}>{token.slice(1, -1)}</code>;
    }
    return <span key={key}>{token}</span>;
  });
}

export default function AnalysisMarkdown({ content }) {
  const blocks = [];
  let paragraph = [];
  let list = [];

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", lines: paragraph });
      paragraph = [];
    }
  }

  function flushList() {
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  }

  content.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      return;
    }

    const numbered = line.match(/^(\d+)[.)]\s+(.*)$/);
    const bullet = line.match(/^[-*]\s+(.*)$/);
    if (numbered || bullet) {
      flushParagraph();
      list.push({ number: numbered?.[1] ?? null, text: numbered?.[2] ?? bullet[1] });
      return;
    }

    const heading = line.match(/^\*\*([^*]+)\*\*:?$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", text: heading[1] });
      return;
    }

    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();

  return (
    <div className="analysis-content">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return <h4 key={`heading-${index}`}>{block.text}</h4>;
        }
        if (block.type === "list") {
          const ordered = block.items.some((item) => item.number !== null);
          const ListTag = ordered ? "ol" : "ul";
          return (
            <ListTag key={`list-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`item-${index}-${itemIndex}`}>{renderInline(item.text, `inline-${index}-${itemIndex}`)}</li>
              ))}
            </ListTag>
          );
        }
        return <p key={`paragraph-${index}`}>{renderInline(block.lines.join(" "), `paragraph-${index}`)}</p>;
      })}
    </div>
  );
}
