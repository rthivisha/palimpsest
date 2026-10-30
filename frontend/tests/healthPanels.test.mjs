import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * Unit tests for frontend health panel state logic, offline button disablement,
 * auto-enable transitions without reload, and fallback badge visibility.
 */

function deriveUiState(health, isRunning = false, is429Blocked = false, expression = 'x + y') {
  const isModelReachable = health?.model_status
    ? health.model_status === 'ready'
    : health?.model_reachable !== false;

  const showOllamaNotRunningPanel = health?.model_status === 'ollama_not_running';
  const showModelMissingPanel = health?.model_status === 'model_missing';

  const isSubmitDisabled = isRunning || is429Blocked || !expression.trim() || isModelReachable === false;
  const buttonLabel = isModelReachable === false
    ? 'MODEL OFFLINE'
    : isRunning
    ? 'RUNNING CEGIS...'
    : 'DE-OBFUSCATE';

  const showFallbackBadge = Boolean(health?.is_fallback);

  return {
    isModelReachable,
    showOllamaNotRunningPanel,
    showModelMissingPanel,
    isSubmitDisabled,
    buttonLabel,
    showFallbackBadge,
  };
}

test('UI State: ollama_not_running renders distinct panel, disables submit with MODEL OFFLINE', () => {
  const health = {
    status: 'ok',
    backend: 'ollama',
    model_name: 'palimpsest',
    model_status: 'ollama_not_running',
    model_reachable: false,
    hint: 'Ollama is not running at http://127.0.0.1:11434',
    fix_command: 'ollama serve',
  };

  const ui = deriveUiState(health);
  assert.equal(ui.isModelReachable, false);
  assert.equal(ui.showOllamaNotRunningPanel, true);
  assert.equal(ui.showModelMissingPanel, false);
  assert.equal(ui.isSubmitDisabled, true);
  assert.equal(ui.buttonLabel, 'MODEL OFFLINE');
  assert.equal(health.fix_command, 'ollama serve');
});

test('UI State: model_missing renders distinct panel with create command and disables submit', () => {
  const health = {
    status: 'ok',
    backend: 'ollama',
    model_name: 'palimpsest',
    model_status: 'model_missing',
    model_reachable: false,
    hint: 'Model "palimpsest" not found in catalog',
    fix_command: 'ollama create palimpsest -f Modelfile',
  };

  const ui = deriveUiState(health);
  assert.equal(ui.isModelReachable, false);
  assert.equal(ui.showOllamaNotRunningPanel, false);
  assert.equal(ui.showModelMissingPanel, true);
  assert.equal(ui.isSubmitDisabled, true);
  assert.equal(ui.buttonLabel, 'MODEL OFFLINE');
  assert.equal(health.fix_command, 'ollama create palimpsest -f Modelfile');
});

test('UI State: auto-enables De-obfuscate when status transitions to ready without reload', () => {
  // Step 1: offline
  const offlineHealth = {
    model_status: 'ollama_not_running',
    model_reachable: false,
  };
  const step1 = deriveUiState(offlineHealth);
  assert.equal(step1.isSubmitDisabled, true);
  assert.equal(step1.buttonLabel, 'MODEL OFFLINE');

  // Step 2: 5s poll returns ready
  const readyHealth = {
    model_status: 'ready',
    model_reachable: true,
  };
  const step2 = deriveUiState(readyHealth);
  assert.equal(step2.isModelReachable, true);
  assert.equal(step2.showOllamaNotRunningPanel, false);
  assert.equal(step2.showModelMissingPanel, false);
  assert.equal(step2.isSubmitDisabled, false);
  assert.equal(step2.buttonLabel, 'DE-OBFUSCATE');
});

test('UI State: fallback to llama.cpp activates visible fallback badge and keeps model ready', () => {
  const fallbackHealth = {
    status: 'ok',
    backend: 'ollama',
    model_name: 'palimpsest-q4_k_m.gguf',
    model_status: 'ready',
    model_reachable: true,
    is_fallback: true,
    fallback_backend: 'llamacpp',
  };

  const ui = deriveUiState(fallbackHealth);
  assert.equal(ui.isModelReachable, true);
  assert.equal(ui.showFallbackBadge, true);
  assert.equal(ui.isSubmitDisabled, false);
  assert.equal(ui.buttonLabel, 'DE-OBFUSCATE');
});

test('UI State: never enables fallback badge when fallback is inactive', () => {
  const normalHealth = {
    status: 'ok',
    backend: 'ollama',
    model_status: 'ready',
    model_reachable: true,
    is_fallback: false,
  };

  const ui = deriveUiState(normalHealth);
  assert.equal(ui.showFallbackBadge, false);
});

