const path = require('path');
const concurrently = require('concurrently').default || require('concurrently');

// On Windows, sanitize ComSpec to point strictly to genuine Windows cmd.exe
// to prevent external CLI tools from hijacking command execution.
// On macOS and Linux, process.platform is 'darwin' / 'linux' and standard shell resolution applies.
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
console.log('  PALIMPSEST De-obfuscation Engine Dev Servers Starting');
console.log('  - Frontend:    http://127.0.0.1:5173 (or http://localhost:5173)');
console.log('  - Backend API: http://127.0.0.1:8000 (Docs: http://127.0.0.1:8000/docs)');
console.log('======================================================================');

const { result, commands } = concurrently(
  [
    {
      command: 'npm run dev:backend',
      name: 'backend',
      prefixColor: 'blue',
      env: extraEnv,
    },
    {
      command: 'npm run dev:frontend',
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
        `\n[PALIMPSEST DEV ERROR] Server '${cmd.name}' exited with failure code: ${info.exitCode}. Stopping both servers.\n`
      );
    } else if (!info.killed) {
      console.log(
        `\n[PALIMPSEST DEV] Server '${cmd.name}' exited cleanly (code 0). Stopping both servers.\n`
      );
    }
  });
});

result.then(
  () => {
    process.exit(0);
  },
  (err) => {
    if (Array.isArray(err)) {
      for (const e of err) {
        if (!e.killed && e.exitCode !== 0) {
          console.error(
            `[PALIMPSEST DEV] Process failure: '${e.command ? e.command.name : 'unknown'}' exited with code ${e.exitCode}.`
          );
        }
      }
    }
    process.exit(1);
  }
);
