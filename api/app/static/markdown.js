// 리포트용 아주 작은 마크다운 변환기 (제목·표·목록·굵게·구분선).
// 외부 CDN을 쓰지 않는 이유: 시연장 네트워크와 무관하게 로컬에서만 동작하도록.
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inline(s) {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function tableRow(line, tag) {
  // "\|"는 셀 안의 글자 → 잠시 치환해서 칸 구분자와 헷갈리지 않게
  const cells = line.replace(/\\\|/g, "\u0000").replace(/^\||\|$/g, "").split("|");
  return "<tr>" + cells.map(c => `<${tag}>${inline(c.trim().replace(/\u0000/g, "|"))}</${tag}>`).join("") + "</tr>";
}

function renderMarkdown(text) {
  const out = [];
  let list = null;   // "ol" | "ul" | null
  let table = null;  // 표 행 버퍼
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const closeTable = () => {
    if (!table) return;
    const [head, ...body] = table.filter(r => !/^\|?\s*:?-{3,}/.test(r));
    out.push("<table><thead>" + tableRow(head, "th") + "</thead><tbody>" +
             body.map(r => tableRow(r, "td")).join("") + "</tbody></table>");
    table = null;
  };

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    if (line.startsWith("|")) { closeList(); (table ||= []).push(line); continue; }
    closeTable();

    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)/))) {
      closeList(); out.push(`<h${m[1].length + 1}>${inline(m[2])}</h${m[1].length + 1}>`);
    } else if ((m = line.match(/^\s*(\d+)\.\s+(.*)/)) || (m = line.match(/^\s*[-*]\s+(.*)/))) {
      const kind = m.length === 3 ? "ol" : "ul";
      if (list !== kind) { closeList(); out.push(`<${kind}>`); list = kind; }
      out.push(`<li>${inline(m[m.length - 1])}</li>`);
    } else if (/^-{3,}$/.test(line)) {
      closeList(); out.push("<hr>");
    } else if (/^\s*(🔧|↳)/.test(line)) {
      closeList(); out.push(`<div class="tool">${inline(line.trim())}</div>`);  // 에이전트 도구 호출 로그
    } else if (line.trim() === "") {
      closeList();
    } else {
      closeList(); out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList(); closeTable();
  return out.join("\n");
}
