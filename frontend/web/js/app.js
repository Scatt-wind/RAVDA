import { ApiError, createApiClient } from "./api.js";

const RAG_STATUS_LABELS = {
  pending: "待索引",
  indexing: "索引中",
  ready: "已就绪",
  failed: "失败",
  skipped: "已跳过",
};

const STORAGE_KEY = "ravda.activeDatasetId";

const state = {
  api: null,
  pollIntervalSec: 4,
  pollTimer: null,
  lastSessionStamp: "",
  selectedFile: null,
  datasetId: null,
  profile: null,
  ragStatus: null,
};

function $(id) {
  return document.getElementById(id);
}

function setHidden(element, hidden) {
  if (!element) {
    return;
  }
  element.classList.toggle("hidden", hidden);
}

function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  return String(value).replace("T", " ").slice(0, 19);
}

function ragBadgeClass(status) {
  if (status === "ready") {
    return "badge-ok";
  }
  if (status === "failed") {
    return "badge-error";
  }
  if (status === "indexing" || status === "pending") {
    return "badge-warn";
  }
  return "badge-muted";
}

function resultToRows(result) {
  if (result == null) {
    return null;
  }
  if (Array.isArray(result)) {
    if (result.length === 0) {
      return { headers: ["结果"], rows: [] };
    }
    if (result.every((row) => row && typeof row === "object" && !Array.isArray(row))) {
      const headers = Object.keys(result[0]);
      return {
        headers,
        rows: result.map((row) => headers.map((key) => row[key])),
      };
    }
    return {
      headers: ["value"],
      rows: result.map((value) => [value]),
    };
  }
  if (typeof result === "object") {
    const headers = Object.keys(result);
    return {
      headers,
      rows: [headers.map((key) => result[key])],
    };
  }
  return {
    headers: ["结果"],
    rows: [[result]],
  };
}

