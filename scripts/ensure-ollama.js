const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

/**
 * Resolves Ollama base URL from environment or .env file.
 * Defaults to http://127.0.0.1:11434.
 * Also honours OLLAMA_HOST, adding scheme if missing and mapping 0.0.0.0 to 127.0.0.1.
 */
function resolveOllamaBaseUrl(customEnv = null) {
  const env = customEnv || { ...loadDotEnv(), ...process.env };
  let url = env.OLLAMA_BASE_URL;

  if (!url && env.OLLAMA_HOST) {
    let host = env.OLLAMA_HOST.trim();
    if (host.startsWith(':')) {
      host = '127.0.0.1' + host;
    }
    if (!host.startsWith('http://') && !host.startsWith('https://')) {
      host = 'http://' + host;
    }
    url = host;
  }

  if (!url) {
    url = 'http://127.0.0.1:11434';
  }

  // Map 0.0.0.0 to 127.0.0.1
  url = url.replace(/0\.0\.0\.0/g, '127.0.0.1');
  return url.replace(/\/+$/, '');
}

/**
 * Minimal helper to read key-value pairs from .env in project root without external dependencies.
 */
function loadDotEnv(envFilePath = null) {
  const targetPath = envFilePath || path.join(__dirname, '..', '.env');
  const values = {};
  if (!fs.existsSync(targetPath)) return values;

  try {
    const content = fs.readFileSync(targetPath, 'utf8');
    for (const rawLine of content.split('\n')) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;
      const eqIdx = line.indexOf('=');
      if (eqIdx !== -1) {
        const k = line.slice(0, eqIdx).trim();
        const v = line.slice(eqIdx + 1).trim();
        values[k] = v;
      }
    }
  } catch (_) {}
  return values;
}

/**
 * Checks if the ollama executable exists on PATH.
 */
function checkOllamaExecutable() {
  const tool = process.platform === 'win32' ? 'where.exe' : 'which';
  try {
    const res = spawnSync(tool, ['ollama'], {
      stdio: 'ignore',
      shell: false,
    });
    return res.status === 0;
  } catch {
    return false;
  }
}

/**
 * Probes GET /api/tags on the specified Ollama base URL with a timeout.
 */
async function probeTags(baseUrl, fetchFn = globalThis.fetch, timeoutMs = 1000) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetchFn(`${baseUrl}/api/tags`, { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) {
      return { reachable: false, models: [] };
    }
    const data = await res.json();
    const models = Array.isArray(data.models)
      ? data.models.map((m) => (typeof m === 'string' ? m : m.name || ''))
      : [];
    return { reachable: true, models };
  } catch {
    return { reachable: false, models: [] };
  }
}

/**
 * Main ensure-ollama logic with full dependency injection for testing.
 */
async function ensureOllama(options = {}) {
  const {
    env = null,
    fetchFn = globalThis.fetch,
    spawnFn = spawn,
    checkExecutableFn = checkOllamaExecutable,
    sleepFn = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    pollTimeoutMs = 20000,
    pollIntervalMs = 500,
    logFn = console.log,
  } = options;

  const baseUrl = resolveOllamaBaseUrl(env);

  // 1. First probe: is Ollama already running?
  const initialProbe = await probeTags(baseUrl, fetchFn, 1000);
  if (initialProbe.reachable) {
    logFn(`[PALIMPSEST] Ollama status: already running at ${baseUrl}`);
    checkPalimpsestModel(initialProbe.models, logFn);
    return { status: 'already_running', baseUrl, models: initialProbe.models };
  }

  // 2. Not reachable: check if ollama executable is on PATH
  const hasExecutable = checkExecutableFn();
  if (!hasExecutable) {
    logFn(
      `[PALIMPSEST] Ollama executable not found on PATH. Install Ollama from https://ollama.com to enable local models.`
    );
    return { status: 'executable_missing', baseUrl };
  }

  // 3. Executable found: spawn detached process (hidden window, stdio ignored)
  try {
    const child = spawnFn('ollama', ['serve'], {
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
    });
    if (child && typeof child.unref === 'function') {
      child.unref();
    }
  } catch (err) {
    logFn(`[PALIMPSEST] Ollama status: failed (spawn error: ${err.message})`);
    return { status: 'failed', baseUrl, error: err.message };
  }

  // 4. Poll /api/tags for up to 20 s
  const startTime = Date.now();
  while (Date.now() - startTime < pollTimeoutMs) {
    await sleepFn(pollIntervalMs);
    const probe = await probeTags(baseUrl, fetchFn, 1000);
    if (probe.reachable) {
      logFn(`[PALIMPSEST] Ollama status: started by the script at ${baseUrl}`);
      checkPalimpsestModel(probe.models, logFn);
      return { status: 'started_by_script', baseUrl, models: probe.models };
    }
  }

  // 5. Timed out
  logFn(`[PALIMPSEST] Ollama status: failed to start within ${Math.round(pollTimeoutMs / 1000)}s`);
  return { status: 'failed', baseUrl };
}

function checkPalimpsestModel(models, logFn = console.log) {
  const found = models.some((m) => m === 'palimpsest' || m.startsWith('palimpsest:'));
  if (!found) {
    logFn('ollama create palimpsest -f Modelfile');
  }
}

// If executed directly from command line
if (require.main === module) {
  ensureOllama().then(() => {
    process.exit(0);
  }).catch((err) => {
    console.error('[PALIMPSEST] ensure-ollama encountered error:', err);
    process.exit(0); // Continue starting app without blocking
  });
}

module.exports = {
  resolveOllamaBaseUrl,
  loadDotEnv,
  checkOllamaExecutable,
  probeTags,
  ensureOllama,
  checkPalimpsestModel,
};
