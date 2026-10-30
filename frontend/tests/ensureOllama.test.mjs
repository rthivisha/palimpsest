import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  resolveOllamaBaseUrl,
  ensureOllama,
  checkPalimpsestModel,
} = require('../../scripts/ensure-ollama.js');

test('resolveOllamaBaseUrl: defaults to http://127.0.0.1:11434', () => {
  const url = resolveOllamaBaseUrl({});
  assert.equal(url, 'http://127.0.0.1:11434');
});

test('resolveOllamaBaseUrl: honours OLLAMA_BASE_URL and strips trailing slash', () => {
  const url = resolveOllamaBaseUrl({ OLLAMA_BASE_URL: 'http://localhost:11434/' });
  assert.equal(url, 'http://localhost:11434');
});

test('resolveOllamaBaseUrl: maps 0.0.0.0 to 127.0.0.1 and prefixes http if missing', () => {
  const url1 = resolveOllamaBaseUrl({ OLLAMA_HOST: '0.0.0.0:11434' });
  assert.equal(url1, 'http://127.0.0.1:11434');

  const url2 = resolveOllamaBaseUrl({ OLLAMA_HOST: ':11434' });
  assert.equal(url2, 'http://127.0.0.1:11434');

  const url3 = resolveOllamaBaseUrl({ OLLAMA_HOST: 'http://0.0.0.0:11434' });
  assert.equal(url3, 'http://127.0.0.1:11434');
});

test('ensureOllama: detects already running daemon and does not spawn', async () => {
  let spawnCalled = false;
  const logs = [];

  const mockFetch = async (url) => {
    return {
      ok: true,
      json: async () => ({ models: [{ name: 'palimpsest:latest' }] }),
    };
  };

  const res = await ensureOllama({
    env: { OLLAMA_BASE_URL: 'http://127.0.0.1:11434' },
    fetchFn: mockFetch,
    spawnFn: () => {
      spawnCalled = true;
      return { unref: () => {} };
    },
    checkExecutableFn: () => true,
    logFn: (msg) => logs.push(msg),
  });

  assert.equal(res.status, 'already_running');
  assert.equal(spawnCalled, false);
  assert.match(logs[0], /already running at http:\/\/127\.0\.0\.1:11434/);
});

test('ensureOllama: spawns detached and polls until reachable when daemon offline', async () => {
  let spawnArgs = null;
  const logs = [];
  let pollAttempts = 0;

  const mockFetch = async () => {
    pollAttempts++;
    if (pollAttempts === 1) {
      throw new Error('Connection refused');
    }
    return {
      ok: true,
      json: async () => ({ models: [{ name: 'palimpsest' }] }),
    };
  };

  const res = await ensureOllama({
    env: { OLLAMA_BASE_URL: 'http://127.0.0.1:11434' },
    fetchFn: mockFetch,
    spawnFn: (cmd, args, opts) => {
      spawnArgs = { cmd, args, opts };
      return { unref: () => {} };
    },
    checkExecutableFn: () => true,
    sleepFn: async () => {},
    pollTimeoutMs: 5000,
    pollIntervalMs: 10,
    logFn: (msg) => logs.push(msg),
  });

  assert.equal(res.status, 'started_by_script');
  assert.ok(spawnArgs);
  assert.equal(spawnArgs.cmd, 'ollama');
  assert.deepEqual(spawnArgs.args, ['serve']);
  assert.equal(spawnArgs.opts.detached, true);
  assert.equal(spawnArgs.opts.windowsHide, true);
  assert.equal(spawnArgs.opts.stdio, 'ignore');
  assert.match(logs[0], /started by the script at http:\/\/127\.0\.0\.1:11434/);
});

test('ensureOllama: prints install guidance and continues without blocking when executable missing', async () => {
  let spawnCalled = false;
  const logs = [];

  const mockFetch = async () => {
    throw new Error('Connection refused');
  };

  const res = await ensureOllama({
    env: { OLLAMA_BASE_URL: 'http://127.0.0.1:11434' },
    fetchFn: mockFetch,
    spawnFn: () => {
      spawnCalled = true;
      return { unref: () => {} };
    },
    checkExecutableFn: () => false,
    logFn: (msg) => logs.push(msg),
  });

  assert.equal(res.status, 'executable_missing');
  assert.equal(spawnCalled, false);
  assert.match(logs[0], /executable not found on PATH/);
  assert.match(logs[0], /https:\/\/ollama\.com/);
});

test('ensureOllama: prints failed message when polling times out', async () => {
  let spawnCalled = false;
  const logs = [];

  const mockFetch = async () => {
    throw new Error('Connection refused');
  };

  const res = await ensureOllama({
    env: { OLLAMA_BASE_URL: 'http://127.0.0.1:11434' },
    fetchFn: mockFetch,
    spawnFn: () => {
      spawnCalled = true;
      return { unref: () => {} };
    },
    checkExecutableFn: () => true,
    sleepFn: async () => {},
    pollTimeoutMs: 50,
    pollIntervalMs: 10,
    logFn: (msg) => logs.push(msg),
  });

  assert.equal(res.status, 'failed');
  assert.equal(spawnCalled, true);
  assert.match(logs[0], /failed to start/);
});

test('checkPalimpsestModel: prints exact create command when palimpsest is missing from catalog', () => {
  const logs = [];
  checkPalimpsestModel(['qwen2.5:3b', 'llama3:8b'], (msg) => logs.push(msg));
  assert.equal(logs.length, 1);
  assert.equal(logs[0], 'ollama create palimpsest -f Modelfile');

  // When palimpsest exists, nothing is printed
  logs.length = 0;
  checkPalimpsestModel(['palimpsest:latest'], (msg) => logs.push(msg));
  assert.equal(logs.length, 0);
});

