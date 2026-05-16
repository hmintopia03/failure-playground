let currentFilter = "all";
let refreshInProgress = false;
let taskChart = null;
let workerChart = null;

let taskOffset = 0;
let taskLimit = 20;

let logOffset = 0;
let logLimit = 30;

let taskTotal = 0;


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

    if (typeof Chart === "undefined") {
        console.warn("Chart.js is not loaded");
        return;
    }

    const chartData = {
        labels: ["Queued", "Processing", "Success", "Failed"],
        datasets: [{
            label: "Tasks",
            data: [
                data.queued,
                data.processing,
                data.success,
                data.failed,
            ],
        }],
    };

    const ctx = document.getElementById("task-chart");

    if (taskChart) {
        taskChart.destroy();
    }

    taskChart = new Chart(ctx, {
        type: "bar",
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
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
        uptime: ${formatUptime(uptime)}`;
} else {
    el.innerHTML =
        `<b style="color:green">SYSTEM RUNNING</b>
        <br>
        environment: ${environment}
        <br>
        version: ${version}
        <br>
        uptime: ${formatUptime(uptime)}`;
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

document
    .getElementById("refresh-interval")
    .addEventListener("change", startRefreshTimer);

startRefreshTimer();

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

document.addEventListener("DOMContentLoaded", () => {
    const statusFilter = document.getElementById("task-status-filter");
    const poisonFilter = document.getElementById("task-poison-filter");
    const logTaskIdFilter = document.getElementById("log-task-id-filter");

    if (statusFilter) {
        statusFilter.addEventListener("change", loadTasks);
    }

    if (poisonFilter) {
        poisonFilter.addEventListener("change", loadTasks);
    }

    if (logTaskIdFilter) {
        logTaskIdFilter.addEventListener("keydown", event => {
            if (event.key === "Enter") {
                loadLogs();
            }
        });
    }
});