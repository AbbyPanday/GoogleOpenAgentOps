// GoogleOpenAgentOps Reactive Client Controller (Crisp 2026 Edition)
const state = {
  currentSessionId: null,
  activeSessionData: null,
  activeSpan: null,
  waterfallFilter: "ALL",
  waterfallSearch: "",
  telemetryFilter: "ALL",
  eventSource: null,
  telemetryLogs: [],
  solutions: [],
  replayEvents: [],
  replayIndex: 0,
  replayPlaying: false,
  replayTimer: null,
  replaySpeed: 1,
  cicdEvents: []
};

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  setupEventListeners();
  loadContext();
  loadSolutions();
  loadSessions();
  loadPricingRegistry();
  loadCicdEvents();
  initLiveStream();
});

/* ==========================================================================
   1. Theme Management (Dual Theme: Dark / Light)
   ========================================================================== */
function initTheme() {
  const saved = localStorage.getItem("google_openagentops_theme") || "light";
  setTheme(saved);

  document.getElementById("btnThemeToggle")?.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
    showToast(`Switched to ${next === "dark" ? "Dark" : "Light"} Mode`);
  });
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("google_openagentops_theme", theme);
  const label = document.getElementById("themeLabel");
  if (label) {
    label.textContent = theme === "dark" ? "Dark" : "Light";
  }
}

/* ==========================================================================
   2. Toast Helper
   ========================================================================== */
function showToast(message) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

/* ==========================================================================
   3. Event Listeners
   ========================================================================== */
function setupEventListeners() {
  // Session selector
  document.getElementById("sessionSelect")?.addEventListener("change", (e) => {
    const sid = e.target.value;
    if (sid) {
      state.currentSessionId = sid;
      loadSessionDetails(sid);
      loadReplayEvents(sid);
    }
  });

  // Top Nav Buttons
  document.getElementById("btnAgentOpsConfig")?.addEventListener("click", () => {
    showToast("AgentOps OTel Exporter active: exporting OpenTelemetry & OpenInference spans");
  });
  document.getElementById("btnRefresh")?.addEventListener("click", () => {
    loadContext();
    loadSolutions();
    loadSessions();
    loadCicdEvents();
    if (state.currentSessionId) loadReplayEvents(state.currentSessionId);
    showToast("Telemetry Refreshed");
  });

  document.getElementById("btnExportJson")?.addEventListener("click", () => {
    if (state.currentSessionId) {
      window.open(`/api/agentops/export/${state.currentSessionId}`, "_blank");
      showToast("Downloading OpenTelemetry Trace JSON");
    } else {
      showToast("No active session selected");
    }
  });

  // Segmented Tabs
  document.querySelectorAll(".seg-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".seg-tab").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.dataset.tab;
      document.getElementById(targetId)?.classList.add("active");

      if (targetId === "tabReplay" && state.currentSessionId) {
        loadReplayEvents(state.currentSessionId);
      } else if (targetId === "tabCicd") {
        loadCicdEvents();
      }
    });
  });

  // Replay Player Controls
  document.getElementById("btnReplayPlay")?.addEventListener("click", () => toggleReplayPlay());
  document.getElementById("btnReplayPrev")?.addEventListener("click", () => stepReplay(-1));
  document.getElementById("btnReplayNext")?.addEventListener("click", () => stepReplay(1));
  document.getElementById("replaySlider")?.addEventListener("input", (e) => {
    pauseReplay();
    seekReplay(parseInt(e.target.value, 10));
  });

  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.replaySpeed = parseFloat(btn.dataset.speed) || 1;
      if (state.replayPlaying) {
        pauseReplay();
        startReplay();
      }
    });
  });

  // CI/CD Actions
  document.getElementById("btnRecordSampleDeploy")?.addEventListener("click", () => recordSampleDeploy());

  // Waterfall Filter & Search
  document.getElementById("wfKindFilter")?.addEventListener("change", (e) => {
    state.waterfallFilter = e.target.value;
    renderWaterfall();
  });

  document.getElementById("wfSearch")?.addEventListener("input", (e) => {
    state.waterfallSearch = e.target.value.toLowerCase();
    renderWaterfall();
  });

  // Telemetry Filter Chips
  document.querySelectorAll(".t-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".t-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.telemetryFilter = chip.dataset.filter;
      renderTelemetry();
    });
  });

  // Drawer Close Handlers
  const btnCloseDrawer = document.getElementById("btnCloseDrawer");
  const backdrop = document.getElementById("inspectorBackdrop");
  btnCloseDrawer?.addEventListener("click", () => closeDrawer());
  backdrop?.addEventListener("click", () => closeDrawer());
  document.getElementById("sheetDragHandle")?.addEventListener("click", () => closeDrawer());

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDrawer();
  });

  // Drawer Tabs
  document.querySelectorAll(".d-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".d-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".d-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      const targetId = tab.dataset.dtab;
      document.getElementById(targetId)?.classList.add("active");
    });
  });
}



