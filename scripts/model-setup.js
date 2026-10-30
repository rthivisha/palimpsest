const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const modelGguf = path.join(__dirname, '..', 'models', 'palimpsest-q4_k_m.gguf');
const modelfile = path.join(__dirname, '..', 'Modelfile');

if (!fs.existsSync(modelGguf)) {
  console.error('\n[PALIMPSEST ERROR] GGUF model file not found at: ' + modelGguf);
  console.error('Please place the quantized model palimpsest-q4_k_m.gguf into the models/ directory before running setup.\n');
  process.exit(1);
}

if (!fs.existsSync(modelfile)) {
  console.error('\n[PALIMPSEST ERROR] Modelfile not found at: ' + modelfile + '\n');
  process.exit(1);
}

console.log('[PALIMPSEST] Found model GGUF at:', modelGguf);
console.log('[PALIMPSEST] Running manual model creation: ollama create palimpsest -f Modelfile');

const tool = process.platform === 'win32' ? 'ollama.exe' : 'ollama';
const res = spawnSync(tool, ['create', 'palimpsest', '-f', 'Modelfile'], {
  stdio: 'inherit',
  shell: false,
});

if (res.error) {
  console.error('[PALIMPSEST ERROR] Failed to invoke ollama CLI:', res.error.message);
  process.exit(1);
}

process.exit(res.status || 0);

