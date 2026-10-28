const path = require('path');
const concurrently = require('concurrently').default || require('concurrently');

// On Windows, sanitize ComSpec to point strictly to genuine Windows cmd.exe
const extraEnv = {};
if (process.platform === 'win32') {
  const cmdPath = process.env.SystemRoot
    ? path.join(process.env.SystemRoot, 'System32', 'cmd.exe')
    : 'C:\\Windows\\system32\\cmd.exe';

  process.env.ComSpec = cmdPath;
  process.env.COMSPEC = cmdPath;
  extraEnv.ComSpec = cmdPath;
  extraEnv.COMSPEC = cmdPath;
}

console.log('======================================================================');
console.log('  PALIMPSEST Dev/Test Servers Starting (Vite Dev Server + Uvicorn Backend, No Auto-Reload)');
console.log('  - Frontend:    http://127.0.0.1:5173 (strictly bound to IPv4 127.0.0.1)');
console.log('  - Backend API: http://127.0.0.1:8000 (strictly bound to IPv4 127.0.0.1)');
console.log('======================================================================');

const pythonBin =
  process.platform === 'win32'
    ? path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', '.venv', 'bin', 'python');

const backendCmd = `"${pythonBin}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`;
const frontendCmd = 'cd frontend && node node_modules/vite/bin/vite.js';

const { result, commands } = concurrently(
  [
    {
      command: backendCmd,
      name: 'backend',
      prefixColor: 'blue',
      env: extraEnv,
    },
    {
      command: frontendCmd,
      name: 'frontend',
      prefixColor: 'cyan',
      env: extraEnv,
    },
  ],
  {
    killOthersOn: ['failure', 'success'],
  }
);

commands.forEach((cmd) => {
  cmd.close.subscribe((info) => {
    if (info.exitCode !== 0 && !info.killed) {
      console.error(
        `\n[PALIMPSEST START ERROR] Server '${cmd.name}' exited with code: ${info.exitCode}. Stopping both servers.\n`
      );
    } else if (!info.killed) {
      console.log(
        `\n[PALIMPSEST START] Server '${cmd.name}' exited cleanly (code 0). Stopping both servers.\n`
      );
    }
  });
});

let isShuttingDown = false;
const handleShutdown = (signalName) => {
  if (isShuttingDown) return;
  isShuttingDown = true;
  console.log(`\n[PALIMPSEST START] Received ${signalName}. Gracefully stopping servers...`);
  commands.forEach((c) => {
    try {
      c.kill();
    } catch (_) {}
  });
  // Fallback timeout to ensure process termination if a child hangs
  setTimeout(() => {
    process.exit(0);
  }, 4000);
};

process.on('SIGINT', () => handleShutdown('Ctrl+C (SIGINT)'));
process.on('SIGBREAK', () => handleShutdown('Ctrl+Break (SIGBREAK)'));
process.on('SIGTERM', () => handleShutdown('SIGTERM'));

result.then(
  () => process.exit(0),
  (err) => {
    if (isShuttingDown) {
      process.exit(0);
    }
    if (Array.isArray(err)) {
      for (const e of err) {
        if (!e.killed && e.exitCode !== 0) {
          console.error(
            `[PALIMPSEST START] Process failure: '${e.command ? e.command.name : 'unknown'}' exited with code ${e.exitCode}.`
          );
        }
      }
    }
    process.exit(1);
  }
);
