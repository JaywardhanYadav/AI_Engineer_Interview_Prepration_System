/* Interview RAG Coach — frontend logic with PostgreSQL Conversations & Auth */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const state = {
  mode: "ask",
  topic: "All",
  difficulty: "medium",
  qaTopic: "All",
  qaDifficulty: "medium",
  qaCards: [],            // history of generated Q&A cards
  qaIndex: -1,            // current index in qaCards
  codingCategory: "All",
  codingDifficulty: "medium",
  codingCards: [],        // history of generated coding cards
  codingIndex: -1,        // current index in codingCards
  user: null,             // { id, username }
  conversations: [],      // list of user conversations
  activeConvId: null,     // active conversation id
  history: [],            // local chat turns
  current: null,          // current interview question
  timerId: null,
  startedAt: 0,
  authTab: "login",       // "login" | "register"
  stats: JSON.parse(localStorage.getItem("ivStats") || '{"answers":[],"asked":[]}'),
};

/* ---------------- helpers ---------------- */
async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 4500);
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function renderMarkdown(md, sources = []) {
  const html = DOMPurify.sanitize(marked.parse(md || ""));
  return html.replace(/\[(\d{1,2})\]/g, (m, n) => {
    const s = sources.find((x) => x.id === Number(n));
    return s ? `<span class="cite" title="${esc(s.source)} · p.${s.page}">${n}</span>` : m;
  });
}

function renderSources(sources) {
  if (!sources?.length) return "";
  return sources
    .map((s) => `<span class="src"><b>[${s.id}]</b>${esc(s.source)} · p.${s.page}
      <span class="tip">${esc(s.snippet)}…</span></span>`)
    .join("");
}

const scoreColor = (s) => (s >= 8 ? "var(--good)" : s >= 5 ? "var(--warn)" : "var(--bad)");

/* ---------------- Auth & User Profile ---------------- */
function openAuthModal(tab = "login") {
  state.authTab = tab;
  $("#auth-modal").classList.remove("hidden");
  $("#tab-login").classList.toggle("active", tab === "login");
  $("#tab-register").classList.toggle("active", tab === "register");
  $("#auth-submit").textContent = tab === "login" ? "Sign In" : "Register";
  $("#auth-err").classList.add("hidden");
  $("#auth-username").focus();
}

