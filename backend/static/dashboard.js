let currentFilter = "all";
let refreshInProgress = false;
let taskChart = null;
let workerChart = null;

let taskOffset = 0;
let taskLimit = 20;

let logOffset = 0;
let logLimit = 30;

let taskTotal = 0;
let liveEventFilter = "all"
let isLiveStreamPaused = false

let liveEventTotal = 0
let liveEventFailures = 0
let liveEventRetries = 0

let liveEventSearchQuery = ""
const maximumLiveEvents = 100
const maximumReceivedEventIds = 500
const receivedEventIds = new Set()
const receivedEventIdOrder = []

const liveEventsContainer = document.getElementById("live-events")
const wsStatus = document.getElementById("ws-status")
const liveWorkersContainer = document.getElementById("live-workers")
const createTaskBtn = document.getElementById("create-task-btn")
const liveEventFilterButtons = document.querySelectorAll("#live-event-filters button")
const pauseLiveEventsBtn = document.getElementById("pause-live-events-btn")

const liveEventTotalEl = document.getElementById("live-event-total")
const liveEventFailuresEl = document.getElementById("live-event-failures")
const liveEventRetriesEl = document.getElementById("live-event-retries")

const toastContainer = document.getElementById("toast-container")
const recentFailures = []
const failureSpikeAlert = document.getElementById( "failure-spike-alert")
const acknowledgeAlertBtn =document.getElementById("acknowledge-alert-btn")
const incidentHistoryContainer = document.getElementById("incident-history")

const throughputPoints = []
const throughputCanvas = document.getElementById("throughput-chart")
const failureRateCanvas = document.getElementById("failure-rate-chart")
const failureRateWindowEl = document.getElementById("failure-rate-window")
const failureRateEmptyEl = document.getElementById("failure-rate-empty")
const failureRateSummaryEl = document.getElementById("failure-rate-summary")
const failureRateChartContainer = document.getElementById("failure-rate-chart-container")
const failureRateValueEl = document.getElementById("failure-rate-value")
const failureRetryCountEl = document.getElementById("failure-retry-count")
const failureTerminalCountEl = document.getElementById("failure-terminal-count")
const failureRateEvents = []
const deliveryMetricsWindowEl = document.getElementById("delivery-metrics-window")
const deliveryMetricsEmptyEl = document.getElementById("delivery-metrics-empty")
const deliveryMetricsSummaryEl = document.getElementById("delivery-metrics-summary")
const deliverySuccessRateEl = document.getElementById("delivery-success-rate")
const deliveryRetryRateEl = document.getElementById("delivery-retry-rate")
const deliveryPoisonRateEl = document.getElementById("delivery-poison-rate")
const deliveryEventCountEl = document.getElementById("delivery-event-count")
const workerThroughputWindowEl = document.getElementById("worker-throughput-window")
const workerThroughputEmptyEl = document.getElementById("worker-throughput-empty")
const workerThroughputListEl = document.getElementById("worker-throughput-list")
const workerThroughputEvents = []
const knownThroughputWorkers = new Set()
const queueLatencyEmptyEl = document.getElementById("queue-latency-empty")
const queueLatencySummaryEl = document.getElementById("queue-latency-summary")
const queueLatencyLatestEl = document.getElementById("queue-latency-latest")
const queueLatencyAverageEl = document.getElementById("queue-latency-average")
const queueLatencyMaxEl = document.getElementById("queue-latency-max")
const queueLatencyCountEl = document.getElementById("queue-latency-count")
const maximumQueueLatencySamples = 100
const maximumQueueLatencyTrackedTasks = 300
const queueCreatedTimestamps = new Map()
const queueCreatedTaskIds = []
const queueStartedTaskIds = new Set()
const queueLatencySamples = []
const processingLatencyEmptyEl = document.getElementById("processing-latency-empty")
const processingLatencySummaryEl = document.getElementById("processing-latency-summary")
const processingLatencyLatestEl = document.getElementById("processing-latency-latest")
const processingLatencyAverageEl = document.getElementById("processing-latency-average")
const processingLatencyMaxEl = document.getElementById("processing-latency-max")
const processingLatencyCountEl = document.getElementById("processing-latency-count")
const maximumProcessingLatencySamples = 100
const maximumProcessingLatencyTrackedTasks = 300
const processingStartedTimestamps = new Map()
const processingStartedTaskIds = []
const processingLatencySamples = []
const systemHealthCardEl = document.getElementById("system-health-card")
const systemHealthStateEl = document.getElementById("system-health-state")
const systemHealthReasonEl = document.getElementById("system-health-reason")
let latestMetricsSnapshot = null
const liveWorkerLastSeen = {}
const reportedStaleWorkers = new Set()
const recoveredWorkers = new Set()

const eventDetailDrawer = document.getElementById("event-detail-drawer")
const eventDetailContent = document.getElementById("event-detail-content")
const eventTraceFields = document.getElementById("event-trace-fields")
const eventTraceId = document.getElementById("event-trace-id")
const eventSpanId = document.getElementById("event-span-id")
const eventTraceLink = document.getElementById("event-trace-link")
const closeEventDetailBtn = document.getElementById("close-event-detail-btn")
const liveEventSearchInput = document.getElementById("live-event-search")
const clearLiveEventsBtn = document.getElementById("clear-live-events-btn")
const clearIncidentHistoryBtn = document.getElementById("clear-incident-history-btn")

let throughputChart = null
let failureRateChart = null

if (throughputCanvas) {
  const throughputCtx = throughputCanvas.getContext("2d")

  throughputChart = new Chart(throughputCtx, {
    type: "line",

    data: {
      labels: [],

      datasets: [
        {
          label: "Tasks/sec",
          data: [],
        },
      ],
    },

    options: {
      responsive: true,
      animation: false,
    },
  })
}

if (failureRateCanvas) {
  const failureRateCtx = failureRateCanvas.getContext("2d")

  failureRateChart = new Chart(failureRateCtx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Failure %",
          data: [],
          borderColor: "#dc2626",
          backgroundColor: "rgba(220, 38, 38, 0.12)",
          fill: true,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: {
            callback: (value) => `${value}%`,
          },
        },
      },
    },
  })
}

function setFilter(status) {
currentFilter = status;
loadTasks();
}

function formatUptime(seconds) {
const hours = Math.floor(seconds / 3600);
const minutes = Math.floor((seconds % 3600) / 60);
const secs = seconds % 60;
return `${hours}h ${minutes}m ${secs}s`;
}

function toggleDarkMode() {
document.body.classList.toggle("dark-mode");

const isDarkMode =
    document.body.classList.contains("dark-mode");

localStorage.setItem("darkMode", isDarkMode);
}

function showActionStatus(message) {
const el = document.getElementById("action-status");

el.innerHTML = `<b>${message}</b>`;

setTimeout(() => {
    el.innerHTML = "";
}, 3000);
}

