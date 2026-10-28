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
console.log('  PALIMPSEST Production/Testing Servers Starting (No Auto-Reload)');
console.log('  - Frontend:    http://127.0.0.1:5173 (strictly bound to IPv4 127.0.0.1)');
console.log('  - Backend API: http://127.0.0.1:8000 (strictly bound to IPv4 127.0.0.1)');
console.log('======================================================================');

const { result, commands } = concurrently(
  [
    {
      command: 'npm run start:backend',
      name: 'backend',
      prefixColor: 'blue',
      env: extraEnv,
    },
    {
      command: 'npm run start:frontend',
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

process.on('SIGINT', () => {
  console.log('\n[PALIMPSEST START] Received Ctrl+C (SIGINT). Stopping both servers cleanly...');
});

process.on('SIGTERM', () => {
  console.log('\n[PALIMPSEST START] Received SIGTERM. Stopping both servers cleanly...');
});

result.then(
  () => process.exit(0),
  (err) => {
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
