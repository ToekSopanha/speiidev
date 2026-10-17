#!/usr/bin/env node

const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');

const isWin = os.platform() === 'win32';
const pythonCmd = isWin ? 'python' : 'python3';

// 1. Check Python installation
const checkPython = spawnSync(pythonCmd, ['--version'], { stdio: 'ignore' });
if (checkPython.error || checkPython.status !== 0) {
  console.error('❌ Error: Python 3 is required to run speiidev, but it was not found.');
  console.error('💡 Please install Python 3: https://www.python.org/downloads/');
  process.exit(1);
}

// 2. Ensure core dependencies (rich, prompt_toolkit) are available
const checkDeps = spawnSync(pythonCmd, ['-c', 'import rich, prompt_toolkit'], { stdio: 'ignore' });
if (checkDeps.status !== 0) {
  console.log('📦 Installing required dependencies (rich, prompt_toolkit)...');
  const installResult = spawnSync(pythonCmd, ['-m', 'pip', 'install', 'rich>=13.0.0', 'prompt_toolkit>=3.0.0'], { stdio: 'inherit' });
  if (installResult.status !== 0) {
    // Retry with --break-system-packages / --user for modern PEP 668 managed environments (Homebrew, Ubuntu 24+)
    spawnSync(pythonCmd, ['-m', 'pip', 'install', '--user', '--break-system-packages', 'rich>=13.0.0', 'prompt_toolkit>=3.0.0'], { stdio: 'inherit' });
  }
}

// 3. Resolve bundled Python source code from the npm package
const srcDir = path.resolve(__dirname, '..', 'src');
const args = process.argv.slice(2);
const env = {
  ...process.env,
  SPEIIDEV_INSTALLER: 'npm',
  PYTHONPATH: srcDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ''),
};

// 4. Launch the exact bundled code
const result = spawnSync(pythonCmd, ['-m', 'autodev.cli', ...args], { stdio: 'inherit', env });
process.exit(result.status !== null ? result.status : 1);