function closeDrawer() {
  const drawer = document.getElementById("inspectorDrawer");
  const backdrop = document.getElementById("inspectorBackdrop");
  if (drawer) {
    drawer.classList.add("hidden");
    drawer.style.display = "none";
  }
  if (backdrop) backdrop.classList.add("hidden");
}

function openDrawer(span) {
  state.activeSpan = span;
  const drawer = document.getElementById("inspectorDrawer");
  const backdrop = document.getElementById("inspectorBackdrop");
  if (!drawer) return;

  const kind = (span.span_kind || span.kind || "AGENT").toUpperCase();
  document.getElementById("inspKind").textContent = kind;
  document.getElementById("inspKind").className = `kind-badge kind-${kind.toLowerCase()}`;
  document.getElementById("inspTitle").textContent = span.name;

  const m = span.metrics || {};
  const metaGrid = document.getElementById("inspMetaGrid");
  if (metaGrid) {
    metaGrid.innerHTML = `
      <div class="meta-item"><span class="meta-lbl">Span ID</span><span class="meta-v">${span.span_id || span.spanId || "span-1"}</span></div>
      <div class="meta-item"><span class="meta-lbl">Trace ID</span><span class="meta-v">${span.trace_id || span.traceId || "trace-1"}</span></div>
      <div class="meta-item"><span class="meta-lbl">Model</span><span class="meta-v">${span.model || "gemini-3.8-flash"}</span></div>
      <div class="meta-item"><span class="meta-lbl">Latency</span><span class="meta-v">${span.duration_ms || span.durationMs || 0}ms</span></div>
      <div class="meta-item"><span class="meta-lbl">Prompt Tokens</span><span class="meta-v">${(m.prompt_tokens || m.promptTokens || 0).toLocaleString()}</span></div>
      <div class="meta-item"><span class="meta-lbl">Output Tokens</span><span class="meta-v">${(m.completion_tokens || m.completionTokens || 0).toLocaleString()}</span></div>
      <div class="meta-item"><span class="meta-lbl">Total Tokens</span><span class="meta-v">${(m.total_tokens || m.totalTokens || 0).toLocaleString()}</span></div>
      <div class="meta-item"><span class="meta-lbl">Cost USD</span><span class="meta-v">$${(m.total_cost_usd || m.totalCostUsd || 0).toFixed(6)}</span></div>
      <div class="meta-item"><span class="meta-lbl">Status</span><span class="meta-v">${span.status || "OK"}</span></div>
    `;
  }

  document.getElementById("inspPromptPre").textContent = JSON.stringify(span.input || "No input prompt payload captured", null, 2);
  document.getElementById("inspThoughtPre").textContent = span.thought || "No internal chain-of-thought captured for this step.";
  document.getElementById("inspOutputPre").textContent = JSON.stringify(span.output || "No output payload", null, 2);
  document.getElementById("inspRawPre").textContent = JSON.stringify(span, null, 2);

  drawer.classList.remove("hidden");
  drawer.style.display = "flex";
  backdrop?.classList.remove("hidden");
}

/* ==========================================================================
   4. API Data Fetching & Sync
   ========================================================================== */
async function loadContext() {
  try {
    const res = await fetch("/api/agentops/context");
    if (!res.ok) return;
    const ctx = await res.json();

    const runtimeEl = document.getElementById("gcpRuntimeBadge");
    const projEl = document.getElementById("gcpProjectText");
    const linkTrace = document.getElementById("linkTraceConsole");
    const linkLogging = document.getElementById("linkLoggingConsole");

    if (runtimeEl) runtimeEl.textContent = ctx.runtime_type || "Local / Workstation";
    if (projEl) projEl.textContent = ctx.project_id || "Local Engine";

    if (ctx.console_trace_url && linkTrace) {
      linkTrace.href = ctx.console_trace_url;
      linkTrace.classList.remove("hidden");
    }
    if (ctx.console_logging_url && linkLogging) {
      linkLogging.href = ctx.console_logging_url;
      linkLogging.classList.remove("hidden");
    }
  } catch (e) {
    console.warn("Context fetch error:", e);
  }
}

