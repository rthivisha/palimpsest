const path = require('path');
const { spawnSync } = require('child_process');

// Sanitize ComSpec on Windows to prevent gitleaks from hijacking shell calls
if (process.platform === 'win32') {
  const cmdPath = process.env.SystemRoot
    ? path.join(process.env.SystemRoot, 'System32', 'cmd.exe')
    : 'C:\\Windows\\system32\\cmd.exe';
  process.env.ComSpec = cmdPath;
  process.env.COMSPEC = cmdPath;
}

const pythonExe = process.platform === 'win32'
  ? path.join('.venv', 'Scripts', 'python.exe')
  : path.join('.venv', 'bin', 'python');

console.log('[PALIMPSEST TEST] Running backend test suite (pytest)...');
const resBackend = spawnSync(pythonExe, ['-m', 'pytest', 'backend/tests'], {
  stdio: 'inherit',
  shell: false,
  env: process.env,
});

if (resBackend.status !== 0) {
  process.exit(resBackend.status || 1);
}

console.log('\n[PALIMPSEST TEST] Running frontend unit tests (node --test)...');
const resFrontend = spawnSync(process.execPath, ['--test', 'frontend/tests/compression.test.mjs', 'frontend/tests/replay.test.mjs'], {
  stdio: 'inherit',
  shell: false,
  env: process.env,
});

if (resFrontend.status !== 0) {
  process.exit(resFrontend.status || 1);
}

console.log('\n[PALIMPSEST TEST] All test suites passed successfully.');

