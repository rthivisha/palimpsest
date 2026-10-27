const path = require('path');
const concurrently = require('concurrently').default || require('concurrently');

// Sanitize ComSpec to point strictly to the genuine Windows cmd.exe
const cmdPath = process.env.SystemRoot
  ? path.join(process.env.SystemRoot, 'System32', 'cmd.exe')
  : 'C:\\Windows\\system32\\cmd.exe';

process.env.ComSpec = cmdPath;
process.env.COMSPEC = cmdPath;

const { result } = concurrently(
  [
    {
      command: 'npm run dev:backend',
      name: 'backend',
      prefixColor: 'blue',
      env: { ComSpec: cmdPath, COMSPEC: cmdPath },
    },
    {
      command: 'npm run dev:frontend',
      name: 'frontend',
      prefixColor: 'cyan',
      env: { ComSpec: cmdPath, COMSPEC: cmdPath },
    },
  ],
  {
    killOthersOn: ['failure'],
  }
);

result.catch((err) => {
  // Exit cleanly if child was terminated
  process.exit(1);
});