async function loadSolutions() {
  try {
    const res = await fetch("/api/agentops/solutions");
    if (!res.ok) return;
    const data = await res.json();
    state.solutions = data.solutions || [];

    const pill = document.getElementById("solutionPillText");
    if (pill) {
      const count = state.solutions.length;
      pill.textContent = count > 0 ? `${count} ADK Solution${count > 1 ? "s" : ""}` : "0 Solutions";
    }

    const grid = document.getElementById("solutionsGrid");
    if (grid) {
      if (state.solutions.length === 0) {
        grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:32px;color:var(--text-muted);">No external ADK solutions registered yet. Use <code>GoogleADKTracker</code> to link multiple agent microservices.</div>';
      } else {
        grid.innerHTML = state.solutions.map(s => `
          <div class="solution-card">
            <div class="solution-card-head">
              <span class="solution-name">🤖 ${s.solution_name}</span>
              <span class="solution-model-tag">${s.default_model || "gemini-3.8-flash"}</span>
            </div>
            <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:8px;">
              Solution ID: <code>${s.solution_id}</code> | Project: <strong>${s.project_id || "Local"}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;font-size:0.75rem;color:var(--emerald);font-weight:600;">
              <span class="dot dot-emerald" style="width:6px;height:6px;"></span> Status: ${s.status || "ONLINE"}
            </div>
          </div>
        `).join("");
      }
    }
  } catch (e) {
    console.warn("Solutions fetch error:", e);
  }
}

async function loadSessions() {
  try {
    const res = await fetch("/api/agentops/sessions");
    if (!res.ok) return;
    const data = await res.json();
    const sessions = data.sessions || [];

    const select = document.getElementById("sessionSelect");
    if (!select) return;

    if (sessions.length === 0) {
      select.innerHTML = '<option value="">No Active Sessions (Run Python Agent)</option>';
      renderEmptyState();
      return;
    }

    select.innerHTML = sessions.map(s => `
      <option value="${s.session_id}" ${s.session_id === state.currentSessionId ? "selected" : ""}>
        ${s.session_name || s.session_id} (${s.spans ? s.spans.length : 0} spans)
      </option>
    `).join("");

    if (!state.currentSessionId && sessions.length > 0) {
      state.currentSessionId = sessions[0].session_id;
      loadSessionDetails(state.currentSessionId);
    } else if (state.currentSessionId) {
      loadSessionDetails(state.currentSessionId);
    }
  } catch (e) {
    console.error("Error loading sessions:", e);
  }
}

function renderEmptyState() {
  const grid = document.getElementById("agentNodesGrid");
  const handoffsSec = document.getElementById("handoffsContainer");
  const wfBody = document.getElementById("waterfallBody");

  if (grid) {
    grid.innerHTML = `
      <div class="empty-welcome-box">
        <div class="empty-icon">🤖</div>
        <div class="empty-title">Ready for AI Agent Observability</div>
        <p class="empty-desc">
          GoogleOpenAgentOps is actively listening for agent runs. Execute any instrumented Python script to stream live traces, agent state machines, and token economics.
        </p>
        <div class="empty-actions">
          <span class="empty-code-snippet">python examples/multi_solution_adk_agent.py</span>
        </div>
      </div>
    `;
  }

  if (handoffsSec) handoffsSec.style.display = "none";
  if (wfBody) {
    wfBody.innerHTML = '<div style="text-align:center;padding:32px;color:var(--text-muted);font-size:0.82rem;">No spans recorded yet. Run a Python agent to see the execution waterfall.</div>';
  }
}

async function loadSessionDetails(sessionId) {
  try {
    const res = await fetch(`/api/agentops/session/${sessionId}`);
    if (!res.ok) return;
    const data = await res.json();
    state.activeSessionData = data.session;

    updateMetricsCards(data.session.metrics || {});
    renderAgentNodes();
    renderHandoffs();
    renderWaterfall();
    renderTokenEconomics();
  } catch (e) {
    console.error("Error loading session details:", e);
  }
}

