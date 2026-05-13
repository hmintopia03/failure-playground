let currentFilter = "all";
let refreshInProgress = false;
let taskChart = null;
let workerChart = null;

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
async function loadMetrics() {
const data = await fetchJson("/metrics");
const queueClass = data.queued > 20 ? "card-danger" : data.queued > 5 ? "card-warning" : "card-good";
const failedClass = data.failed > 5 ? "card-danger" : data.failed > 0 ? "card-warning" : "card-good";

document.getElementById("metrics-cards").innerHTML = `
    <div class="card ${queueClass}"><span>Queued</span><strong>${data.queued}</strong></div>
    <div class="card"><span>Processing</span><strong>${data.processing}</strong></div>
    <div class="card"><span>Success</span><strong>${data.success}</strong></div>
    <div class="card ${failedClass}"><span>Failed</span><strong>${data.failed}</strong></div>
    <div class="card"><span>Workers Alive</span><strong>${data.alive_workers}</strong></div>
    <div class="card"><span>Throughput/min</span><strong>${data.throughput_last_minute}</strong></div>
`;
const warningEl =
    document.getElementById("queue-warning");

if (data.redis_queue_length > 20) {
    warningEl.innerHTML =
        "<b style='color:red'>HIGH QUEUE PRESSURE</b>";
} else {
    warningEl.innerHTML = "";
}

document.getElementById("metrics").textContent =
    JSON.stringify(data, null, 2);

const chartData = {
    labels: [
        "Queued",
        "Processing",
        "Success",
        "Failed",
    ],
    datasets: [{
        label: "Tasks",
        data: [
            data.queued,
            data.processing,
            data.success,
            data.failed,
        ],
    }]
};

const ctx =
    document.getElementById("task-chart");

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
if (typeof Chart !== "undefined") {
    const ctx =
        document.getElementById("task-chart");

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
}

async function loadTasks() {
const response = await fetch("/tasks");
const tasks = await response.json();
const visibleTasks =
currentFilter === "all"
    ? tasks
    : tasks.filter(task => task.status === currentFilter);
const searchValue =
document
    .getElementById("task-search")
    .value
    .trim();
const table =
    document.getElementById("tasks-table");

table.innerHTML = "";

let searchedTasks =
    searchValue === ""
        ? visibleTasks
        : visibleTasks.filter(task =>
            String(task.id).includes(searchValue)
        );

const sortValue =
    document.getElementById("task-sort").value;

searchedTasks.sort((a, b) => {
    if (sortValue === "id-asc") {
        return a.id - b.id;
    }

    if (sortValue === "id-desc") {
        return b.id - a.id;
    }

    if (sortValue === "priority") {
        return a.priority - b.priority;
    }

    if (sortValue === "retries") {
        return b.retry_count - a.retry_count;
    }

    return 0;
});


searchedTasks.forEach(task => {
    const row = document.createElement("tr");
    row.className = `row-${task.status}`;
    const createdAt = new Date(task.created_at + "Z");
    const ageSeconds = Math.floor((Date.now() - createdAt) / 1000);
    const isOldQueuedTask = task.status === "queued" && ageSeconds > 30;
    if (isOldQueuedTask) {
        row.className += " old-queued";
    }
    row.innerHTML = `
        <td>${task.id}</td>
        <td>${formatAge(ageSeconds)}</td>
        <td class="status ${task.status}">
            ${task.status}
        </td>
        <td>${task.priority}</td>
        <td>${task.retry_count}</td>
        <td>${task.failure_reason || ""}</td>
        <td>${task.is_poison ? "yes" : ""}</td>
        <td>
            ${
                task.status === "failed"
                    ? `<button onclick="retryTask(${task.id})">Retry</button>`
                    : ""
            }
            <button onclick="duplicateTask(${task.id})">
                Duplicate
            </button>
        </td>
        <td>
            <a href="/tasks/${task.id}" target="_blank">Open</a>
        </td>
    `;

    table.appendChild(row);
});
}

async function loadLogs() {
const response = await fetch("/logs");
const logs = await response.json();

const recentLogs = logs.slice(-15);

const logsPanel =
    document.getElementById("logs-panel");

logsPanel.textContent =
    recentLogs
        .map(log =>
            `[${log.created_at}] Task ${log.task_id}: ${log.message}`
        )
        .join("\n");

const autoScroll =
    document.getElementById("auto-scroll-logs").checked;

if (autoScroll) {
    logsPanel.scrollTop = logsPanel.scrollHeight;
}
    recentLogs
        .map(log =>
            `[${log.created_at}] Task ${log.task_id}: ${log.message}`
        )
        .join("\\n");
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
        .join("\\n");
        const workerCtx =
            document.getElementById("worker-chart");

        const workerChartData = {
            labels: workers.map(worker => worker.worker_name),
            datasets: [{
                label: "Processed Tasks",
                data: workers.map(worker => worker.processed_count),
            }]
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
        if (typeof Chart !== "undefined") {
    const workerCtx =
        document.getElementById("worker-chart");

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