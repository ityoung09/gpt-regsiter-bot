const POLL_INTERVAL_MS = 1500;

const $ = (id) => document.getElementById(id);

const els = {
  totalRuns: $("totalRuns"),
  concurrency: $("concurrency"),
  provider: $("provider"),
  proxy: $("proxy"),
  cpaUrl: $("cpaUrl"),
  cpaToken: $("cpaToken"),
  startBtn: $("startBtn"),
  stopBtn: $("stopBtn"),
  clearBtn: $("clearBtn"),
  copyBtn: $("copyBtn"),
  statusBadge: $("statusBadge"),
  statusText: $("statusText"),
  pid: $("pid"),
  uptime: $("uptime"),
  command: $("command"),
  logs: $("logs"),
  message: $("message"),
};

let lastLogs = [];

async function api(path, method = "GET", body = undefined) {
  const resp = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const payload = await resp.json();
      if (payload?.detail) detail = payload.detail;
    } catch (_) {
      // ignored
    }
    throw new Error(detail);
  }

  return resp.json();
}

function buildPayload() {
  return {
    total_runs: Number(els.totalRuns.value || 1),
    concurrency: Number(els.concurrency.value || 3),
    provider_key: els.provider.value || "mailtm",
    proxy: els.proxy.value.trim() || null,
    cpa_url: els.cpaUrl.value.trim() || null,
    cpa_token: els.cpaToken.value.trim() || null,
  };
}

function setMessage(message, isError = false) {
  els.message.textContent = message;
  els.message.classList.toggle("is-error", isError);
}

function formatUptime(seconds) {
  const s = Number(seconds || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;

  if (h > 0) return `${h}h ${m}m ${sec}s`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function classifyLine(line) {
  if (/\[error\]/i.test(line)) return "log-error";
  if (/\[warn(ing)?\]/i.test(line)) return "log-warn";
  if (/\[system\]/i.test(line)) return "log-system";
  if (/\[task\]|saved:|completed summary/.test(line)) return "log-task";
  return "log-info";
}

function paintStatus(running) {
  els.statusBadge.classList.toggle("running", !!running);
  els.statusBadge.classList.toggle("idle", !running);
  els.statusText.textContent = running ? "Running" : "Idle";
  els.startBtn.disabled = !!running;
  els.stopBtn.disabled = !running;
}

function renderLogs(logs) {
  const shouldStickBottom =
    Math.abs(els.logs.scrollHeight - els.logs.clientHeight - els.logs.scrollTop) < 24;

  const fragment = document.createDocumentFragment();
  for (const line of logs) {
    const row = document.createElement("div");
    row.className = `log-line ${classifyLine(line)}`;
    row.textContent = line;
    fragment.appendChild(row);
  }
  els.logs.replaceChildren(fragment);

  if (shouldStickBottom) {
    els.logs.scrollTop = els.logs.scrollHeight;
  }
}

async function refreshState() {
  try {
    const state = await api("/api/state");
    paintStatus(state.running);

    els.pid.textContent = state.pid ?? "-";
    els.uptime.textContent = formatUptime(state.uptime_seconds);
    els.command.textContent = state.command || "-";

    lastLogs = state.logs || [];
    renderLogs(lastLogs);
  } catch (error) {
    setMessage(`状态刷新失败: ${error.message}`, true);
  }
}

async function startTask() {
  try {
    await api("/api/start", "POST", buildPayload());
    setMessage("任务已启动");
    await refreshState();
  } catch (error) {
    setMessage(`启动失败: ${error.message}`, true);
  }
}

async function stopTask() {
  try {
    await api("/api/stop", "POST");
    setMessage("已发送停止请求，等待进行中的请求收尾...");
    await refreshState();
  } catch (error) {
    setMessage(`停止失败: ${error.message}`, true);
  }
}

async function clearLogs() {
  try {
    await api("/api/logs/clear", "POST");
    setMessage("日志已清空");
    await refreshState();
  } catch (error) {
    setMessage(`清空失败: ${error.message}`, true);
  }
}

async function copyLogs() {
  if (!lastLogs.length) {
    setMessage("暂无日志可复制");
    return;
  }
  try {
    await navigator.clipboard.writeText(lastLogs.join("\n"));
    setMessage(`已复制 ${lastLogs.length} 行日志`);
  } catch (error) {
    setMessage(`复制失败: ${error.message}`, true);
  }
}

els.startBtn.addEventListener("click", startTask);
els.stopBtn.addEventListener("click", stopTask);
els.clearBtn.addEventListener("click", clearLogs);
els.copyBtn.addEventListener("click", copyLogs);

refreshState();
setInterval(refreshState, POLL_INTERVAL_MS);