function updateMetricsCards(metrics) {
  const cost = metrics.total_cost_usd || metrics.totalCostUsd || 0;
  const tokens = metrics.total_tokens || metrics.totalTokens || 0;
  const spans = metrics.total_spans || metrics.totalSpans || 0;
  const hops = (state.activeSessionData?.handoffs || []).length;
  const lat = metrics.avg_latency_ms || metrics.avgLatencyMs || 0;

  const costEl = document.getElementById("metricCost");
  const tokEl = document.getElementById("metricTokens");
  const spanEl = document.getElementById("metricSpans");
  const hopEl = document.getElementById("metricHandoffs");
  const latEl = document.getElementById("metricLatency");

  if (costEl) costEl.textContent = `$${cost.toFixed(6)}`;
  if (tokEl) tokEl.textContent = tokens.toLocaleString();
  if (spanEl) spanEl.textContent = spans.toLocaleString();
  if (hopEl) hopEl.textContent = hops.toString();
  if (latEl) latEl.textContent = `${lat}ms`;

  const mCost = document.getElementById("miniCost");
  const mSpans = document.getElementById("miniSpans");
  const mLat = document.getElementById("miniLatency");
  if (mCost) mCost.textContent = `$${cost.toFixed(4)}`;
  if (mSpans) mSpans.textContent = `${spans} spans`;
  if (mLat) mLat.textContent = `${lat}ms`;
}

function renderAgentNodes() {
  const grid = document.getElementById("agentNodesGrid");
  const handoffsSec = document.getElementById("handoffsContainer");
  if (!grid) return;
  const spans = state.activeSessionData?.spans || [];

  if (spans.length === 0) {
    renderEmptyState();
    return;
  }

  if (handoffsSec) handoffsSec.style.display = "block";

  const agents = {};
  spans.forEach(s => {
    const name = s.agent_name || s.name;
    if (!agents[name]) {
      agents[name] = {
        name,
        role: s.agent_role || "Autonomous Agent",
        model: s.model || "gemini-3.8-flash",
        state: s.status === "ERROR" ? "FAILED" : "COMPLETED",
        spansCount: 0,
        tokens: 0,
        cost: 0,
        lastThought: s.thought || ""
      };
    }
    const a = agents[name];
    a.spansCount++;
    if (s.metrics) {
      a.tokens += s.metrics.total_tokens || 0;
      a.cost += s.metrics.total_cost_usd || 0;
    }
    if (s.thought) a.lastThought = s.thought;
  });

  grid.innerHTML = Object.values(agents).map(a => `
    <div class="agent-node-card">
      <div class="agent-card-head">
        <div>
          <div class="agent-card-name">🤖 ${a.name}</div>
          <div class="agent-card-role">${a.role}</div>
        </div>
        <span class="chip chip-${a.state === 'COMPLETED' ? 'done' : 'think'}">
          <span class="chip-dot"></span> ${a.state}
        </span>
      </div>
      <div class="agent-card-stats">
        <div class="agent-stat-item">Spans: <span>${a.spansCount}</span></div>
        <div class="agent-stat-item">Model: <span>${a.model}</span></div>
        <div class="agent-stat-item">Tokens: <span>${a.tokens.toLocaleString()}</span></div>
        <div class="agent-stat-item">Cost: <span>$${a.cost.toFixed(6)}</span></div>
      </div>
      ${a.lastThought ? `<div class="agent-thought-snippet">"${a.lastThought.slice(0, 110)}..."</div>` : ''}
    </div>
  `).join("");
}

function renderHandoffs() {
  const container = document.getElementById("handoffsList");
  if (!container) return;
  const handoffs = state.activeSessionData?.handoffs || [];

  if (handoffs.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">No multi-agent handoffs recorded yet in this session.</div>';
    return;
  }

  container.innerHTML = handoffs.map(h => `
    <div class="handoff-item">
      <span style="font-weight:700;">${h.from_agent}</span>
      <span class="handoff-arrow">➔ 🔀 ➔</span>
      <span style="font-weight:700;color:var(--google-blue);">${h.to_agent}</span>
      <span style="color:var(--text-muted);font-size:0.75rem;margin-left:auto;">${h.summary || "Cross-Solution Delegation"}</span>
    </div>
  `).join("");
}

