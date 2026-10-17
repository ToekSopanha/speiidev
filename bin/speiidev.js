#!/usr/bin/env node

const { spawnSync } = require('child_process');
const os = require('os');

const isWin = os.platform() === 'win32';
const pythonCmd = isWin ? 'python' : 'python3';

// 1. Check Python
const checkPython = spawnSync(pythonCmd, ['--version'], { stdio: 'ignore' });
if (checkPython.error || checkPython.status !== 0) {
  console.error('❌ Error: Python 3 is required to run speiidev, but it was not found.');
  console.error('💡 Windows Tip: Install Python via: winget install Python.Python.3.11');
  process.exit(1);
}

// 2. Install/Update core Python package from PyPI
spawnSync(pythonCmd, ['-m', 'pip', 'install', '--user', '--upgrade', 'autodev_orchestrator'], { stdio: 'inherit' });

// 3. Forward arguments and run
const args = process.argv.slice(2);
const result = spawnSync(pythonCmd, ['-m', 'autodev.cli', ...args], { stdio: 'inherit' });
process.exit(result.status);