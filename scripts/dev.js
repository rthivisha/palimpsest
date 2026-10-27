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

const { result } = concurrently(
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
    killOthersOn: ['failure'],
  }
);

result.catch((_err) => {
  // Exit cleanly if child was terminated
  process.exit(1);
});