function renderTable(tableEl, wrapEl, result) {
  const parsed = resultToRows(result);
  tableEl.innerHTML = "";
  if (!parsed || parsed.rows.length === 0) {
    setHidden(wrapEl, true);
    return;
  }

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  parsed.headers.forEach((header) => {
    const th = document.createElement("th");
    th.textContent = String(header);
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  parsed.rows.forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((cell) => {
      const td = document.createElement("td");
      td.textContent = cell == null ? "" : String(cell);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  tableEl.appendChild(thead);
  tableEl.appendChild(tbody);
  setHidden(wrapEl, false);
}

function renderCharts(container, charts) {
  container.innerHTML = "";
  if (!Array.isArray(charts) || charts.length === 0) {
    return;
  }

  charts.forEach((chart, index) => {
    try {
      const img = document.createElement("img");
      const format = chart.format || "png";
      img.src = `data:image/${format};base64,${chart.data || ""}`;
      img.alt = `分析图表 ${index + 1}`;
      container.appendChild(img);
    } catch (_error) {
      const note = document.createElement("p");
      note.className = "error-text";
      note.textContent = `图表 ${index + 1} 无法显示`;
      container.appendChild(note);
    }
  });
}

function renderLatestTurn(session) {
  const emptyEl = $("results-empty");
  const contentEl = $("results-content");
  const metaEl = $("results-meta");
  const questionEl = $("turn-question");
  const summaryEl = $("turn-summary");
  const errorEl = $("turn-error");
  const tableWrap = $("turn-table-wrap");
  const tableEl = $("turn-table");
  const chartsEl = $("turn-charts");

  if (!session || !Array.isArray(session.turns) || session.turns.length === 0) {
    setHidden(emptyEl, false);
    setHidden(contentEl, true);
    metaEl.textContent = "";
    return;
  }

  const turn = session.turns[session.turns.length - 1];
  setHidden(emptyEl, true);
  setHidden(contentEl, false);

  questionEl.textContent = turn.question || "";
  summaryEl.textContent = turn.summary || "";
  metaEl.textContent = `会话 ${session.session_id.slice(0, 8)}… · 更新 ${formatDateTime(session.updated_at)}`;

  if (turn.success === false) {
    errorEl.textContent = turn.error || "执行失败";
    setHidden(errorEl, false);
  } else {
    errorEl.textContent = "";
    setHidden(errorEl, true);
  }

  renderTable(tableEl, tableWrap, turn.result);
  renderCharts(chartsEl, turn.charts);
}

async function refreshLatestResults() {
  if (!state.datasetId || !state.api) {
    renderLatestTurn(null);
    return;
  }

  try {
    const payload = await state.api.getLatestSession(state.datasetId);
    const session = payload?.session;
    const stamp = session ? `${session.session_id}:${session.updated_at}:${session.turns?.length || 0}` : "";
    if (stamp !== state.lastSessionStamp) {
      state.lastSessionStamp = stamp;
      renderLatestTurn(session);
    }
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      renderLatestTurn(null);
      state.lastSessionStamp = "";
      return;
    }
    console.warn("刷新分析结果失败:", error);
  }
}

function startPolling() {
  stopPolling();
  state.pollTimer = window.setInterval(() => {
    refreshLatestResults().catch(() => {});
  }, state.pollIntervalSec * 1000);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function applyDatasetDetail(detail) {
  const profile = detail?.profile;
  if (!profile?.dataset_id) {
    return;
  }

  state.datasetId = profile.dataset_id;
  state.profile = profile;
  state.ragStatus = detail.rag_index_status || null;
  state.lastSessionStamp = "";
  localStorage.setItem(STORAGE_KEY, state.datasetId);

  $("metric-rows").textContent = String(profile.row_count ?? "—");
  $("metric-cols").textContent = String(profile.column_count ?? "—");
  $("metric-filename").textContent = profile.filename || "";
  $("dataset-id").textContent = profile.dataset_id;
  setHidden($("current-dataset-panel"), false);
  updateRagBadge(state.ragStatus);

  renderDatasetList();
  refreshLatestResults().catch(() => {});
}

function updateRagBadge(status) {
  const badge = $("rag-badge");
  const label = RAG_STATUS_LABELS[status] || status || "未知";
  badge.textContent = `RAG ${label}`;
  badge.className = `badge ${ragBadgeClass(status)}`;
}

async function loadDatasets() {
  const listEl = $("dataset-list");
  listEl.innerHTML = `<p class="hint">加载中…</p>`;

  try {
    const payload = await state.api.listDatasets(10);
    const datasets = payload?.datasets || [];
    renderDatasetList(datasets);
  } catch (error) {
    listEl.innerHTML = `<p class="error-text">${error.message || "加载失败"}</p>`;
  }
}

function renderDatasetList(datasets) {
  const listEl = $("dataset-list");
  if (!datasets) {
    loadDatasets().catch(() => {});
    return;
  }

  if (datasets.length === 0) {
    listEl.innerHTML = `<p class="hint">暂无历史记录</p>`;
    return;
  }

  listEl.innerHTML = "";
  datasets.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dataset-item";
    if (item.dataset_id === state.datasetId) {
      button.classList.add("active");
    }

    const title = document.createElement("p");
    title.className = "dataset-item-title";
    title.textContent = item.original_filename || "未知文件";

    const meta = document.createElement("p");
    meta.className = "dataset-item-meta";
    meta.textContent = `${item.row_count}×${item.column_count} · ${formatFileSize(item.file_size_bytes || 0)}`;

    const time = document.createElement("p");
    time.className = "dataset-item-time";
    time.textContent = formatDateTime(item.created_at);

    button.appendChild(title);
    button.appendChild(meta);
    button.appendChild(time);

    button.addEventListener("click", async () => {
      try {
        const detail = await state.api.getDataset(item.dataset_id);
        applyDatasetDetail(detail);
      } catch (error) {
        $("upload-message").textContent = error.message || "切换数据集失败";
        $("upload-message").className = "error-text";
      }
    });

    listEl.appendChild(button);
  });
}

async function checkHealth() {
  const badge = $("health-badge");
  try {
    const health = await state.api.health();
    badge.textContent = health.rag_configured ? "已连接 · RAG 已配置" : "已连接";
    badge.className = "badge badge-ok";
  } catch (error) {
    badge.textContent = error.message || "连接失败";
    badge.className = "badge badge-error";
  }
}

function setupDifyIframe(embedUrl) {
  const iframe = $("dify-iframe");
  const loading = $("iframe-loading");
  const errorEl = $("iframe-error");

  if (!embedUrl) {
    setHidden(loading, true);
    errorEl.textContent = "未配置 DIFY_EMBED_URL，请在 .env 中设置 Dify 嵌入地址。";
    setHidden(errorEl, false);
    return;
  }

  iframe.addEventListener("load", () => {
    setHidden(loading, true);
  });

  iframe.addEventListener("error", () => {
    setHidden(loading, true);
    errorEl.textContent = "Agent 加载失败，请确认 Dify 已启动且允许 iframe 嵌入。";
    setHidden(errorEl, false);
  });

  iframe.src = embedUrl;
}

function bindEvents() {
  const fileInput = $("file-input");
  const fileLabel = $("file-label");
  const uploadBtn = $("upload-btn");
  const uploadMessage = $("upload-message");

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0] || null;
    state.selectedFile = file;
    uploadBtn.disabled = !file;
    fileLabel.textContent = file ? file.name : "选择 CSV / Excel";
    uploadMessage.textContent = "";
    uploadMessage.className = "hint";
  });

  uploadBtn.addEventListener("click", async () => {
    if (!state.selectedFile) {
      return;
    }

    uploadBtn.disabled = true;
    uploadMessage.textContent = "上传中…";
    uploadMessage.className = "hint";

    try {
      const data = await state.api.uploadDataset(state.selectedFile);
      applyDatasetDetail(data);
      uploadMessage.textContent = data.deduplicated
        ? "该文件已上传过，已加载历史数据集"
        : "上传成功，已生成数据画像";
      uploadMessage.className = "hint";
      await loadDatasets();
    } catch (error) {
      uploadMessage.textContent = error.message || "上传失败";
      uploadMessage.className = "error-text";
    } finally {
      uploadBtn.disabled = !state.selectedFile;
    }
  });

  $("refresh-datasets-btn").addEventListener("click", () => {
    loadDatasets().catch(() => {});
  });

  $("copy-id-btn").addEventListener("click", async () => {
    if (!state.datasetId) {
      return;
    }
    try {
      await navigator.clipboard.writeText(state.datasetId);
      $("copy-id-btn").textContent = "已复制";
      window.setTimeout(() => {
        $("copy-id-btn").textContent = "复制 ID";
      }, 1500);
    } catch (_error) {
      window.prompt("复制 dataset_id", state.datasetId);
    }
  });

  $("refresh-rag-btn").addEventListener("click", async () => {
    if (!state.datasetId) {
      return;
    }
    try {
      const rag = await state.api.getRagStatus(state.datasetId);
      state.ragStatus = rag.rag_index_status;
      updateRagBadge(state.ragStatus);
      if (rag.rag_index_error) {
        $("upload-message").textContent = rag.rag_index_error;
        $("upload-message").className = "error-text";
      }
    } catch (error) {
      $("upload-message").textContent = error.message || "刷新 RAG 状态失败";
      $("upload-message").className = "error-text";
    }
  });

  $("reindex-rag-btn").addEventListener("click", async () => {
    if (!state.datasetId) {
      return;
    }
    try {
      const rag = await state.api.reindexRag(state.datasetId);
      state.ragStatus = rag.rag_index_status;
      updateRagBadge(state.ragStatus);
      $("upload-message").textContent = "已触发重新索引";
      $("upload-message").className = "hint";
    } catch (error) {
      $("upload-message").textContent = error.message || "重新索引失败";
      $("upload-message").className = "error-text";
    }
  });
}

async function restoreActiveDataset() {
  const savedId = localStorage.getItem(STORAGE_KEY);
  if (!savedId) {
    return;
  }

  try {
    const detail = await state.api.getDataset(savedId);
    applyDatasetDetail(detail);
  } catch (_error) {
    localStorage.removeItem(STORAGE_KEY);
  }
}

async function bootstrap() {
  state.api = createApiClient("");
  bindEvents();

  let embedUrl = "";
  try {
    const config = await state.api.getPublicConfig();
    embedUrl = config?.difyEmbedUrl || "";
    const pollSec = Number.parseInt(config?.pollIntervalSec || "4", 10);
    state.pollIntervalSec = Number.isFinite(pollSec) && pollSec > 0 ? pollSec : 4;
  } catch (error) {
    console.warn("读取 public-config 失败:", error);
  }

  setupDifyIframe(embedUrl);
  await Promise.all([checkHealth(), loadDatasets(), restoreActiveDataset()]);
  startPolling();
}

bootstrap().catch((error) => {
  const badge = $("health-badge");
  badge.textContent = error.message || "页面初始化失败";
  badge.className = "badge badge-error";
});

window.addEventListener("beforeunload", stopPolling);
