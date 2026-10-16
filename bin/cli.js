#!/usr/bin/env node

const { spawnSync } = require('child_process');
const os = require('os');

const isWin = os.platform() === 'win32';
const pythonCmd = isWin ? 'python' : 'python3';

// 1. Verify Python exists on their system
const checkPython = spawnSync(pythonCmd, ['--version'], { stdio: 'ignore' });
if (checkPython.error || checkPython.status !== 0) {
  console.error('❌ Error: Python 3 is required to run speiidev, but it was not found.');
  console.error('💡 Windows Tip: Install Python from the Microsoft Store or via: winget install Python.Python.3.11');
  process.exit(1);
}

const args = process.argv.slice(2);

// 2. Automatically install your Python core code directly from your GitHub repo using pip
let runArgs = ['install', '--user', 'git+https://github.com/speiidev/TSmrloverman.git'];
spawnSync(pythonCmd, ['-m', 'pip', ...runArgs], { stdio: 'inherit' });

// 3. Launch the core Python application passing along any terminal arguments
const result = spawnSync(pythonCmd, ['-m', 'autodev.cli', ...args], { stdio: 'inherit' });
process.exit(result.status);