function renderWaterfall() {
  const body = document.getElementById("waterfallBody");
  if (!body) return;
  const spans = state.activeSessionData?.spans || [];

  let filtered = spans;
  if (state.waterfallFilter !== "ALL") {
    filtered = filtered.filter(s => (s.span_kind || s.kind) === state.waterfallFilter);
  }
  if (state.waterfallSearch) {
    filtered = filtered.filter(s => 
      s.name.toLowerCase().includes(state.waterfallSearch) ||
      (s.agent_name && s.agent_name.toLowerCase().includes(state.waterfallSearch))
    );
  }

  if (filtered.length === 0) {
    body.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted);font-size:0.82rem;">No spans match the filter criteria.</div>';
    return;
  }

  const maxDur = Math.max(...spans.map(s => s.duration_ms || s.durationMs || 1), 1);

  body.innerHTML = filtered.map(s => {
    const dur = s.duration_ms || s.durationMs || 1;
    const pct = Math.max(8, Math.min(100, Math.round((dur / maxDur) * 100)));
    const kind = (s.span_kind || s.kind || "AGENT").toUpperCase();
    const cost = s.metrics ? (s.metrics.total_cost_usd || 0).toFixed(6) : "0.000000";
    const toks = s.metrics ? (s.metrics.total_tokens || 0) : 0;

    return `
      <div class="wf-row" onclick='handleSpanClick(${JSON.stringify(s.span_id || s.spanId)})'>
        <div class="wf-col-name">
          <span class="kind-badge kind-${kind.toLowerCase()}">${kind}</span>
          <span title="${s.name}">${s.name}</span>
        </div>
        <div class="wf-col-timeline">
          <div class="wf-bar-track">
            <div class="wf-bar-fill" style="width: ${pct}%;"></div>
          </div>
        </div>
        <div class="wf-col-model">${s.model || "gemini-3.8-flash"}</div>
        <div class="wf-col-tokens">${toks.toLocaleString()}</div>
        <div class="wf-col-cost">$${cost}</div>
        <div class="wf-col-dur">${dur}ms</div>
        <div class="wf-col-status">
          <span class="chip ${s.status === 'ERROR' ? 'chip-fail' : 'chip-done'}">${s.status || 'OK'}</span>
        </div>
      </div>
    `;
  }).join("");
}

window.handleSpanClick = function(spanId) {
  const spans = state.activeSessionData?.spans || [];
  const found = spans.find(s => (s.span_id || s.spanId) === spanId);
  if (found) openDrawer(found);
};

function renderTokenEconomics() {
  const wrap = document.getElementById("tokenBarsWrap");
  if (!wrap) return;
  const spans = state.activeSessionData?.spans || [];

  const agents = {};
  spans.forEach(s => {
    const name = s.agent_name || s.name;
    agents[name] = (agents[name] || 0) + (s.metrics ? s.metrics.total_tokens : 0);
  });

  const total = Object.values(agents).reduce((a, b) => a + b, 0) || 1;

  wrap.innerHTML = Object.entries(agents).map(([name, toks]) => {
    const pct = Math.round((toks / total) * 100);
    return `
      <div style="margin-bottom: 12px;">
        <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px;">
          <strong>${name}</strong>
          <span>${toks.toLocaleString()} toks (${pct}%)</span>
        </div>
        <div style="width:100%;height:8px;background:var(--bg-subtle);border-radius:4px;overflow:hidden;">
          <div style="width:${pct}%;height:100%;background:linear-gradient(90deg, var(--google-blue), var(--gemini-purple));border-radius:4px;"></div>
        </div>
      </div>
    `;
  }).join("");
}