function setDangerButtonsDisabled(disabled) {
document
    .querySelectorAll(".danger-action")
    .forEach(button => {
        button.disabled = disabled;
    });
}

function previousTaskPage() {
    taskOffset = Math.max(0, taskOffset - taskLimit);
    loadTasks();
}

function nextTaskPage() {
    if (taskOffset + taskLimit >= taskTotal) {
        return;
    }

    taskOffset += taskLimit;
    loadTasks();
}

function previousLogPage() {
    logOffset = Math.max(0, logOffset - logLimit);
    loadLogs();
}

function nextLogPage() {
    if (logOffset + logLimit >= logTotal) {
        return;
    }

    logOffset += logLimit;
    loadLogs();
}

function applyTaskFilters() {
    taskOffset = 0;
    loadTasks();
}

function applyLogFilter() {
    logOffset = 0;
    loadLogs();
}

async function loadMetrics() {
    const data = await fetchJson("/metrics");
    latestMetricsSnapshot = data

    const queueClass =
        data.queued > 20 ? "card-danger" :
        data.queued > 5 ? "card-warning" :
        "card-good";

    const failedClass =
        data.failed > 5 ? "card-danger" :
        data.failed > 0 ? "card-warning" :
        "card-good";

    document.getElementById("metrics-cards").innerHTML = `
        <div class="card ${queueClass}"><span>Queued</span><strong>${data.queued}</strong></div>
        <div class="card"><span>Processing</span><strong>${data.processing}</strong></div>
        <div class="card"><span>Success</span><strong>${data.success}</strong></div>
        <div class="card ${failedClass}"><span>Failed</span><strong>${data.failed}</strong></div>
        <div class="card"><span>Workers Alive</span><strong>${data.alive_workers}</strong></div>
        <div class="card"><span>Throughput/min</span><strong>${data.throughput_last_minute}</strong></div>
    `;

    const warningEl = document.getElementById("queue-warning");

    if (data.redis_queue_length > 20) {
        warningEl.innerHTML = "<b style='color:red'>HIGH QUEUE PRESSURE</b>";
    } else {
        warningEl.innerHTML = "";
    }

    document.getElementById("metrics").textContent =
        JSON.stringify(data, null, 2);

    updateSystemHealthPanel()

    if (typeof Chart === "undefined") {
        console.warn("Chart.js is not loaded");
        return;
    }

const chartData = {
    labels: ["Queued", "Processing", "Success", "Failed"],
    datasets: [
        {
            label: "Tasks",
            data: [
                data.queued,
                data.processing,
                data.success,
                data.failed,
            ],
            backgroundColor: [
                "rgba(34, 197, 94, 0.35)",
                "rgba(59, 130, 246, 0.35)",
                "rgba(16, 185, 129, 0.35)",
                "rgba(239, 68, 68, 0.35)",
            ],
            borderColor: [
                "rgba(34, 197, 94, 1)",
                "rgba(59, 130, 246, 1)",
                "rgba(16, 185, 129, 1)",
                "rgba(239, 68, 68, 1)",
            ],
            borderWidth: 1,
        },
    ],
};

const ctx = document.getElementById("task-chart");

if (!ctx) {
    console.warn("Missing task chart canvas");
    return;
}

if (taskChart) {
    taskChart.destroy();
}

taskChart = new Chart(ctx, {
    type: "bar",
    data: chartData,
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                ticks: {
                    precision: 0,
                },
            },
        },
        plugins: {
            legend: {
                display: true,
            },
        },
    },
});
}

async function loadLogs() {

    let logTotal = 0;
    const taskIdFilter = document.getElementById("log-task-id-filter");

    const params = new URLSearchParams();

    params.set("limit", String(logLimit));
    params.set("offset", String(logOffset));

    if (taskIdFilter && taskIdFilter.value) {
        params.set("task_id", taskIdFilter.value);
    }

    const data = await fetchJson(`/logs?${params.toString()}`);
    const logs = Array.isArray(data) ? data : data.items;
    logTotal = Array.isArray(data) ? logs.length : data.total;

    const html = logs
        .map(log => {
            return `
                <div>
                    <b>Task #${log.task_id}</b>
                    - ${log.message}
                </div>
            `;
        })
        .join("");

    const logsEl =
        document.getElementById("logs") ||
        document.getElementById("logs-panel") ||
        document.getElementById("log-list");

    if (!logsEl) {
        console.warn("Missing logs container element");
        return;
    }

    logsEl.innerHTML = html;

    const summaryEl = document.getElementById("logs-summary");

    if (summaryEl) {
        const start = data.total === 0 ? 0 : logOffset + 1;
        const end = Math.min(logOffset + logs.length, data.total);

        summaryEl.textContent =
            `Showing ${start}-${end} of ${data.total} logs`;
    }
}

function clearLogFilter() {
    const taskIdFilter = document.getElementById("log-task-id-filter");

    if (taskIdFilter) {
        taskIdFilter.value = "";
    }

    loadLogs();
}

async function retryTask(taskId) {
await fetch(`/tasks/${taskId}/retry`, {
    method: "POST"
});

await refresh();
}

async function createTask(priority) {
await fetch(`/tasks?priority=${priority}`, {
    method: "POST"
});

await refresh();
}

async function pauseSystem() {
await fetch("/pause", { method: "POST" });
await refresh();
}

async function resumeSystem() {
await fetch("/resume", { method: "POST" });
await refresh();
}

async function loadSystemState() {
const configResponse = await fetch("/config");
const configData = await configResponse.json();

const environment = configData.environment;
const version = configData.version;

document.getElementById("footer-info").textContent =
    `Failure Playground · ${environment} · v${version}`;

const response = await fetch("/system-state");
const data = await response.json();

const paused = data.paused;

const pauseButton =
    document.getElementById("pause-button");

const resumeButton =
    document.getElementById("resume-button");

pauseButton.disabled = paused;
resumeButton.disabled = !paused;

const el = document.getElementById("system-state");

const healthResponse = await fetch("/health");
const healthData = await healthResponse.json();

const uptime = healthData.uptime_seconds;

if (paused) {
    el.innerHTML =
        `<b style="color:red">SYSTEM PAUSED</b>
        <br>
        environment: ${environment}
        <br>
        version: ${version}
        <br>
        ${/*uptime: ${formatUptime(uptime)*/ ""}`;
} else {
    el.innerHTML =
        `<b style="color:green">SYSTEM RUNNING</b>
        <br>
        environment: ${environment}
        <br>
        version: ${version}
        <br>
        ${/* uptime: ${formatUptime(uptime)*/ ""}`;
}
}

if (localStorage.getItem("darkMode") === "true") {
document.body.classList.add("dark-mode");
}

