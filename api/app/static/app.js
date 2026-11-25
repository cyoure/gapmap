// 화면 동작: 스트리밍 리포트 받기, 후속 질문, 통계·상태 수정. 계산은 전부 서버(api) 몫.
const $ = id => document.getElementById(id);
let controller = null;  // 진행 중인 요청 중단용
let threadId = null;    // 에이전트 대화 id → 후속 질문 때 같은 메모리 사용
let shown = "";         // 지금 화면에 그려진 원문 (후속 답변을 이어 붙이기 위해)

async function checkHealth() {
  try {
    const h = await (await fetch("/health")).json();
    const ok = h.ollama === "ok" && h.chroma === "ok";
    $("health").textContent = ok ? `● 연결됨 · ${h.model}` : `● 일부 서비스 문제 (ollama: ${h.ollama}, chroma: ${h.chroma})`;
    $("health").className = "badge " + (ok ? "ok" : "bad");
  } catch {
    $("health").textContent = "● api 연결 안 됨";
    $("health").className = "badge bad";
  }
}

function setBusy(busy) {
  for (const id of ["btn-report", "btn-agent"]) $(id).disabled = busy;
  $("btn-stop").disabled = !busy;
  $("chat").querySelector("button").disabled = busy;
}

// fetch 응답 본문을 조각(chunk)이 도착하는 대로 읽어 화면에 다시 그린다 — StreamingResponse의 짝
async function streamInto(url, body, prefix = "") {
  controller = new AbortController();
  setBusy(true);
  const out = $("output");
  out.classList.remove("empty");
  let text = prefix;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    if (res.headers.get("X-Thread-Id")) threadId = res.headers.get("X-Thread-Id");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
      out.innerHTML = renderMarkdown(text);
      out.scrollTop = out.scrollHeight;
    }
  } catch (e) {
    text += e.name === "AbortError" ? "\n\n[중단됨]\n" : `\n\n[오류] ${e.message}\n`;
    out.innerHTML = renderMarkdown(text);
  } finally {
    shown = text;
    setBusy(false);
    controller = null;
  }
}

async function runReport(url) {
  const posting = $("posting").value.trim();
  if (!posting) { $("posting").focus(); return; }
  threadId = null;
  $("chat").hidden = true;
  await streamInto(url, { text: posting });
  $("chat").hidden = !threadId;  // 에이전트 분석일 때만 후속 질문 가능
  loadStats();
}

$("btn-report").onclick = () => runReport("/gap/report");
$("btn-agent").onclick = () => runReport("/agent/report");
$("btn-stop").onclick = () => controller?.abort();

$("chat").onsubmit = async e => {
  e.preventDefault();
  const q = $("chat-input").value.trim();
  if (!q || !threadId) return;
  $("chat-input").value = "";
  // 앞의 리포트 아래에 질문·답변을 이어 붙인다
  await streamInto("/agent/chat", { thread_id: threadId, message: q }, shown + `\n\n---\n\n**🙋 ${q}**\n\n`);
};

