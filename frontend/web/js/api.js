const DEFAULT_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  constructor(message, statusCode = null) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
  }
}

async function parseResponse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }

  if (response.ok) {
    return payload;
  }

  let message = response.statusText || `HTTP ${response.status}`;
  if (payload && typeof payload === "object" && payload.detail != null) {
    const detail = payload.detail;
    if (Array.isArray(detail)) {
      message = detail.map((item) => String(item)).join("; ");
    } else {
      message = String(detail);
    }
  } else if (typeof payload === "string" && payload) {
    message = payload;
  }

  throw new ApiError(message, response.status);
}

export function createApiClient(baseUrl = "") {
  const root = baseUrl.replace(/\/$/, "");

  function url(path) {
    return `${root}${path}`;
  }

  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeoutMs = options.timeoutMs ?? 30_000;
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url(path), {
        ...options,
        signal: controller.signal,
      });
      return await parseResponse(response);
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError("请求超时，请稍后重试");
      }
      throw new ApiError(`无法连接后端: ${error.message || error}`);
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    getPublicConfig() {
      return request("/api/v1/public-config");
    },

    health() {
      return request("/health", { timeoutMs: 10_000 });
    },

    listDatasets(limit = 10) {
      return request(`/api/v1/datasets?limit=${encodeURIComponent(limit)}`);
    },

    getDataset(datasetId) {
      return request(`/api/v1/datasets/${encodeURIComponent(datasetId)}`);
    },

    uploadDataset(file) {
      const formData = new FormData();
      formData.append("file", file, file.name);
      return request("/api/v1/datasets/upload", {
        method: "POST",
        body: formData,
        timeoutMs: DEFAULT_TIMEOUT_MS,
      });
    },

    getRagStatus(datasetId) {
      return request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/rag`);
    },

    reindexRag(datasetId) {
      return request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/rag/reindex`, {
        method: "POST",
        timeoutMs: DEFAULT_TIMEOUT_MS,
      });
    },

    getLatestSession(datasetId) {
      return request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/sessions/latest`);
    },
  };
}