async function refresh() {
    if (refreshInProgress) {
        return;
    }

    refreshInProgress = true;

    document.getElementById(
        "loading-indicator"
    ).textContent = "Refreshing...";

    try {
        document.getElementById(
            "error-banner"
        ).textContent = "";

        const results = await Promise.allSettled([
            loadMetrics(),
            loadWorkers(),
            loadAlerts(),
            loadTasks(),
            loadLogs(),
            loadSystemState(),
        ]);

        const failedResults = results.filter(
            result => result.status === "rejected"
        );

        if (failedResults.length > 0) {
            throw failedResults[0].reason;
        }

        document.getElementById("last-refresh-time").textContent =
        `Last refreshed: ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        console.error(error);

        document.getElementById(
            "error-banner"
        ).textContent = error.message;

    } finally {
        refreshInProgress = false;

        document.getElementById(
            "loading-indicator"
        ).textContent = "";
    }
}
async function duplicateTask(taskId) {
await fetch(`/tasks/${taskId}/duplicate`, {
    method: "POST"
});

await refresh();
}
async function createPoisonTask() {
await fetch("/tasks?is_poison=true", {
    method: "POST"
});

await refresh();
}
async function clearCompletedTasks() {
const ok = confirm("Delete all completed tasks?");

if (!ok) {
    return;
}

await fetch("/tasks/completed", {
    method: "DELETE"
});

await refresh();
}
async function clearFailedTasks() {
const ok = confirm("Delete all failed tasks?");

if (!ok) {
    return;
}

await fetch("/tasks/failed", {
    method: "DELETE"
});

await refresh();
}
async function loadWorkers() {
    const response = await fetch("/workers");
    const workers = await response.json();

    const now = new Date();

    document.getElementById("workers-panel").innerHTML =
        workers
            .map(worker => {
                const lastSeen = new Date(worker.last_seen + "Z");
                const secondsAgo = Math.floor((now - lastSeen) / 1000);

                const status =
                    secondsAgo <= 5
                        ? "alive"
                        : "stale";

                return `
                    <div>
                        <b style="color:${status === "alive" ? "green" : "red"}">
                            ${worker.worker_name} - ${status}
                        </b>
                        - ${secondsAgo}s ago
                        - processed: ${worker.processed_count}
                    </div>
                `;
            })
            .join("");

    if (typeof Chart === "undefined") {
        console.warn("Chart.js is not loaded");
        return;
    }

    const workerCtx = document.getElementById("worker-chart");

    const workerChartData = {
        labels: workers.map(worker => worker.worker_name),
        datasets: [{
            label: "Processed Tasks",
            data: workers.map(worker => worker.processed_count),
        }],
    };

    if (workerChart) {
        workerChart.destroy();
    }

    workerChart = new Chart(workerCtx, {
        type: "bar",
        data: workerChartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
        },
    });
}

async function loadTasks() {
    const statusFilter = document.getElementById("task-status-filter");
    const poisonFilter = document.getElementById("task-poison-filter");

    const params = new URLSearchParams();

    params.set("limit", String(taskLimit));
    params.set("offset", String(taskOffset));

    if (statusFilter && statusFilter.value) {
        params.set("status", statusFilter.value);
    }

    if (poisonFilter && poisonFilter.value) {
        params.set("is_poison", poisonFilter.value);
    }

    const data = await fetchJson(`/tasks?${params.toString()}`);
    const tasks = Array.isArray(data) ? data : data.items;

    taskTotal = Array.isArray(data) ? tasks.length : data.total;

    const html = tasks
        .map(task => {
            return `
                <div>
                    <b>#${task.id}</b>
                    - ${task.status}
                    - retries: ${task.retry_count}
                    - priority: ${task.priority}
                    - poison: ${task.is_poison}
                </div>
            `;
        })
        .join("");

    const tasksEl =
        document.getElementById("tasks") ||
        document.getElementById("tasks-panel") ||
        document.getElementById("task-list");

    if (!tasksEl) {
        console.warn("Missing tasks container element");
        return;
    }

    tasksEl.innerHTML = html;

    const summaryEl = document.getElementById("tasks-summary");

    if (summaryEl) {
        const total = Array.isArray(data) ? tasks.length : data.total;
        const start = total === 0 ? 0 : taskOffset + 1;
        const end = Math.min(taskOffset + tasks.length, total);

        summaryEl.textContent =
            `Showing ${start}-${end} of ${total} tasks`;
    }
}

async function resetWorkerCounts() {
await fetch("/workers/reset-counts", {
    method: "POST"
});

await refresh();
}
async function createBulkTasks(count) {
await fetch(`/tasks/bulk?count=${count}`, {
    method: "POST"
});

await refresh();
}
async function loadAlerts() {
const response = await fetch("/alerts");
const alerts = await response.json();const incidentSummary =
document.getElementById("incident-summary");
    if (alerts.length === 0) {
        incidentSummary.innerHTML =
            "<b style='color:green'>No recent incidents</b>";
    } else {
        incidentSummary.innerHTML =
            `<b style="color:red">${alerts.length} alert(s) recorded</b>`;
    }

const recentAlerts = alerts.slice(-10);

document.getElementById("alerts-panel").textContent =
    recentAlerts
        .map(alert =>
            `[${alert.created_at}] ${alert.message}`
        )
        .join("\\n");
}
async function clearAlerts() {
const ok = confirm("Clear all alerts?");

if (!ok) {
    return;
}

await fetch("/alerts", {
    method: "DELETE"
});

await refresh();
}
async function clearQueue() {
const ok = confirm("Clear Redis queue?");

if (!ok) {
    return;
}

await fetch("/queue", {
    method: "DELETE"
});

await refresh();
}
async function resetSystem() {
const ok = confirm("Reset whole system?");

if (!ok) {
    return;
}

setDangerButtonsDisabled(true);

await fetch("/reset", {
    method: "DELETE"
});

await refresh();
showActionStatus("System reset complete");
showActionStatus("Queue cleared");
}
refresh();
let refreshTimer = null;

function startRefreshTimer() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }

    const interval =
        Number(document.getElementById("refresh-interval").value);

    refreshTimer = setInterval(() => {
        const enabled =
            document.getElementById("auto-refresh-toggle").checked;

        if (enabled) {
            refresh();
        }
    }, interval);
}

function formatAge(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    }

    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;

    return `${minutes}m ${secs}s`;
}

async function fetchJson(url) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`${url} failed: ${response.status}`);
    }

    return response.json();
}

function initializeDashboardEventListeners() {
  // Live event filter buttons
  liveEventFilterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      liveEventFilter = button.dataset.filter
    })
  })

  if (pauseLiveEventsBtn) {
    pauseLiveEventsBtn.addEventListener("click", () => {
      isLiveStreamPaused = !isLiveStreamPaused

      pauseLiveEventsBtn.textContent = isLiveStreamPaused
        ? "Resume Live Stream"
        : "Pause Live Stream"
    })
  }

  if (acknowledgeAlertBtn && failureSpikeAlert) {
    acknowledgeAlertBtn.addEventListener("click", () => {
      failureSpikeAlert.classList.add("hidden")
    })
  }

  if (liveEventSearchInput) {
    liveEventSearchInput.addEventListener("input", (e) => {
      liveEventSearchQuery = e.target.value.toLowerCase()
      applyLiveEventSearchFilter()
    })
  }

  if (clearLiveEventsBtn) {
    clearLiveEventsBtn.addEventListener("click", () => {
      liveEventsContainer.innerHTML = ""

      liveEventTotal = 0
      liveEventFailures = 0
      liveEventRetries = 0

      if (liveEventTotalEl) liveEventTotalEl.textContent = "0"
      if (liveEventFailuresEl) liveEventFailuresEl.textContent = "0"
      if (liveEventRetriesEl) liveEventRetriesEl.textContent = "0"
    })
  }

  if (clearIncidentHistoryBtn) {
    clearIncidentHistoryBtn.addEventListener("click", () => {
      incidentHistoryContainer.innerHTML = ""
    })
  }

  if (closeEventDetailBtn && eventDetailDrawer) {
    closeEventDetailBtn.addEventListener("click", () => {
      eventDetailDrawer.classList.add("hidden")
    })
  }

  if (createTaskBtn) {
    createTaskBtn.addEventListener("click", async () => {
      const response = await fetch("/tasks?priority=1", {
        method: "POST",
      })

      if (!response.ok) {
        console.error("Failed to create task")
        return
      }

      await response.json()
    })
  }

  // Task / log filter listeners (formerly in DOMContentLoaded)
  const statusFilter = document.getElementById("task-status-filter")
  const poisonFilter = document.getElementById("task-poison-filter")
  const logTaskIdFilter = document.getElementById("log-task-id-filter")

  if (statusFilter) {
    statusFilter.addEventListener("change", loadTasks)
  }

  if (poisonFilter) {
    poisonFilter.addEventListener("change", loadTasks)
  }

  if (logTaskIdFilter) {
    logTaskIdFilter.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        loadLogs()
      }
    })
  }

  // Refresh interval control
  const refreshIntervalEl = document.getElementById("refresh-interval")

  if (refreshIntervalEl) {
    refreshIntervalEl.addEventListener("change", startRefreshTimer)
  }

  if (failureRateWindowEl) {
    failureRateWindowEl.addEventListener("change", updateFailureRateChart)
  }

  if (deliveryMetricsWindowEl) {
    deliveryMetricsWindowEl.addEventListener("change", updateDeliveryMetricsPanel)
  }

  if (workerThroughputWindowEl) {
    workerThroughputWindowEl.addEventListener("change", updateWorkerThroughputPanel)
  }

  startRefreshTimer()
}

document.addEventListener("DOMContentLoaded", () => {
  initializeDashboardEventListeners()
})

const websocketReconnectDelays = [1000, 2000, 5000, 10000]
const reconnectedStatusDuration = 2000
let operationsSocket = null
let reconnectTimer = null
let reconnectedStatusTimer = null
let reconnectAttempt = 0
let hasConnected = false
let isSocketShuttingDown = false

function setWebSocketStatus(state) {
  if (!wsStatus) return

  const labels = {
    connected: "Connected",
    disconnected: "Disconnected",
    reconnecting: "Reconnecting...",
    reconnected: "Reconnected",
  }

  wsStatus.textContent = labels[state]
  wsStatus.className = `ws-${state}`
  wsStatus.dataset.state = state
}

function clearReconnectedStatusTimer() {
  if (!reconnectedStatusTimer) return

  clearTimeout(reconnectedStatusTimer)
  reconnectedStatusTimer = null
}

function scheduleWebSocketReconnect() {
  if (isSocketShuttingDown || reconnectTimer) return

  const delay = websocketReconnectDelays[
    Math.min(reconnectAttempt, websocketReconnectDelays.length - 1)
  ]

  reconnectAttempt += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null

    if (isSocketShuttingDown) return

    setWebSocketStatus("reconnecting")
    connectOperationsWebSocket()
  }, delay)
}

function connectOperationsWebSocket() {
  if (
    operationsSocket &&
    (
      operationsSocket.readyState === WebSocket.CONNECTING ||
      operationsSocket.readyState === WebSocket.OPEN
    )
  ) {
    return
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/operations`)

  operationsSocket = socket

  socket.onmessage = (event) => {
    if (socket !== operationsSocket) return

    const data = JSON.parse(event.data)

    if (data.event === "worker_heartbeat") {
      renderLiveWorker(data)
      rememberThroughputWorker(data.worker_name)
      updateWorkerThroughputPanel()
      return
    }

    if (hasReceivedEvent(data)) return

    recordFailureRateEvent(data)
    recordWorkerThroughputEvent(data)
    recordQueueLatencyEvent(data)
    recordProcessingLatencyEvent(data)
    appendLiveEvent(data, data.replayed === true)
  }

  socket.onopen = () => {
    if (socket !== operationsSocket) return

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    reconnectAttempt = 0
    clearReconnectedStatusTimer()

    if (hasConnected) {
      setWebSocketStatus("reconnected")
      reconnectedStatusTimer = setTimeout(() => {
        reconnectedStatusTimer = null

        if (socket === operationsSocket && socket.readyState === WebSocket.OPEN) {
          setWebSocketStatus("connected")
        }
      }, reconnectedStatusDuration)
      return
    }

    hasConnected = true
    setWebSocketStatus("connected")
  }

  socket.onclose = () => {
    if (socket !== operationsSocket) return

    operationsSocket = null
    clearReconnectedStatusTimer()

    if (isSocketShuttingDown) return

    setWebSocketStatus("disconnected")
    scheduleWebSocketReconnect()
  }
}