async function loadPricingRegistry() {
  const container = document.getElementById("pricingList");
  if (!container) return;

  const models = [
    { id: "gemini-3.8-flash", name: "Gemini 3.8 Flash", inRate: 0.30, outRate: 1.20, role: "Complex Autonomous Reasoning, Architecture & Coding" },
    { id: "gemini-3.5-flash", name: "Gemini 3.5 Flash", inRate: 0.10, outRate: 0.40, role: "High-Velocity Workflows, Fast Edits & Unit Tests" },
    { id: "gemini-3.8-live",  name: "Gemini 3.8 Live",  inRate: 0.60, outRate: 2.40, role: "Real-Time Bidirectional Voice & Agent Orchestration" },
    { id: "gemini-3.1-flash-image", name: "Gemini 3.1 Flash Image", inRate: 0.50, outRate: 1.50, role: "Visual Inspection, Diagrams & Screenshot Analysis" }
  ];

  container.innerHTML = models.map(m => `
    <div class="pricing-item">
      <div>
        <div class="pricing-item-name">${m.name} <code>${m.id}</code></div>
        <div class="pricing-item-desc">${m.role}</div>
      </div>
      <div class="pricing-rates">
        <div>In: <strong>$${m.inRate.toFixed(2)}</strong> / M</div>
        <div>Out: <strong>$${m.outRate.toFixed(2)}</strong> / M</div>
      </div>
    </div>
  `).join("");
}

/* ==========================================================================
   5. Server-Sent Events (SSE) Live Telemetry Stream
   ========================================================================== */
function initLiveStream() {
  if (state.eventSource) state.eventSource.close();

  const liveText = document.getElementById("liveText");

  // Continuous auto-sync poller (2.5s)
  if (!state.pollInterval) {
    state.pollInterval = setInterval(() => {
      loadSessions();
      loadCicdEvents();
      if (state.currentSessionId) {
        loadSessionDetails(state.currentSessionId);
      }
    }, 2500);
  }

  try {
    state.eventSource = new EventSource("/api/agentops/stream");

    state.eventSource.onopen = () => {
      if (liveText) liveText.textContent = "Live Stream Active";
    };

    state.eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleStreamPayload(payload);
      } catch (err) {}
    };

    state.eventSource.onerror = () => {
      if (liveText) liveText.textContent = "Live Polling (2.5s)";
    };
  } catch (e) {
    console.warn("SSE stream error:", e);
    if (liveText) liveText.textContent = "Live Polling (2.5s)";
  }
}

function handleStreamPayload(payload) {
  if (!payload || !payload.type) return;

  state.telemetryLogs.unshift({
    type: payload.type,
    timestamp: payload.timestamp || Date.now(),
    data: payload.data || {}
  });

  if (state.telemetryLogs.length > 200) state.telemetryLogs.pop();
  renderTelemetry();

  const sid = payload.data?.session_id || payload.data?.sessionId;
  if (sid && !state.currentSessionId) {
    state.currentSessionId = sid;
  }

  loadSolutions();
  loadSessions();
  if (state.currentSessionId) {
    loadSessionDetails(state.currentSessionId);
  }
}

function renderTelemetry() {
  const logContainer = document.getElementById("telemetryLog");
  if (!logContainer) return;

  let filtered = state.telemetryLogs;
  if (state.telemetryFilter !== "ALL") {
    filtered = filtered.filter(l => l.type === state.telemetryFilter);
  }

  if (filtered.length === 0) {
    logContainer.innerHTML = '<div style="color:var(--text-muted);padding:14px;text-align:center;">Waiting for real-time agent telemetry events...</div>';
    return;
  }

  logContainer.innerHTML = filtered.slice(0, 50).map(l => {
    const timeStr = new Date(l.timestamp).toLocaleTimeString();
    return `
      <div class="log-entry">
        <div>
          <span class="log-entry-type">${l.type}</span>
          <div style="color:var(--text-body);margin-top:2px;">${formatTelemetrySnippet(l.data)}</div>
        </div>
        <span class="log-entry-time">${timeStr}</span>
      </div>
    `;
  }).join("");
}

function formatTelemetrySnippet(data) {
  if (!data) return "Event received";
  if (data.solution) return `Solution registered: <strong>${data.solution.solution_name}</strong> (${data.solution.solution_id})`;
  if (data.handoff) return `Handoff: ${data.handoff.from_agent} ➔ ${data.handoff.to_agent} (${data.handoff.summary || ''})`;
  if (data.name) return `Span: ${data.name} [${data.durationMs || 0}ms] Model: ${data.model || ''}`;
  if (data.sessionId) return `Session ID: <code>${data.sessionId}</code>`;
  return JSON.stringify(data).slice(0, 120);
}

/* ==========================================================================
   6. Session Replay Controller (AgentOps Parity)
   ========================================================================== */
