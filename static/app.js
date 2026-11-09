const form = document.querySelector("#form");
const input = document.querySelector("#url");
const button = document.querySelector("#convert");
const status = document.querySelector("#status");
const message = document.querySelector("#status-text");
const download = document.querySelector("#download");
let mode = "track";
let busy = false;
let ready = false;
let connecting = false;
const connectionText = document.querySelector("#connection-text");
const connectionRetry = document.querySelector("#connection-retry");
async function wakeServer() {
  if (connecting) return;
  connecting = true;
  ready = false;
  button.disabled = true;
  connectionRetry.hidden = true;
  connectionText.textContent = "Connecting to the server…";
  for (let attempt = 0; attempt < 12; attempt++) {
    try {
      const response = await fetch("/api/health", {
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
      if (response.ok && (await response.json()).status === "ok") {
        ready = true;
        connecting = false;
        connectionText.textContent = "Ready";
        button.disabled = busy;
        return;
      }
    } catch (_) {
      // A sleeping service or a brief network failure can recover on the next attempt.
    }
    connectionText.textContent = "Starting up the server. This can take about a minute…";
    if (attempt < 11) await new Promise(resolve => setTimeout(resolve, 2000));
  }
  connecting = false;
  connectionText.textContent = "Couldn’t reach the server. Please try again.";
  connectionRetry.hidden = false;
}
connectionRetry.addEventListener("click", wakeServer);
wakeServer();
document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    if (busy) return;
    mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach((item) => {
      item.classList.toggle("active", item === tab);
      item.setAttribute("aria-pressed", String(item === tab));
    });
    document.querySelector("#link-label").textContent =
      mode === "playlist" ? "SoundCloud playlist link" : "Track link";
    document.querySelector("#hint").textContent =
      mode === "playlist"
        ? "All tracks joined in playlist order · Up to 100 tracks"
        : "YouTube or SoundCloud";
    document.querySelector("#mode-note").textContent =
      mode === "playlist"
        ? "All tracks combined into one MP3, in playlist order."
        : "Paste a link above. Your MP3 will be ready to save here.";
    input.placeholder =
      mode === "playlist"
        ? "https://soundcloud.com/artist/sets/playlist"
        : "https://youtube.com/watch?v=…";
  }),
);
async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}
function formatDuration(seconds) {
  seconds = Math.max(0, Math.ceil(seconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${remainder}`
    : `${minutes}:${remainder}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !ready) return;
  busy = true;
  button.disabled = true;
  button.textContent = "Converting…";
  status.hidden = false;
  status.classList.remove("error");
  download.hidden = true;
  message.textContent = "Starting conversion…";
  document.querySelector("#progress").removeAttribute("value");
  document.querySelector("#percent").textContent = "";
  const started = performance.now();
  const elapsed = document.querySelector("#elapsed");
  const remaining = document.querySelector("#remaining");
  let estimatedFinish = null;
  let finished = false;
  function renderTiming() {
    elapsed.textContent = `Elapsed: ${formatDuration((performance.now() - started) / 1000)}`;
    remaining.textContent = finished ? "Complete" : estimatedFinish === null
      ? "Time remaining: estimating…"
      : `Estimated remaining: ${formatDuration(Math.max(1, (estimatedFinish - performance.now()) / 1000))}`;
  }
  renderTiming();
  const timer = setInterval(renderTiming, 1000);
  try {
    const job = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: input.value.trim(), mode }),
    });
    while (true) {
      const progress = await api(`/api/jobs/${job.id}`);
      message.textContent = progress.message;
      // Progress includes a reserved share for conversion; this is an approximate
      // whole-job estimate. Recalculate when a stage has no measurable progress.
      const fraction = progress.progress / 100;
      estimatedFinish = typeof progress.progress === "number" && fraction > 0 && fraction < 1
        ? performance.now() + (performance.now() - started) * (1 - fraction) / fraction
        : null;
      finished = progress.status === "done";
      renderTiming();
      const bar = document.querySelector("#progress");
      const percent = document.querySelector("#percent");
      if (typeof progress.progress === "number") {
        bar.value = progress.progress;
        percent.textContent = `${Math.round(progress.progress)}%`;
      } else {
        bar.removeAttribute("value");
        percent.textContent = "";
      }
      if (progress.status === "error") throw new Error(progress.message);
      if (progress.status === "done") {
        download.href = `/api/jobs/${job.id}/download`;
        download.hidden = false;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  } catch (error) {
    status.classList.add("error");
    message.textContent = error.message;
    document.querySelector("#percent").textContent = "";
  } finally {
    clearInterval(timer);
    renderTiming();
    if (!finished) remaining.textContent = "Time remaining: unavailable";
    busy = false;
    button.disabled = !ready;
    button.innerHTML = "Convert to MP3 <span>↗</span>";
  }
});