// 숨기기/되돌리기 아이콘 (선 아이콘, 글자색을 따라감)
const svg = d => `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON_HIDE = svg('<path d="M10.7 5.1A10.4 10.4 0 0 1 12 5c5 0 9 4.5 10 7a13 13 0 0 1-2.2 3.2M6.6 6.6C4.4 8 2.8 10.2 2 12c1 2.5 5 7 10 7 1.9 0 3.6-.6 5.1-1.5"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="M3 3l18 18"/>');
const ICON_SHOW = svg('<path d="M2 12c1-2.5 5-7 10-7s9 4.5 10 7c-1 2.5-5 7-10 7S3 14.5 2 12z"/><circle cx="12" cy="12" r="3"/>');

async function loadStats() {
  const box = $("stats");
  try {
    const s = await (await fetch("/stats?limit=15")).json();
    if (!s.total_jobs) { box.innerHTML = '<p class="note">아직 저장된 공고가 없어요.</p>'; return; }
    box.innerHTML = `<p class="note">공고 ${s.total_jobs}개 기준</p>` + s.skills.map(k => `
      <div class="stat">
        <span class="name" title="${escapeHtml(k.name)}">${escapeHtml(k.name)}</span>
        <span class="bar"><i style="width:${k.percent}%"></i></span>
        <span class="pct">${k.jobs}곳 · ${k.percent}%</span>
        <button class="status ${k.my_status === "보유" ? "have" : "none"}" data-name="${escapeHtml(k.name)}"
          data-status="${k.my_status}" title="눌러서 상태 바꾸기 (PATCH /skills)">${k.my_status === "보유" ? "✅ 보유" : "❔ 근거 없음"}</button>
        <button class="hide" data-name="${escapeHtml(k.name)}" title="기술이 아니면 통계에서 숨기기 (PUT /hidden-skills)" aria-label="숨기기">${ICON_HIDE}</button>
      </div>`).join("")
      + (s.hidden?.length ? `<div class="hidden-list"><span class="note">숨긴 항목 · 눌러서 되돌리기</span>` + s.hidden.map(n =>
          `<button class="unhide" data-name="${escapeHtml(n)}" title="다시 보이기">${ICON_SHOW}<span>${escapeHtml(n)}</span></button>`).join("") + "</div>" : "");
  } catch {
    box.innerHTML = '<p class="note">통계를 불러오지 못했어요.</p>';
  }
}

$("stats").onclick = async e => {
  const hide = e.target.closest("button.hide, button.unhide");
  if (hide) {
    const name = hide.dataset.name, unhide = hide.classList.contains("unhide");
    if (!unhide && !confirm(`'${name}'을(를) 통계에서 숨길까요?\n기술이 아닌 항목(OCR 잡음·자격증 등)일 때 쓰세요. 다음 분석부터 점수에서도 빠지고, 아래 '숨긴 항목'에서 되돌릴 수 있어요.`)) return;
    await fetch(`/hidden-skills/${encodeURIComponent(name)}`, { method: unhide ? "DELETE" : "PUT" });
    loadStats();
    return;
  }
  const b = e.target.closest("button.status");
  if (!b) return;
  const next = b.dataset.status === "보유" ? "근거 없음" : "보유";
  if (!confirm(`'${b.dataset.name}' 상태를 '${next}'(으)로 바꿀까요?`)) return;
  await fetch(`/skills/${encodeURIComponent(b.dataset.name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: next }),
  });
  loadStats();
};
$("btn-stats").onclick = loadStats;

// 복사가 안 되는 공고: 이미지·PDF → 서버 OCR → 입력창에 채움. 바로 분석하지 않고 사용자가 확인·수정
async function ocr(file) {
  const status = $("ocr-status");
  status.textContent = "⏳ 글자 읽는 중…";
  const form = new FormData();
  form.append("file", file, file.name || "image.png");
  try {
    const res = await fetch("/jobs/ocr", { method: "POST", body: form });
    const r = await res.json();
    if (!res.ok) throw new Error(r.detail || res.status);
    const box = $("posting");
    box.value = box.value.trim() ? box.value.trimEnd() + "\n\n" + r.text : r.text;  // 여러 장 캡처하면 이어 붙임
    status.textContent = `✅ ${r.chars}자 추출 (${r.method === "ocr" ? "OCR" : "PDF 텍스트"}) — 기술명 오타를 확인·수정한 뒤 분석하세요`;
  } catch (e) {
    status.textContent = `❌ ${e.message}`;
  }
}

$("file").onchange = e => { if (e.target.files[0]) ocr(e.target.files[0]); e.target.value = ""; };
$("posting").addEventListener("paste", e => {  // 캡처 도구로 찍고 Ctrl+V
  const img = [...e.clipboardData.files].find(f => f.type.startsWith("image/"));
  if (img) { e.preventDefault(); ocr(img); }
});

checkHealth();
loadStats();