function cleanupOperationsWebSocket() {
  isSocketShuttingDown = true
  clearReconnectedStatusTimer()

  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  if (operationsSocket) {
    const socket = operationsSocket
    operationsSocket = null
    socket.close()
  }
}

function restoreOperationsWebSocket() {
  if (!isSocketShuttingDown) return

  isSocketShuttingDown = false
  setWebSocketStatus("disconnected")
  connectOperationsWebSocket()
}

connectOperationsWebSocket()
window.addEventListener("pagehide", cleanupOperationsWebSocket)
window.addEventListener("pageshow", restoreOperationsWebSocket)

function renderLiveWorker(data) {
  const id = `live-worker-${data.worker_name}`

  let item = document.getElementById(id)

  liveWorkerLastSeen[data.worker_name] = Date.now()

  if (!item) {
    item = document.createElement("div")
    item.id = id
    item.className = "live-worker"
    liveWorkersContainer.appendChild(item)
  }

  item.textContent =
  `${data.worker_name} | healthy | processed=${data.processed_count}`
  updateSystemHealthPanel()
}

function hasReceivedEvent(data) {
  if (!data.event_id) return false

  if (receivedEventIds.has(data.event_id)) {
    return true
  }

  receivedEventIds.add(data.event_id)
  receivedEventIdOrder.push(data.event_id)

  if (receivedEventIdOrder.length > maximumReceivedEventIds) {
    receivedEventIds.delete(receivedEventIdOrder.shift())
  }

  return false
}

