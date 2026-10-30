const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawnSync } = require('child_process');
const { resolveOllamaBaseUrl, loadDotEnv, probeTags } = require('./ensure-ollama');

function testPort(port, signaturePath = '/', signatureKeyword = null) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}${signaturePath}`, { timeout: 2000 }, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        if (signatureKeyword && data.includes(signatureKeyword)) {
          resolve({ status: 'ours', isOurs: true, detail: `In use by Palimpsest (${port})` });
        } else {
          resolve({ status: 'in_use', isOurs: false, detail: `In use by unknown process (${port})` });
        }
      });
    });

    req.on('error', (err) => {
      if (err.code === 'ECONNREFUSED') {
        resolve({ status: 'free', isOurs: false, detail: 'Free' });
      } else {
        resolve({ status: 'free', isOurs: false, detail: `Available (${err.code})` });
      }
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({ status: 'in_use', isOurs: false, detail: `Occupied (timeout on ${port})` });
    });
  });
}

async function runDoctor() {
  console.log('======================================================================');
  console.log('  PALIMPSEST System Doctor Checklist');
  console.log('======================================================================');

  let criticalFailure = false;

  // 1. Check Node
  const nodeVersion = process.version;
  const major = parseInt(nodeVersion.replace(/^v/, '').split('.')[0], 10);
  if (major >= 18) {
    console.log(`[PASS] Node.js Runtime:           ${nodeVersion} (>= 18.0.0 required)`);
  } else {
    console.log(`[FAIL] Node.js Runtime:           ${nodeVersion} (Node 18+ required)`);
    criticalFailure = true;
  }

  // 2. Check Python venv
  const isWin = process.platform === 'win32';
  const venvPython = isWin
    ? path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', '.venv', 'bin', 'python');

  if (fs.existsSync(venvPython)) {
    try {
      const pyVer = spawnSync(venvPython, ['--version'], { encoding: 'utf8' });
      const verText = (pyVer.stdout || pyVer.stderr || '').trim();
      console.log(`[PASS] Python Virtualenv:         ${path.relative(path.join(__dirname, '..'), venvPython)} (${verText})`);
    } catch (e) {
      console.log(`[FAIL] Python Virtualenv:         Found at ${venvPython} but execution failed: ${e.message}`);
      criticalFailure = true;
    }
  } else {
    console.log(`[FAIL] Python Virtualenv:         Not found at ${venvPython}. Run: python -m venv .venv`);
    criticalFailure = true;
  }

  // 3. Check GGUF file
  const ggufPath = path.join(__dirname, '..', 'models', 'palimpsest-q4_k_m.gguf');
  if (fs.existsSync(ggufPath)) {
    const stats = fs.statSync(ggufPath);
    const sizeMb = (stats.size / (1024 * 1024)).toFixed(1);
    console.log(`[PASS] GGUF Model File:           models/palimpsest-q4_k_m.gguf (${sizeMb} MB)`);
  } else {
    console.log(`[WARN] GGUF Model File:           Missing at models/palimpsest-q4_k_m.gguf`);
  }

  // 4. Check Ports 5173 and 8000
  const port8000 = await testPort(8000, '/api/health', 'z3_logic');
  const port5173 = await testPort(5173, '/', 'PALIMPSEST');

  if (port8000.status === 'free' || port8000.isOurs) {
    console.log(`[PASS] Port 8000 (Backend API):   ${port8000.detail}`);
  } else {
    console.log(`[FAIL] Port 8000 (Backend API):   ${port8000.detail}`);
    criticalFailure = true;
  }

  if (port5173.status === 'free' || port5173.isOurs) {
    console.log(`[PASS] Port 5173 (Frontend Vite): ${port5173.detail}`);
  } else {
    console.log(`[FAIL] Port 5173 (Frontend Vite): ${port5173.detail}`);
    criticalFailure = true;
  }

  // 5. Check Ollama reachable and palimpsest model present
  const dotEnv = loadDotEnv();
  const baseUrl = resolveOllamaBaseUrl(dotEnv);
  const probe = await probeTags(baseUrl, globalThis.fetch, 1000);

  if (probe.reachable) {
    console.log(`[PASS] Ollama Reachable:          Active at ${baseUrl}`);
    const hasPalimpsest = probe.models.some((m) => m === 'palimpsest' || m.startsWith('palimpsest:'));
    if (hasPalimpsest) {
      console.log(`[PASS] Model "palimpsest":        Present in Ollama catalog`);
    } else {
      console.log(`[WARN] Model "palimpsest":        Missing from catalog. Run: npm run model:setup`);
    }
  } else {
    console.log(`[WARN] Ollama Reachable:          Not running at ${baseUrl}`);
    console.log(`[WARN] Model "palimpsest":        Catalog unqueriable (Ollama offline)`);
  }

  // 6. Print Key .env Values
  console.log('----------------------------------------------------------------------');
  console.log('Key .env Configuration Values:');
  const keyEnvVars = [
    'PALIMPSEST_BACKEND',
    'OLLAMA_MODEL',
    'OLLAMA_BASE_URL',
    'PROMPT_PROFILE',
    'WITNESS_POLICY',
    'SHIFT_SEMANTICS',
    'RSHIFT_SEMANTICS',
    'Z3_TIMEOUT_MS',
    'BACKEND_FALLBACK',
  ];
  for (const k of keyEnvVars) {
    const val = dotEnv[k] || process.env[k] || '(default / not set)';
    console.log(`  ${(k + ':').padEnd(23)} ${val}`);
  }
  console.log('======================================================================');

  if (criticalFailure) {
    console.error('\n[PALIMPSEST DOCTOR ERROR] Critical checks failed. Resolve issues above before starting.\n');
    process.exit(1);
  } else {
    console.log('\n[PALIMPSEST DOCTOR] All critical checks passed.\n');
    process.exit(0);
  }
}

if (require.main === module) {
  runDoctor().catch((err) => {
    console.error('[PALIMPSEST DOCTOR FATAL]', err);
    process.exit(1);
  });
}

module.exports = {
  testPort,
  runDoctor,
};