function closeAuthModal() {
  $("#auth-modal").classList.add("hidden");
  $("#auth-form").reset();
  $("#auth-err").classList.add("hidden");
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = $("#auth-username").value.trim();
  const password = $("#auth-password").value;
  const errEl = $("#auth-err");
  errEl.classList.add("hidden");

  const endpoint = state.authTab === "login" ? "/api/auth/login" : "/api/auth/register";
  try {
    const res = await api(endpoint, { username, password });
    state.user = res.user;
    updateUserUI();
    closeAuthModal();
    toast(`Welcome, ${state.user.username}!`);
    await loadConversations();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
}

async function logout() {
  try {
    await api("/api/auth/logout");
  } catch (_) {}
  state.user = null;
  state.conversations = [];
  state.activeConvId = null;
  updateUserUI();
  renderConversations();
  clearChatView();
  toast("Signed out");
}

function updateUserUI() {
  const userPill = $("#user-pill");
  const sidebarFooter = $("#sidebar-footer");
  if (state.user) {
    if (userPill) {
      userPill.classList.remove("hidden");
      $("#user-name").textContent = state.user.username;
    }
    if (sidebarFooter) {
      sidebarFooter.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;font-size:12.5px;">
        <span>👤 <b>${esc(state.user.username)}</b></span>
        <button class="btn-logout" id="sidebar-logout" title="Log out">Logout</button>
      </div>`;
      $("#sidebar-logout")?.addEventListener("click", logout);
    }
  } else {
    if (userPill) userPill.classList.add("hidden");
    if (sidebarFooter) {
      sidebarFooter.innerHTML = `<button class="btn ghost full-width" id="open-auth-btn">🔐 Sign In / Register</button>`;
      $("#open-auth-btn")?.addEventListener("click", () => openAuthModal("login"));
    }
  }
}

/* ---------------- Conversation Management (PostgreSQL) ---------------- */
async function loadConversations() {
  if (!state.user) {
    renderConversations();
    return;
  }
  try {
    state.conversations = await api("/api/conversations");
    renderConversations();
  } catch (e) {
    console.error("Failed to load conversations:", e);
  }
}

function renderConversations() {
  const list = $("#conv-list");
  if (!list) return;

  if (!state.user) {
    list.innerHTML = `<div class="conv-empty">Sign in to save and resume your chats</div>`;
    return;
  }

  if (state.conversations.length === 0) {
    list.innerHTML = `<div class="conv-empty">No saved chats yet. Start asking!</div>`;
    return;
  }

  list.innerHTML = state.conversations.map((c) => `
    <div class="conv-item ${c.id === state.activeConvId ? "active" : ""}" data-id="${c.id}">
      <span class="conv-item-title">${esc(c.title)}</span>
      <button class="conv-del-btn" data-id="${c.id}" title="Delete chat">✕</button>
    </div>
  `).join("");
}

async function selectConversation(convId) {
  state.activeConvId = convId;
  renderConversations();
  setMode("ask");

  try {
    const conv = await api(`/api/conversations/${convId}`);
    const thread = $("#thread");
    thread.innerHTML = "";
    state.history = [];

    if (!conv.messages || conv.messages.length === 0) {
      showEmptyAskState();
      return;
    }

    for (const m of conv.messages) {
      if (m.role === "user") {
        addMsg("user", esc(m.content));
      } else {
        const bot = addMsg("bot", `<div class="md">${renderMarkdown(m.content, m.sources)}</div>
          <div class="sources">${renderSources(m.sources)}</div>`);
      }
      state.history.push({ role: m.role, content: m.content });
    }
    state.history = state.history.slice(-10);
  } catch (e) {
    toast(`Failed to load chat: ${e.message}`);
  }
}

async function createNewChat() {
  state.activeConvId = null;
  state.history = [];
  renderConversations();
  clearChatView();
  showEmptyAskState();
  $("#ask-input")?.focus();
}

async function deleteConv(convId, e) {
  e.stopPropagation();
  if (!confirm("Delete this conversation?")) return;
  try {
    await fetch(`/api/conversations/${convId}`, { method: "DELETE" });
    state.conversations = state.conversations.filter((c) => c.id !== convId);
    if (state.activeConvId === convId) {
      createNewChat();
    } else {
      renderConversations();
    }
  } catch (err) {
    toast(`Delete failed: ${err.message}`);
  }
}

function clearChatView() {
  const thread = $("#thread");
  if (thread) thread.innerHTML = "";
}

function showEmptyAskState() {
  const thread = $("#thread");
  if (!thread || $("#ask-empty")) return;
  thread.innerHTML = `
    <div class="empty-state" id="ask-empty">
      <div class="empty-glow">✦</div>
      <h2>What do you want to master today?</h2>
      <p>Answers are grounded in your PDFs, with page citations.</p>
      <div class="suggestions">
        <button class="suggest">Explain RAG vs fine-tuning and when to use each</button>
        <button class="suggest">LoRA vs QLoRA vs full fine-tuning</button>
        <button class="suggest">What is the bias-variance trade-off?</button>
        <button class="suggest">How do multi-agent systems coordinate?</button>
      </div>
    </div>
  `;
  $$(".suggest").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));
}

/* ---------------- Status & Init ---------------- */
async function loadStatus() {
  try {
    const st = await api("/api/status");
    const pill = $("#model-pill");
    if (pill) pill.textContent = `${st.model} · ${st.reranker || "FlashRank"}`;

    const select = $("#topic-select");
    if (select) {
      select.innerHTML = `<option value="All">All Topics (${st.total_chunks.toLocaleString()} chunks)</option>` +
        Object.entries(st.topics).map(([t, n]) => `<option value="${esc(t)}">${esc(t)} (${n})</option>`).join("");
      select.value = state.topic;
    }

    const qaSelect = $("#qa-topic-select");
    if (qaSelect) {
      qaSelect.innerHTML = `<option value="All">All Topics</option>` +
        Object.entries(st.topics).map(([t, n]) => `<option value="${esc(t)}">${esc(t)} (${n})</option>`).join("");
      qaSelect.value = state.qaTopic;
    }

    if (st.user) {
      state.user = st.user;
      updateUserUI();
      await loadConversations();
    }
  } catch (e) {
    console.error("Status check failed:", e);
  }
}

/* ---------------- mode switching ---------------- */
function setMode(mode) {
  state.mode = mode;
  $$(".mode-btn").forEach((b) => {
    const on = b.dataset.mode === mode;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on);
  });
  $("#view-ask").classList.toggle("active", mode === "ask");
  $("#view-qa").classList.toggle("active", mode === "qa");
  $("#view-interview").classList.toggle("active", mode === "interview");
  $("#view-coding").classList.toggle("active", mode === "coding");
  $("#page-title").textContent =
    mode === "ask" ? "Ask & Learn" :
    mode === "qa" ? "Interview Q & A" :
    mode === "coding" ? "AI Engineer Coding" :
    "Mock Interview";
  $("#sidebar").classList.remove("open");

  if (mode === "qa") {
    if (state.qaCards.length === 0) {
      fetchQaCard();
    } else {
      renderQaCard();
    }
  } else if (mode === "coding") {
    if (state.codingCards.length === 0) {
      fetchCodingCard();
    } else {
      renderCodingCard();
    }
  }
}

/* ---------------- Ask mode ---------------- */
function addMsg(role, html) {
  $("#ask-empty")?.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = role === "user"
    ? `<div class="bubble">${html}</div>`
    : `<div class="avatar">◆</div><div class="bubble glass">${html}</div>`;
  $("#thread").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
  return el;
}

async function ask(question) {
  question = question.trim();
  if (!question) return;
  const input = $("#ask-input");
  input.value = "";
  autoGrow(input);
  $("#ask-send").disabled = true;

  addMsg("user", esc(question));
  const pending = addMsg("bot", `<div class="typing"><i></i><i></i><i></i></div>`);
  try {
    const res = await api("/api/ask", {
      question,
      topic: state.topic,
      history: state.history,
      conversation_id: state.activeConvId,
    });
    pending.querySelector(".bubble").innerHTML =
      `<div class="md">${renderMarkdown(res.answer, res.sources)}</div><div class="sources">${renderSources(res.sources)}</div>`;
    state.history.push({ role: "user", content: question }, { role: "assistant", content: res.answer });
    state.history = state.history.slice(-10);

    if (res.conversation_id && state.activeConvId !== res.conversation_id) {
      state.activeConvId = res.conversation_id;
      await loadConversations();
    }
  } catch (e) {
    pending.querySelector(".bubble").innerHTML = `<span style="color:var(--warn)">⚠ ${esc(e.message)}</span>`;
  } finally {
    $("#ask-send").disabled = false;
    pending.scrollIntoView({ behavior: "smooth", block: "end" });
  }
}

function autoGrow(t) {
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 180) + "px";
}

/* ---------------- Interview mode ---------------- */
function startTimer() {
  clearInterval(state.timerId);
  state.startedAt = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - state.startedAt) / 1000);
    $("#q-timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  };
  tick();
  state.timerId = setInterval(tick, 1000);
}

function showQuestion(q) {
  state.current = q;
  $("#iv-empty").classList.add("hidden");
  $("#result-card").classList.add("hidden");
  $("#q-card").classList.remove("hidden");
  $("#q-topic").textContent = q.topic || state.topic;
  $("#q-diff").textContent = q.difficulty;
  $("#q-concept").textContent = q.concept || "follow-up";
  $("#q-text").textContent = q.question;
  const ans = $("#answer-input");
  ans.value = "";
  ans.disabled = false;
  $("#submit-answer").disabled = false;
  $("#skip-btn").disabled = false;
  ans.focus();
  startTimer();
}

async function newQuestion() {
  const btn = $("#new-question");
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    const q = await api("/api/interview/question", {
      topic: state.topic, difficulty: state.difficulty, avoid: state.stats.asked.slice(-15),
    });
    state.stats.asked.push(q.question);
    state.stats.asked = state.stats.asked.slice(-50);
    localStorage.setItem("ivStats", JSON.stringify(state.stats));
    showQuestion(q);
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "✦ New question";
  }
}

async function submitAnswer(skip = false) {
  const q = state.current;
  if (!q) return;
  const answer = skip ? "" : $("#answer-input").value.trim();
  if (!skip && answer.length < 5) return toast("Write an answer first (or click Reveal answer).");

  clearInterval(state.timerId);
  const btn = skip ? $("#skip-btn") : $("#submit-answer");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = skip ? "Loading…" : "Grading…";
  $("#answer-input").disabled = true;
  try {
    const g = await api("/api/interview/grade", {
      question: q.question, answer, topic: q.topic || state.topic, difficulty: q.difficulty, seed_id: q.seed_id,
    });
    showResult(g, skip);
    if (!skip) {
      state.stats.answers.push({ topic: q.topic || "General", score: g.score, concept: q.concept, ts: Date.now() });
      localStorage.setItem("ivStats", JSON.stringify(state.stats));
    }
  } catch (e) {
    toast(e.message);
    $("#answer-input").disabled = false;
    btn.disabled = false;
  } finally {
    btn.textContent = label;
  }
}

function showResult(g, skipped) {
  const card = $("#result-card");
  card.classList.remove("hidden");
  const score = skipped ? 0 : g.score;
  const ring = $("#ring-fg");
  ring.style.stroke = scoreColor(score);
  ring.style.strokeDashoffset = 326.7;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    ring.style.strokeDashoffset = 326.7 * (1 - score / 10);
  }));
  animateNumber($("#score-val"), score);
  $("#verdict").textContent = skipped ? "Answer revealed — study the model answer below" : g.verdict;

  const list = (arr, empty) => arr?.length ? arr.map((x) => `<li>${esc(x)}</li>`).join("") : `<li class="none">${empty}</li>`;
  $("#strengths").innerHTML = skipped ? `<li class="none">—</li>` : list(g.strengths, "Nothing notable yet");
  $("#gaps").innerHTML = skipped ? `<li class="none">—</li>` : list(g.gaps, "No major gaps 🎉");
  $("#model-answer").innerHTML = renderMarkdown(g.model_answer, g.sources);
  $("#iv-sources").innerHTML = renderSources(g.sources);
  $("#follow-up").textContent = g.follow_up;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function animateNumber(el, to) {
  const start = performance.now();
  const step = (t) => {
    const p = Math.min((t - start) / 900, 1);
    el.textContent = Math.round(to * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ---------------- Event Listeners & Boot ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  marked.setOptions({ breaks: false, gfm: true });

  $$(".mode-btn").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  const select = $("#topic-select");
  if (select) {
    select.addEventListener("change", (e) => {
      state.topic = e.target.value;
    });
  }

  $$(".seg-btn").forEach((b) => b.addEventListener("click", () => {
    state.difficulty = b.dataset.diff;
    $$(".seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  }));

  const input = $("#ask-input");
  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); }
  });
  $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
  $$(".suggest").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));

  $("#new-question").addEventListener("click", newQuestion);
  $("#next-question").addEventListener("click", newQuestion);
  $("#submit-answer").addEventListener("click", () => submitAnswer(false));
  $("#skip-btn").addEventListener("click", () => submitAnswer(true));
  $("#answer-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey) submitAnswer(false);
  });
  $("#answer-followup").addEventListener("click", () => {
    const prev = state.current;
    showQuestion({
      question: $("#follow-up").textContent, concept: "follow-up",
      difficulty: prev?.difficulty || state.difficulty, topic: prev?.topic, seed_id: null,
    });
  });

  // Conversation list item clicks
  $("#conv-list").addEventListener("click", (e) => {
    const delBtn = e.target.closest(".conv-del-btn");
    if (delBtn) {
      deleteConv(Number(delBtn.dataset.id), e);
      return;
    }
    const item = e.target.closest(".conv-item");
    if (item) {
      selectConversation(Number(item.dataset.id));
    }
  });

  $("#new-chat-btn").addEventListener("click", createNewChat);

  // Auth Modal Listeners
  $("#tab-login").addEventListener("click", () => {
    state.authTab = "login";
    $("#tab-login").classList.add("active");
    $("#tab-register").classList.remove("active");
    $("#auth-submit").textContent = "Sign In";
    $("#auth-err").classList.add("hidden");
  });

  $("#tab-register").addEventListener("click", () => {
    state.authTab = "register";
    $("#tab-register").classList.add("active");
    $("#tab-login").classList.remove("active");
    $("#auth-submit").textContent = "Register";
    $("#auth-err").classList.add("hidden");
  });

  $("#open-auth-btn")?.addEventListener("click", () => openAuthModal("login"));
  $("#modal-close").addEventListener("click", closeAuthModal);
  $("#auth-modal").addEventListener("click", (e) => {
    if (e.target === $("#auth-modal")) closeAuthModal();
  });
  $("#auth-form").addEventListener("submit", handleAuthSubmit);
  $("#logout-btn")?.addEventListener("click", logout);

  // Q & A mode listeners
  const qaTopicSel = $("#qa-topic-select");
  if (qaTopicSel) {
    qaTopicSel.addEventListener("change", (e) => {
      state.qaTopic = e.target.value;
      fetchQaCard();
    });
  }

  $$("[data-qa-diff]").forEach((b) => b.addEventListener("click", () => {
    const newDiff = b.dataset.qaDiff;
    if (state.qaDifficulty !== newDiff) {
      state.qaDifficulty = newDiff;
      $$("[data-qa-diff]").forEach((x) => x.classList.toggle("active", x === b));
      fetchQaCard();
    }
  }));

  $("#qa-new-btn")?.addEventListener("click", () => fetchQaCard());
  $("#qa-start-btn")?.addEventListener("click", () => fetchQaCard());
  $("#qa-prev-btn")?.addEventListener("click", prevQa);
  $("#qa-next-btn")?.addEventListener("click", nextQa);

  // Coding mode listeners
  const codingCatSel = $("#coding-cat-select");
  if (codingCatSel) {
    codingCatSel.addEventListener("change", (e) => {
      state.codingCategory = e.target.value;
      fetchCodingCard();
    });
  }

  $$("[data-coding-diff]").forEach((b) => b.addEventListener("click", () => {
    const newDiff = b.dataset.codingDiff;
    if (state.codingDifficulty !== newDiff) {
      state.codingDifficulty = newDiff;
      $$("[data-coding-diff]").forEach((x) => x.classList.toggle("active", x === b));
      fetchCodingCard();
    }
  }));

  $("#coding-new-btn")?.addEventListener("click", () => fetchCodingCard());
  $("#coding-prev-btn")?.addEventListener("click", prevCoding);
  $("#coding-next-btn")?.addEventListener("click", nextCoding);
  $("#coding-copy-btn")?.addEventListener("click", copyCodingSolution);

  $("#toggle-sidebar").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  loadStatus();
});

/* ---------------- Q & A Practice Functions ---------------- */
function renderQaCard() {
  const empty = $("#qa-empty");
  const card = $("#qa-card");
  if (state.qaIndex < 0 || state.qaIndex >= state.qaCards.length) {
    empty?.classList.remove("hidden");
    card?.classList.add("hidden");
    return;
  }

  empty?.classList.add("hidden");
  card?.classList.remove("hidden");

  const cur = state.qaCards[state.qaIndex];
  $("#qa-topic-tag").textContent = cur.topic || "General";
  $("#qa-diff-tag").textContent = (cur.difficulty || "medium").toUpperCase();
  $("#qa-concept-tag").textContent = cur.concept || "Concept";
  $("#qa-counter").textContent = `${state.qaIndex + 1} / ${state.qaCards.length}`;
  $("#qa-question-text").textContent = cur.question;
  $("#qa-answer-text").innerHTML = renderMarkdown(cur.answer, cur.sources);
  $("#qa-sources").innerHTML = renderSources(cur.sources);

  const prevBtn = $("#qa-prev-btn");
  if (prevBtn) prevBtn.disabled = state.qaIndex <= 0;

  const nextBtn = $("#qa-next-btn");
  if (nextBtn) {
    nextBtn.disabled = false;
    nextBtn.textContent = state.qaIndex < state.qaCards.length - 1 ? "Next ➡️" : "Next (New) ➡️";
  }
  const indexLbl = $("#qa-index-lbl");
  if (indexLbl) indexLbl.textContent = `Card ${state.qaIndex + 1} of ${state.qaCards.length}`;
}

async function fetchQaCard() {
  const newBtn = $("#qa-new-btn");
  const startBtn = $("#qa-start-btn");
  const prevBtn = $("#qa-prev-btn");
  const nextBtn = $("#qa-next-btn");
  if (newBtn) { newBtn.disabled = true; newBtn.textContent = "Loading…"; }
  if (startBtn) { startBtn.disabled = true; startBtn.textContent = "Loading…"; }
  if (prevBtn) prevBtn.disabled = true;
  if (nextBtn) nextBtn.disabled = true;

  const empty = $("#qa-empty");
  const card = $("#qa-card");
  if (empty) empty.classList.add("hidden");
  if (card) card.classList.remove("hidden");

  $("#qa-topic-tag").textContent = state.qaTopic === "All" ? "All Topics" : state.qaTopic;
  $("#qa-diff-tag").textContent = state.qaDifficulty.toUpperCase();
  $("#qa-concept-tag").textContent = "Finding Question…";
  $("#qa-counter").textContent = `Card ${state.qaCards.length + 1}`;
  $("#qa-question-text").innerHTML = `<span class="loading-pulse">🔍 Finding an interview question from your study material...</span>`;
  $("#qa-answer-text").innerHTML = `
    <div class="qa-skeleton">
      <div class="typing" style="margin-bottom:12px;"><i></i><i></i><i></i></div>
      <p style="color:var(--muted); font-size:14px; line-height:1.6;">
        Generating student-friendly explanation with intuitive analogies, step-by-step breakdown, and exact PDF page citations...
      </p>
    </div>
  `;
  $("#qa-sources").innerHTML = `<span style="font-size:12px; color:var(--faint);">Searching citations in Weaviate...</span>`;
  const indexLbl = $("#qa-index-lbl");
  if (indexLbl) indexLbl.textContent = `Generating card ${state.qaCards.length + 1}...`;

  try {
    const cardData = await api("/api/qa/card", {
      topic: state.qaTopic,
      difficulty: state.qaDifficulty,
      avoid: state.qaCards.slice(-15).map((c) => c.question),
    });
    state.qaCards.push(cardData);
    state.qaIndex = state.qaCards.length - 1;
    renderQaCard();
  } catch (err) {
    $("#qa-question-text").textContent = "Could not load question";
    $("#qa-answer-text").innerHTML = `
      <div style="color:var(--bad); font-size:14.5px; padding:8px 0;">
        ⚠️ Error: ${esc(err.message)}
        <div style="margin-top:12px;">
          <button class="btn primary" id="qa-retry-btn">Try Again</button>
        </div>
      </div>
    `;
    $("#qa-retry-btn")?.addEventListener("click", () => fetchQaCard());
    toast(`Q&A generation failed: ${err.message}`);
  } finally {
    if (newBtn) { newBtn.disabled = false; newBtn.textContent = "✦ New Q&A"; }
    if (startBtn) { startBtn.disabled = false; startBtn.textContent = "✦ Start Practicing"; }
    if (prevBtn) prevBtn.disabled = state.qaIndex <= 0;
    if (nextBtn) nextBtn.disabled = false;
  }
}

function prevQa() {
  if (state.qaIndex > 0) {
    state.qaIndex--;
    renderQaCard();
  }
}

async function nextQa() {
  if (state.qaIndex < state.qaCards.length - 1) {
    state.qaIndex++;
    renderQaCard();
  } else {
    await fetchQaCard();
  }
}

/* ---------------- Coding Practice Functions ---------------- */
function renderCodingCard() {
  const card = $("#coding-card");
  if (state.codingIndex < 0 || state.codingIndex >= state.codingCards.length) {
    return;
  }

  const cur = state.codingCards[state.codingIndex];
  $("#coding-cat-tag").textContent = cur.category || "General";
  $("#coding-diff-tag").textContent = (cur.difficulty || "medium").toUpperCase();
  $("#coding-title-tag").textContent = "AI Engineer";
  $("#coding-counter").textContent = `Problem ${state.codingIndex + 1} / ${state.codingCards.length}`;

  $("#coding-problem-title").textContent = cur.title || "Coding Challenge";
  $("#coding-problem-text").innerHTML = renderMarkdown(cur.problem_statement, cur.sources);
  $("#coding-code-text").textContent = cur.code_solution || "# No code provided";
  $("#coding-explanation-text").innerHTML = renderMarkdown(cur.explanation, cur.sources);
  $("#coding-sources").innerHTML = renderSources(cur.sources);

  const prevBtn = $("#coding-prev-btn");
  if (prevBtn) prevBtn.disabled = state.codingIndex <= 0;

  const nextBtn = $("#coding-next-btn");
  if (nextBtn) {
    nextBtn.disabled = false;
    nextBtn.textContent = state.codingIndex < state.codingCards.length - 1 ? "Next ➡️" : "Next (New) ➡️";
  }
  const indexLbl = $("#coding-index-lbl");
  if (indexLbl) indexLbl.textContent = `Problem ${state.codingIndex + 1} of ${state.codingCards.length}`;
}

async function fetchCodingCard() {
  const newBtn = $("#coding-new-btn");
  const prevBtn = $("#coding-prev-btn");
  const nextBtn = $("#coding-next-btn");
  if (newBtn) { newBtn.disabled = true; newBtn.textContent = "Loading…"; }
  if (prevBtn) prevBtn.disabled = true;
  if (nextBtn) nextBtn.disabled = true;

  $("#coding-cat-tag").textContent = state.codingCategory === "All" ? "All Categories" : state.codingCategory;
  $("#coding-diff-tag").textContent = state.codingDifficulty.toUpperCase();
  $("#coding-title-tag").textContent = "Selecting Problem…";
  $("#coding-counter").textContent = `Problem ${state.codingCards.length + 1}`;
  $("#coding-problem-title").textContent = "Generating Interview Problem...";
  $("#coding-problem-text").innerHTML = `<span class="loading-pulse">🔍 Selecting a realistic AI Engineer coding challenge in ${esc(state.codingCategory)}...</span>`;
  $("#coding-code-text").textContent = "# Crafting production-quality Python solution with comments...";
  $("#coding-explanation-text").innerHTML = `
    <div class="qa-skeleton">
      <div class="typing" style="margin-bottom:12px;"><i></i><i></i><i></i></div>
      <p style="color:var(--muted); font-size:14px; line-height:1.6;">
        Generating student-friendly walkthrough with intuition, code breakdown, complexity, and interview tips...
      </p>
    </div>
  `;
  $("#coding-sources").innerHTML = `<span style="font-size:12px; color:var(--faint);">Searching citations in study material...</span>`;
  const indexLbl = $("#coding-index-lbl");
  if (indexLbl) indexLbl.textContent = `Generating problem ${state.codingCards.length + 1}...`;

  try {
    const cardData = await api("/api/coding/card", {
      category: state.codingCategory,
      difficulty: state.codingDifficulty,
      avoid: state.codingCards.slice(-15).map((c) => c.title),
    });
    state.codingCards.push(cardData);
    state.codingIndex = state.codingCards.length - 1;
    renderCodingCard();
  } catch (err) {
    $("#coding-problem-title").textContent = "Could not load problem";
    $("#coding-problem-text").innerHTML = `
      <div style="color:var(--bad); font-size:14.5px; padding:8px 0;">
        ⚠️ Error: ${esc(err.message)}
        <div style="margin-top:12px;">
          <button class="btn primary" id="coding-retry-btn">Try Again</button>
        </div>
      </div>
    `;
    $("#coding-retry-btn")?.addEventListener("click", () => fetchCodingCard());
    toast(`Coding challenge generation failed: ${err.message}`);
  } finally {
    if (newBtn) { newBtn.disabled = false; newBtn.textContent = "✦ New Problem"; }
    if (prevBtn) prevBtn.disabled = state.codingIndex <= 0;
    if (nextBtn) nextBtn.disabled = false;
  }
}

function prevCoding() {
  if (state.codingIndex > 0) {
    state.codingIndex--;
    renderCodingCard();
  }
}

async function nextCoding() {
  if (state.codingIndex < state.codingCards.length - 1) {
    state.codingIndex++;
    renderCodingCard();
  } else {
    await fetchCodingCard();
  }
}

function copyCodingSolution() {
  const cur = state.codingCards[state.codingIndex];
  if (!cur?.code_solution) return;
  navigator.clipboard.writeText(cur.code_solution).then(() => {
    const btn = $("#coding-copy-btn");
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "✓ Copied!";
      setTimeout(() => { btn.textContent = orig; }, 2000);
    }
  }).catch(() => {
    toast("Failed to copy code to clipboard");
  });
}