function recordFailureRateEvent(data) {
  if (
    data.event !== "task_succeeded" &&
    data.event !== "task_failed" &&
    data.event !== "task_poisoned" &&
    data.event !== "task_retried"
  ) {
    return
  }

  const timestamp = Date.parse(data.timestamp)

  if (Number.isNaN(timestamp)) return

  failureRateEvents.push({
    event: data.event,
    timestamp,
  })

  trimFailureRateEvents()
  updateFailureRateChart()
}

function trimFailureRateEvents() {
  const cutoff = Date.now() - 300_000

  for (let index = failureRateEvents.length - 1; index >= 0; index -= 1) {
    if (failureRateEvents[index].timestamp < cutoff) {
      failureRateEvents.splice(index, 1)
    }
  }
}

function updateFailureRateChart() {
  if (
    !failureRateChart ||
    !failureRateEmptyEl ||
    !failureRateSummaryEl ||
    !failureRateChartContainer
  ) {
    return
  }

  trimFailureRateEvents()

  const windowMs = Number(failureRateWindowEl ? failureRateWindowEl.value : 60_000)
  const now = Date.now()
  const cutoff = now - windowMs
  const windowEvents = failureRateEvents.filter((event) => event.timestamp >= cutoff)
  const terminalEvents = windowEvents.filter(
    (event) => (
      event.event === "task_succeeded" ||
      event.event === "task_failed" ||
      event.event === "task_poisoned"
    )
  )
  const failedEvents = terminalEvents.filter(
    (event) => event.event === "task_failed" || event.event === "task_poisoned"
  )
  const retryCount = windowEvents.filter((event) => event.event === "task_retried").length
  const failureRate = terminalEvents.length
    ? Math.round((failedEvents.length / terminalEvents.length) * 100)
    : 0

  if (failureRateValueEl) failureRateValueEl.textContent = `${failureRate}%`
  if (failureRetryCountEl) failureRetryCountEl.textContent = retryCount
  if (failureTerminalCountEl) failureTerminalCountEl.textContent = terminalEvents.length

  const hasTerminalEvents = terminalEvents.length > 0

  failureRateEmptyEl.classList.toggle("hidden", hasTerminalEvents)
  failureRateSummaryEl.classList.toggle("hidden", !hasTerminalEvents)
  failureRateChartContainer.classList.toggle("hidden", !hasTerminalEvents)

  if (!hasTerminalEvents) {
    failureRateChart.data.labels = []
    failureRateChart.data.datasets[0].data = []
    failureRateChart.update()
    updateDeliveryMetricsPanel()
    updateSystemHealthPanel()
    return
  }

  failureRateChart.resize()

  const bucketCount = windowMs === 60_000 ? 12 : 10
  const bucketSize = windowMs / bucketCount
  const labels = []
  const points = []

  for (let index = 0; index < bucketCount; index += 1) {
    const bucketEnd = cutoff + ((index + 1) * bucketSize)
    const outcomesToPoint = terminalEvents.filter((event) => event.timestamp <= bucketEnd)
    const failuresToPoint = outcomesToPoint.filter(
      (event) => event.event === "task_failed" || event.event === "task_poisoned"
    )

    labels.push(new Date(bucketEnd).toLocaleTimeString())
    points.push(
      outcomesToPoint.length
        ? Math.round((failuresToPoint.length / outcomesToPoint.length) * 100)
        : null
    )
  }

  failureRateChart.data.labels = labels
  failureRateChart.data.datasets[0].data = points
  failureRateChart.update()
  updateDeliveryMetricsPanel()
  updateSystemHealthPanel()
}

function updateDeliveryMetricsPanel() {
  if (
    !deliveryMetricsEmptyEl ||
    !deliveryMetricsSummaryEl ||
    !deliverySuccessRateEl ||
    !deliveryRetryRateEl ||
    !deliveryPoisonRateEl ||
    !deliveryEventCountEl
  ) {
    return
  }

  trimFailureRateEvents()

  const windowMs = Number(deliveryMetricsWindowEl ? deliveryMetricsWindowEl.value : 60_000)
  const cutoff = Date.now() - windowMs
  const windowEvents = failureRateEvents.filter((event) => event.timestamp >= cutoff)
  const terminalEvents = windowEvents.filter((event) => isTerminalTaskEvent(event.event))
  const succeededEvents = terminalEvents.filter((event) => event.event === "task_succeeded")
  const poisonEvents = terminalEvents.filter((event) => event.event === "task_poisoned")
  const retryEvents = windowEvents.filter((event) => event.event === "task_retried")
  const denominator = terminalEvents.length + retryEvents.length

  if (!denominator) {
    deliveryMetricsEmptyEl.classList.remove("hidden")
    deliveryMetricsSummaryEl.classList.add("hidden")
    deliverySuccessRateEl.textContent = "0%"
    deliveryRetryRateEl.textContent = "0%"
    deliveryPoisonRateEl.textContent = "0%"
    deliveryEventCountEl.textContent = "0"
    return
  }

  const successRate = terminalEvents.length
    ? Math.round((succeededEvents.length / terminalEvents.length) * 100)
    : 0
  const retryRate = Math.round((retryEvents.length / denominator) * 100)
  const poisonRate = terminalEvents.length
    ? Math.round((poisonEvents.length / terminalEvents.length) * 100)
    : 0

  deliverySuccessRateEl.textContent = `${successRate}%`
  deliveryRetryRateEl.textContent = `${retryRate}%`
  deliveryPoisonRateEl.textContent = `${poisonRate}%`
  deliveryEventCountEl.textContent = denominator

  deliveryMetricsEmptyEl.classList.add("hidden")
  deliveryMetricsSummaryEl.classList.remove("hidden")
}

function rememberThroughputWorker(workerName) {
  if (workerName) {
    knownThroughputWorkers.add(workerName)
  }
}

function recordWorkerThroughputEvent(data) {
  if (data.event !== "worker_processed_count_updated" || !data.worker_name) {
    return
  }

  const timestamp = Date.parse(data.timestamp)

  if (Number.isNaN(timestamp)) return

  rememberThroughputWorker(data.worker_name)
  workerThroughputEvents.push({
    timestamp,
    workerName: data.worker_name,
  })

  trimWorkerThroughputEvents()
  updateWorkerThroughputPanel()
}

function trimWorkerThroughputEvents() {
  const cutoff = Date.now() - 60_000

  for (let index = workerThroughputEvents.length - 1; index >= 0; index -= 1) {
    if (workerThroughputEvents[index].timestamp < cutoff) {
      workerThroughputEvents.splice(index, 1)
    }
  }
}

