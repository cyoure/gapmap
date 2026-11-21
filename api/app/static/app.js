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

async function loadStats() {
  const box = $("stats");
  try {
    const s = await (await fetch("/stats?limit=15")).json();
    if (!s.total_jobs) { box.innerHTML = '<p class="note">아직 저장된 공고가 없어요.</p>'; return; }
    box.innerHTML = `<p class="note">공고 ${s.total_jobs}개 기준</p>` + s.skills.map(k => `
      <div class="stat">
        <span class="name">${escapeHtml(k.name)}</span>
        <span class="bar"><i style="width:${k.percent}%"></i></span>
        <span class="pct">${k.jobs}곳 · ${k.percent}%</span>
        <button class="status ${k.my_status === "보유" ? "have" : "none"}" data-name="${escapeHtml(k.name)}"
          data-status="${k.my_status}" title="눌러서 상태 바꾸기 (PATCH /skills)">${k.my_status === "보유" ? "✅ 보유" : "❔ 근거 없음"}</button>
      </div>`).join("");
  } catch {
    box.innerHTML = '<p class="note">통계를 불러오지 못했어요.</p>';
  }
}

$("stats").onclick = async e => {
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

checkHealth();
loadStats();