async function loadReplayEvents(sessionId) {
  if (!sessionId) return;
  try {
    const res = await fetch(`/api/agentops/session/${sessionId}/replay`);
    if (!res.ok) return;
    const data = await res.json();
    state.replayEvents = data.events || [];
    state.replayIndex = 0;

    const slider = document.getElementById("replaySlider");
    const totalEl = document.getElementById("replayStepTotal");
    const numEl = document.getElementById("replayStepNum");

    const maxIdx = Math.max(0, state.replayEvents.length - 1);
    if (slider) {
      slider.max = maxIdx.toString();
      slider.value = "0";
    }
    if (totalEl) totalEl.textContent = state.replayEvents.length.toString();
    if (numEl) numEl.textContent = state.replayEvents.length > 0 ? "1" : "0";

    renderReplayTimeline();
    if (state.replayEvents.length > 0) {
      renderReplayStep(0);
    }
  } catch (e) {
    console.warn("Replay fetch error:", e);
  }
}

function renderReplayTimeline() {
  const container = document.getElementById("replayEventsList");
  if (!container) return;

  if (state.replayEvents.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎬</div>
        <p>No replay events recorded for this session yet.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = state.replayEvents.map((ev, idx) => {
    const timeStr = new Date(ev.timestamp * 1000).toLocaleTimeString();
    const isAct = idx === state.replayIndex;
    const kind = ev.event_type || "EVENT";
    let badgeClass = "rep-badge-agent";
    if (kind.includes("TOOL")) badgeClass = "rep-badge-tool";
    else if (kind.includes("THOUGHT")) badgeClass = "rep-badge-thought";
    else if (kind.includes("HANDOFF")) badgeClass = "rep-badge-handoff";
    else if (kind.includes("GUARDRAIL")) badgeClass = "rep-badge-guardrail";

    return `
      <div class="replay-event-row ${isAct ? 'active' : ''}" data-idx="${idx}">
        <span class="rep-step-num">#${idx + 1}</span>
        <span class="rep-badge ${badgeClass}">${kind}</span>
        <div class="rep-text-col">
          <div class="rep-title">${ev.title || ev.event_type}</div>
          <div class="rep-sub">${ev.agent_name ? '🤖 ' + ev.agent_name + ' • ' : ''}${ev.description || ''}</div>
        </div>
        <span class="rep-time">${timeStr}</span>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".replay-event-row").forEach(row => {
    row.addEventListener("click", () => {
      pauseReplay();
      const idx = parseInt(row.dataset.idx, 10);
      seekReplay(idx);
    });
  });
}

function renderReplayStep(idx) {
  state.replayIndex = idx;
  const slider = document.getElementById("replaySlider");
  const numEl = document.getElementById("replayStepNum");
  if (slider) slider.value = idx.toString();
  if (numEl) numEl.textContent = (idx + 1).toString();

  document.querySelectorAll(".replay-event-row").forEach((r, i) => {
    if (i === idx) {
      r.classList.add("active");
      r.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
      r.classList.remove("active");
    }
  });

  const card = document.getElementById("replaySnapshotCard");
  if (!card) return;
  const ev = state.replayEvents[idx];
  if (!ev) {
    card.innerHTML = '<div class="empty-state"><p>No event data</p></div>';
    return;
  }

  const kind = ev.event_type || "EVENT";
  const payloadStr = JSON.stringify(ev.payload || {}, null, 2);

  card.innerHTML = `
    <div class="snapshot-header">
      <span class="kind-badge">${kind}</span>
      <h4 style="margin:0;font-size:1.05rem;color:var(--text-heading);">${ev.title || kind}</h4>
      <span style="font-size:0.75rem;color:var(--text-muted);margin-left:auto;">${ev.iso_timestamp || ''}</span>
    </div>
    <div class="snapshot-meta-row">
      <div>Agent: <strong>${ev.agent_name || 'Workflow'}</strong></div>
      <div>Description: <span style="color:var(--text-body);">${ev.description || 'N/A'}</span></div>
    </div>
    <div class="snapshot-body">
      <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px;">Event Payload & Execution Context:</div>
      <pre class="code-box" style="max-height:280px;overflow:auto;">${payloadStr}</pre>
    </div>
  `;
}

function toggleReplayPlay() {
  if (state.replayPlaying) {
    pauseReplay();
  } else {
    startReplay();
  }
}

function startReplay() {
  if (state.replayEvents.length === 0) return;
  state.replayPlaying = true;
  const btn = document.getElementById("btnReplayPlay");
  if (btn) btn.textContent = "⏸ Pause";

  const delay = Math.max(250, 1000 / (state.replaySpeed || 1));
  state.replayTimer = setInterval(() => {
    if (state.replayIndex < state.replayEvents.length - 1) {
      renderReplayStep(state.replayIndex + 1);
    } else {
      pauseReplay();
    }
  }, delay);
}

function pauseReplay() {
  state.replayPlaying = false;
  if (state.replayTimer) {
    clearInterval(state.replayTimer);
    state.replayTimer = null;
  }
  const btn = document.getElementById("btnReplayPlay");
  if (btn) btn.textContent = "▶ Play";
}

function stepReplay(delta) {
  pauseReplay();
  const nextIdx = Math.max(0, Math.min(state.replayEvents.length - 1, state.replayIndex + delta));
  seekReplay(nextIdx);
}

function seekReplay(index) {
  if (index >= 0 && index < state.replayEvents.length) {
    renderReplayStep(index);
  }
}

/* ==========================================================================
   7. CI/CD Pipeline & Cloud Run Deployments Controller
   ========================================================================== */
async function loadCicdEvents() {
  try {
    const res = await fetch("/api/agentops/cicd");
    if (!res.ok) return;
    const data = await res.json();
    state.cicdEvents = data.events || [];
    renderCicd();
  } catch (e) {
    console.warn("CI/CD fetch error:", e);
  }
}

function renderCicd() {
  const totalEl = document.getElementById("cicdTotal");
  const succEl = document.getElementById("cicdSuccess");
  const failEl = document.getElementById("cicdFailed");
  const provEl = document.getElementById("cicdProvider");
  const tbody = document.getElementById("cicdTableBody");

  const total = state.cicdEvents.length;
  const passing = state.cicdEvents.filter(e => e.status === "SUCCESS").length;
  const failed = state.cicdEvents.filter(e => e.status === "FAILURE").length;

  if (totalEl) totalEl.textContent = total.toString();
  if (succEl) succEl.textContent = passing.toString();
  if (failEl) failEl.textContent = failed.toString();

  if (tbody) {
    if (total === 0) {
      tbody.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🚀</div>
          <p>No CI/CD pipeline events logged yet. Connect GitHub Actions or Cloud Build to view pipeline traces.</p>
        </div>
      `;
      return;
    }

    tbody.innerHTML = state.cicdEvents.map(e => `
      <div class="cicd-tr">
        <div class="cicd-td"><strong>${e.pipeline_name}</strong> <span class="cicd-prov-tag">${e.provider}</span></div>
        <div class="cicd-td"><code>${e.run_id}</code></div>
        <div class="cicd-td"><code>${e.branch}</code> • <span style="font-family:monospace;font-size:0.75rem;">${(e.commit_sha || '').slice(0, 7)}</span></div>
        <div class="cicd-td"><span class="badge-env">${e.environment}</span></div>
        <div class="cicd-td">${e.duration_ms}ms</div>
        <div class="cicd-td">
          <span class="badge-status badge-${(e.status || 'SUCCESS').toLowerCase()}">${e.status}</span>
        </div>
        <div class="cicd-td" style="color:var(--text-muted);font-size:0.75rem;">${e.iso_timestamp ? new Date(e.iso_timestamp).toLocaleTimeString() : 'N/A'}</div>
      </div>
    `).join("");
  }
}

async function recordSampleDeploy() {
  try {
    const payload = {
      pipeline_name: "Google Cloud Build • ADK Swarm Release",
      run_id: "build-" + Math.floor(1000 + Math.random() * 9000),
      commit_sha: "a1b2c3d" + Math.floor(100 + Math.random() * 900),
      branch: "main",
      status: "SUCCESS",
      duration_ms: Math.floor(1800 + Math.random() * 2500),
      environment: "production",
      provider: "cloud-build",
      details: {
        target: "Cloud Run Service: google-openagentops-server",
        region: "us-central1",
        container: "gcr.io/google-adk-observatory/agentops:v2.0.0"
      }
    };
    const res = await fetch("/api/agentops/cicd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast("Deployment event recorded successfully!");
      loadCicdEvents();
    }
  } catch (e) {
    showToast("Failed to record deploy event");
  }
}