function updateWorkerThroughputPanel() {
  if (!workerThroughputEmptyEl || !workerThroughputListEl) return

  trimWorkerThroughputEvents()

  if (!knownThroughputWorkers.size) {
    workerThroughputEmptyEl.classList.remove("hidden")
    workerThroughputListEl.classList.add("hidden")
    updateSystemHealthPanel()
    return
  }

  const windowMs = Number(workerThroughputWindowEl ? workerThroughputWindowEl.value : 10_000)
  const windowSeconds = windowMs / 1000
  const cutoff = Date.now() - windowMs
  const counts = new Map()

  workerThroughputEvents.forEach((event) => {
    if (event.timestamp >= cutoff) {
      counts.set(event.workerName, (counts.get(event.workerName) || 0) + 1)
    }
  })

  const rows = Array.from(knownThroughputWorkers)
    .sort()
    .map((workerName) => {
      const count = counts.get(workerName) || 0

      return {
        count,
        rate: count / windowSeconds,
        workerName,
      }
    })
  const maximumRate = Math.max(...rows.map((row) => row.rate), 0.01)

  workerThroughputEmptyEl.classList.add("hidden")
  workerThroughputListEl.classList.remove("hidden")
  workerThroughputListEl.innerHTML = ""

  rows.forEach((row) => {
    const item = document.createElement("div")
    const name = document.createElement("span")
    const bar = document.createElement("div")
    const fill = document.createElement("div")
    const rate = document.createElement("span")

    item.className = "worker-throughput-row"

    if (row.rate === 0) {
      item.classList.add("worker-throughput-idle")
    }

    name.className = "worker-throughput-name"
    name.textContent = row.workerName
    bar.className = "worker-throughput-bar"
    fill.className = "worker-throughput-bar-fill"
    fill.style.width = `${Math.round((row.rate / maximumRate) * 100)}%`
    rate.className = "worker-throughput-rate"
    rate.textContent = `${row.rate.toFixed(2)}/sec`

    bar.appendChild(fill)
    item.appendChild(name)
    item.appendChild(bar)
    item.appendChild(rate)
    workerThroughputListEl.appendChild(item)
  })

  updateSystemHealthPanel()
}

function recordQueueLatencyEvent(data) {
  if (!data.task_id) return

  const taskId = String(data.task_id)
  const timestamp = Date.parse(data.timestamp)

  if (Number.isNaN(timestamp)) return

  if (data.event === "task_created") {
    if (!queueCreatedTimestamps.has(taskId)) {
      queueCreatedTaskIds.push(taskId)
    }

    queueCreatedTimestamps.set(taskId, timestamp)

    while (queueCreatedTaskIds.length > maximumQueueLatencyTrackedTasks) {
      queueCreatedTimestamps.delete(queueCreatedTaskIds.shift())
    }

    return
  }

  if (data.event !== "task_started" || queueStartedTaskIds.has(taskId)) {
    return
  }

  const createdTimestamp = parseQueueReferenceTimestamp(data) ?? queueCreatedTimestamps.get(taskId)

  if (createdTimestamp === undefined) return

  const waitMs = Math.max(timestamp - createdTimestamp, 0)

  queueStartedTaskIds.add(taskId)
  queueLatencySamples.push({
    taskId,
    timestamp,
    waitMs,
  })

  while (queueLatencySamples.length > maximumQueueLatencySamples) {
    queueLatencySamples.shift()
  }

  updateQueueLatencyPanel()
}

function parseQueueReferenceTimestamp(data) {
  const reference = data.queued_at || data.created_at

  if (!reference) return undefined

  const timestamp = Date.parse(reference)

  if (Number.isNaN(timestamp)) return undefined

  return timestamp
}

function formatQueueLatency(waitMs) {
  if (waitMs < 1000) {
    return `${Math.round(waitMs)} ms`
  }

  if (waitMs < 60_000) {
    return `${(waitMs / 1000).toFixed(1)} sec`
  }

  return `${(waitMs / 60_000).toFixed(1)} min`
}

function updateQueueLatencyPanel() {
  if (
    !queueLatencyEmptyEl ||
    !queueLatencySummaryEl ||
    !queueLatencyLatestEl ||
    !queueLatencyAverageEl ||
    !queueLatencyMaxEl ||
    !queueLatencyCountEl
  ) {
    return
  }

  if (!queueLatencySamples.length) {
    queueLatencyEmptyEl.classList.remove("hidden")
    queueLatencySummaryEl.classList.add("hidden")
    return
  }

  const latest = queueLatencySamples[queueLatencySamples.length - 1]
  const totalWait = queueLatencySamples.reduce((sum, sample) => sum + sample.waitMs, 0)
  const averageWait = totalWait / queueLatencySamples.length
  const maxWait = Math.max(...queueLatencySamples.map((sample) => sample.waitMs))

  queueLatencyLatestEl.textContent = formatQueueLatency(latest.waitMs)
  queueLatencyAverageEl.textContent = formatQueueLatency(averageWait)
  queueLatencyMaxEl.textContent = formatQueueLatency(maxWait)
  queueLatencyCountEl.textContent = queueLatencySamples.length

  queueLatencyEmptyEl.classList.add("hidden")
  queueLatencySummaryEl.classList.remove("hidden")
  updateSystemHealthPanel()
}

function recordProcessingLatencyEvent(data) {
  if (!data.task_id) return

  const taskId = String(data.task_id)
  const timestamp = Date.parse(data.timestamp)

  if (Number.isNaN(timestamp)) return

  if (data.event === "task_started") {
    if (!processingStartedTimestamps.has(taskId)) {
      processingStartedTaskIds.push(taskId)
    }

    processingStartedTimestamps.set(taskId, timestamp)

    while (processingStartedTaskIds.length > maximumProcessingLatencyTrackedTasks) {
      processingStartedTimestamps.delete(processingStartedTaskIds.shift())
    }

    return
  }

  if (!isTerminalTaskEvent(data.event)) {
    return
  }

  const startedTimestamp =
    parseProcessingReferenceTimestamp(data) ?? processingStartedTimestamps.get(taskId)

  if (startedTimestamp === undefined) return

  const durationMs = Math.max(timestamp - startedTimestamp, 0)

  processingLatencySamples.push({
    taskId,
    timestamp,
    durationMs,
  })

  while (processingLatencySamples.length > maximumProcessingLatencySamples) {
    processingLatencySamples.shift()
  }

  updateProcessingLatencyPanel()
}

function isTerminalTaskEvent(event) {
  return (
    event === "task_succeeded" ||
    event === "task_failed" ||
    event === "task_poisoned"
  )
}

function parseProcessingReferenceTimestamp(data) {
  const reference = data.started_at || data.processing_started_at

  if (!reference) return undefined

  const timestamp = Date.parse(reference)

  if (Number.isNaN(timestamp)) return undefined

  return timestamp
}

