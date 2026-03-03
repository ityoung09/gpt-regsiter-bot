const POLL_INTERVAL_MS = 1500;

const $ = (id) => document.getElementById(id);

const els = {
  totalRuns: $("totalRuns"),
  cpaUrl: $("cpaUrl"),
  cpaToken: $("cpaToken"),
  startBtn: $("startBtn"),
  stopBtn: $("stopBtn"),
  clearBtn: $("clearBtn"),
  statusBadge: $("statusBadge"),
  statusText: $("statusText"),
  pid: $("pid"),
  uptime: $("uptime"),
  command: $("command"),
  logs: $("logs"),
  message: $("message"),
};

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
    cpa_url: els.cpaUrl.value.trim() || null,
    cpa_token: els.cpaToken.value.trim() || null,
  };
}

function setMessage(message, isError = false) {
  els.message.textContent = message;
  els.message.style.color = isError ? "#b4232f" : "#234363";
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

function paintStatus(running) {
  els.statusBadge.classList.toggle("running", !!running);
  els.statusBadge.classList.toggle("idle", !running);
  els.statusText.textContent = running ? "Running" : "Idle";
}

async function refreshState() {
  try {
    const state = await api("/api/state");
    paintStatus(state.running);

    els.pid.textContent = state.pid ?? "-";
    els.uptime.textContent = formatUptime(state.uptime_seconds);
    els.command.textContent = state.command || "-";

    const shouldStickBottom =
      Math.abs(els.logs.scrollHeight - els.logs.clientHeight - els.logs.scrollTop) < 20;

    els.logs.textContent = (state.logs || []).join("\n");

    if (shouldStickBottom) {
      els.logs.scrollTop = els.logs.scrollHeight;
    }
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
    setMessage("已发送停止请求");
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

els.startBtn.addEventListener("click", startTask);
els.stopBtn.addEventListener("click", stopTask);
els.clearBtn.addEventListener("click", clearLogs);

refreshState();
setInterval(refreshState, POLL_INTERVAL_MS);