function updateProcessingLatencyPanel() {
  if (
    !processingLatencyEmptyEl ||
    !processingLatencySummaryEl ||
    !processingLatencyLatestEl ||
    !processingLatencyAverageEl ||
    !processingLatencyMaxEl ||
    !processingLatencyCountEl
  ) {
    return
  }

  if (!processingLatencySamples.length) {
    processingLatencyEmptyEl.classList.remove("hidden")
    processingLatencySummaryEl.classList.add("hidden")
    return
  }

  const latest = processingLatencySamples[processingLatencySamples.length - 1]
  const totalDuration = processingLatencySamples.reduce(
    (sum, sample) => sum + sample.durationMs,
    0
  )
  const averageDuration = totalDuration / processingLatencySamples.length
  const maxDuration = Math.max(...processingLatencySamples.map((sample) => sample.durationMs))

  processingLatencyLatestEl.textContent = formatQueueLatency(latest.durationMs)
  processingLatencyAverageEl.textContent = formatQueueLatency(averageDuration)
  processingLatencyMaxEl.textContent = formatQueueLatency(maxDuration)
  processingLatencyCountEl.textContent = processingLatencySamples.length

  processingLatencyEmptyEl.classList.add("hidden")
  processingLatencySummaryEl.classList.remove("hidden")
  updateSystemHealthPanel()
}

function getFailureHealthStats() {
  trimFailureRateEvents()

  const now = Date.now()
  const cutoff = now - 60_000
  const recentEvents = failureRateEvents.filter((event) => event.timestamp >= cutoff)
  const terminalEvents = recentEvents.filter((event) => isTerminalTaskEvent(event.event))
  const failedEvents = terminalEvents.filter(
    (event) => event.event === "task_failed" || event.event === "task_poisoned"
  )
  const failureRate = terminalEvents.length
    ? Math.round((failedEvents.length / terminalEvents.length) * 100)
    : 0

  return {
    failedCount: failedEvents.length,
    failureRate,
    terminalCount: terminalEvents.length,
  }
}

function averageSampleValue(samples, key) {
  if (!samples.length) return 0

  return samples.reduce((sum, sample) => sum + sample[key], 0) / samples.length
}

function maxSampleValue(samples, key) {
  if (!samples.length) return 0

  return Math.max(...samples.map((sample) => sample[key]))
}

function getWorkerHealthCounts() {
  const now = Date.now()
  const workers = Object.values(liveWorkerLastSeen)

  return {
    healthy: workers.filter((lastSeen) => now - lastSeen <= 5000).length,
    total: workers.length,
  }
}

function setSystemHealth(state, label, reason) {
  if (!systemHealthCardEl || !systemHealthStateEl || !systemHealthReasonEl) return

  systemHealthCardEl.className = `system-health-card health-${state}`
  systemHealthStateEl.textContent = label
  systemHealthReasonEl.textContent = reason
}

function updateSystemHealthPanel() {
  if (!systemHealthCardEl || !systemHealthStateEl || !systemHealthReasonEl) return

  if (!latestMetricsSnapshot) {
    setSystemHealth(
      "unknown",
      "Unknown",
      "Waiting for metrics and live events..."
    )
    return
  }

  const queueDepth = Number(
    latestMetricsSnapshot.redis_queue_length ?? latestMetricsSnapshot.queued ?? 0
  )
  const queuedTasks = Number(latestMetricsSnapshot.queued ?? 0)
  const processingTasks = Number(latestMetricsSnapshot.processing ?? 0)
  const failureStats = getFailureHealthStats()
  const averageQueueWaitMs = averageSampleValue(queueLatencySamples, "waitMs")
  const maxQueueWaitMs = maxSampleValue(queueLatencySamples, "waitMs")
  const averageProcessingMs = averageSampleValue(processingLatencySamples, "durationMs")
  const maxProcessingMs = maxSampleValue(processingLatencySamples, "durationMs")
  const workerCounts = getWorkerHealthCounts()

  if (failureStats.terminalCount >= 3 && failureStats.failureRate >= 50) {
    setSystemHealth(
      "failure-spike",
      "Failure Spike",
      `${failureStats.failedCount} of ${failureStats.terminalCount} recent terminal events failed (${failureStats.failureRate}% over the last minute).`
    )
    return
  }

  if (queueDepth > 20 || queuedTasks > 20 || (queueDepth > 5 && averageQueueWaitMs > 5_000)) {
    setSystemHealth(
      "queue-pressure",
      "Queue Pressure",
      `Queue depth is ${queueDepth} with ${queuedTasks} queued tasks; average queue wait is ${formatQueueLatency(averageQueueWaitMs)} and max wait is ${formatQueueLatency(maxQueueWaitMs)}.`
    )
    return
  }

  if (
    processingLatencySamples.length >= 3 &&
    (averageProcessingMs > 4_000 || maxProcessingMs > 10_000)
  ) {
    setSystemHealth(
      "processing-bottleneck",
      "Processing Bottleneck",
      `Workers are spending ${formatQueueLatency(averageProcessingMs)} on average per task, with a max of ${formatQueueLatency(maxProcessingMs)} across ${processingLatencySamples.length} recent terminal events.`
    )
    return
  }

  const workerText = workerCounts.total
    ? `${workerCounts.healthy}/${workerCounts.total} workers healthy`
    : "worker health not observed yet"

  setSystemHealth(
    "healthy",
    "Healthy",
    `No active pressure detected: queue depth ${queueDepth}, ${processingTasks} processing, failure rate ${failureStats.failureRate}%, ${workerText}.`
  )
}

function appendLiveEvent(data, isReplayed = false) {
  if (isLiveStreamPaused) {
    return
  }

    if (!shouldShowLiveEvent(data)) {
    return
    }

    if (!matchesLiveEventSearch(data)) {
    return
    }

  const eventCard = document.createElement("div")
  const severity = getEventSeverity(data)
  eventCard.dataset.searchText = JSON.stringify(data).toLowerCase()

  if (data.event_id) {
    eventCard.dataset.eventId = data.event_id
  }

  eventCard.className = `live-event severity-${severity}`

  if (isReplayed) {
    eventCard.classList.add("live-event-replayed")
  }

  eventCard.textContent = formatEvent(data)

  if (isReplayed) {
    const replayBadge = document.createElement("span")
    replayBadge.className = "live-event-origin"
    replayBadge.textContent = "History"
    eventCard.appendChild(replayBadge)
  }

  eventCard.addEventListener("click", () => {
    if (!eventDetailDrawer || !eventDetailContent) return

    renderEventTraceFields(data)
    eventDetailContent.textContent = JSON.stringify(data, null, 2)
    eventDetailDrawer.classList.remove("hidden")
    })
  liveEventsContainer.prepend(eventCard)

  if (liveEventsContainer.children.length > maximumLiveEvents) {
    liveEventsContainer.removeChild(liveEventsContainer.lastChild)
  }

  if (!isReplayed && (data.event.includes("failed") || data.event.includes("poison"))) {
    const message = formatEvent(data)
    showToast(message)
    addIncident(message)
  }

    if (!isReplayed && data.event === "task_succeeded") {
    recordThroughputSuccess()
    }

  updateLiveEventStats(data)

  if (!isReplayed) {
    detectFailureSpike(data)
  }
}
function renderEventTraceFields(data) {
  if (!eventTraceFields || !eventTraceId || !eventSpanId || !eventTraceLink) return

  if (!data.trace_id && !data.span_id) {
    eventTraceFields.classList.add("hidden")
    eventTraceId.textContent = ""
    eventSpanId.textContent = ""
    eventTraceLink.classList.add("hidden")
    eventTraceLink.removeAttribute("href")
    return
  }

  eventTraceId.textContent = data.trace_id || "Unavailable"
  eventSpanId.textContent = data.span_id || "Unavailable"

  if (data.trace_id) {
    eventTraceLink.href = `http://localhost:16686/trace/${data.trace_id}`
    eventTraceLink.classList.remove("hidden")
  } else {
    eventTraceLink.classList.add("hidden")
    eventTraceLink.removeAttribute("href")
  }

  eventTraceFields.classList.remove("hidden")
}
function formatEvent(data) {
  switch (data.event) {
    case "task_created":
      return `Task #${data.task_id} created`

    case "task_enqueued":
      return `Task #${data.task_id} enqueued`

    case "task_started":
      return `${data.worker_name} started task #${data.task_id}`

    case "task_succeeded":
      return `${data.worker_name} completed task #${data.task_id}`

    case "task_failed":
      return `${data.worker_name} failed task #${data.task_id}`

    case "task_retried":
      return `Retry scheduled for task #${data.task_id}`

    case "task_claimed":
        return `${data.worker_name} claimed task #${data.task_id}`

    case "task_not_ready_for_retry":
        return `Task #${data.task_id} waiting for retry`

    case "worker_processed_count_updated":
        return `${data.worker_name} processed count = ${data.processed_count}`

    case "task_poisoned":
        return `Task #${data.task_id} became poison after retries`

    default:
      return JSON.stringify(data)
  }
}
function shouldShowLiveEvent(data) {
  if (liveEventFilter === "all") return true

  if (liveEventFilter === "task") {
    return data.event.startsWith("task_")
  }

  if (liveEventFilter === "failure") {
    return data.event.includes("failed") || data.event.includes("poison")
  }

  if (liveEventFilter === "retry") {
    return data.event.includes("retry")
  }

  if (liveEventFilter === "worker") {
    return data.event.startsWith("worker_")
  }

  return true
}
function updateLiveEventStats(data) {
  if (!liveEventTotalEl || !liveEventFailuresEl || !liveEventRetriesEl) {
    return
  }

  liveEventTotal += 1

  if (data.event.includes("failed") || data.event.includes("poison")) {
    liveEventFailures += 1
  }

  if (data.event.includes("retry")) {
    liveEventRetries += 1
  }

  liveEventTotalEl.textContent = liveEventTotal
  liveEventFailuresEl.textContent = liveEventFailures
  liveEventRetriesEl.textContent = liveEventRetries
}

function showToast(message) {
  if (!toastContainer) return

  const toast = document.createElement("div")
  toast.className = "toast"
  toast.textContent = message

  toastContainer.appendChild(toast)

  setTimeout(() => {
    toast.remove()
  }, 4000)
}

function detectFailureSpike(data) {
  if (
    !data.event.includes("failed") &&
    !data.event.includes("poison")
  ) {
    return
  }

  const now = Date.now()

  recentFailures.push(now)

  const windowMs = 10_000

  while (
    recentFailures.length > 0 &&
    now - recentFailures[0] > windowMs
  ) {
    recentFailures.shift()
  }

  if (recentFailures.length >= 5) {
    triggerFailureSpikeAlert()
  }
}

function triggerFailureSpikeAlert() {
  if (!failureSpikeAlert) return

  failureSpikeAlert.classList.remove("hidden")
  addIncident("Failure spike detected")
}  

function addIncident(message) {
  if (!incidentHistoryContainer) return

  const item = document.createElement("div")
  item.className = "incident-history-item"

  const time = new Date().toLocaleTimeString()

  item.textContent = `${time} | ${message}`

  incidentHistoryContainer.prepend(item)

  if (incidentHistoryContainer.children.length > 20) {
    incidentHistoryContainer.removeChild(
      incidentHistoryContainer.lastChild
    )
  }
}
function recordThroughputSuccess() {
  throughputPoints.push(Date.now())
}

function updateThroughputChart() {
  if (!throughputChart) return

  const now = Date.now()
  const windowMs = 60_000

  while (
    throughputPoints.length > 0 &&
    now - throughputPoints[0] > windowMs
  ) {
    throughputPoints.shift()
  }

  throughputChart.data.labels.push(
    new Date().toLocaleTimeString()
  )

  throughputChart.data.datasets[0].data.push(
    throughputPoints.length
  )

  if (throughputChart.data.labels.length > 30) {
    throughputChart.data.labels.shift()
    throughputChart.data.datasets[0].data.shift()
  }

  throughputChart.update()
}

function updateWorkerHealth() {
  const now = Date.now()

  Object.entries(liveWorkerLastSeen).forEach(([workerName, lastSeen]) => {
    const item = document.getElementById(`live-worker-${workerName}`)

    if (!item) return

    const isStale = now - lastSeen > 5000

    if (isStale && !reportedStaleWorkers.has(workerName)) {
      reportedStaleWorkers.add(workerName)

      const message = `${workerName} became stale`

      addIncident(message)
      showToast(message)
    }

    if (!isStale && reportedStaleWorkers.has(workerName)) {
      const message = `${workerName} recovered`

      addIncident(message)
      showToast(message)

      reportedStaleWorkers.delete(workerName)
    }

    item.classList.toggle("worker-stale", isStale)
    item.classList.toggle("worker-healthy", !isStale)
  })

  updateSystemHealthPanel()
}

function getEventSeverity(data) {
  const event = data.event

  if (event.includes("poison")) {
    return "critical"
  }

  if (
    event.includes("failed") ||
    event.includes("stale")
  ) {
    return "error"
  }

  if (
    event.includes("retry")
  ) {
    return "warning"
  }

  return "info"
}

function matchesLiveEventSearch(data) {
  if (!liveEventSearchQuery) {
    return true
  }

  const text =
    JSON.stringify(data).toLowerCase()

  return text.includes(
    liveEventSearchQuery
  )
}

function applyLiveEventSearchFilter() {
  const items =
    document.querySelectorAll(".live-event")

  items.forEach((item) => {
    const matches =
      item.dataset.searchText.includes(
        liveEventSearchQuery
      )

    item.style.display =
      matches ? "" : "none"
  })
}

setInterval(updateWorkerHealth, 1000)
setInterval(updateThroughputChart, 1000)
setInterval(updateFailureRateChart, 1000)
setInterval(updateDeliveryMetricsPanel, 1000)
setInterval(updateWorkerThroughputPanel, 1000)
setInterval(updateSystemHealthPanel, 1000)
