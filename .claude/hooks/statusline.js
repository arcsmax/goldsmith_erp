#!/usr/bin/env node
/**
 * Status line display for Goldsmith ERP.
 */
const { execSync } = require('child_process');

try {
  const branch = execSync('git branch --show-current', { encoding: 'utf8' }).trim();
  const status = execSync('git status --porcelain', { encoding: 'utf8' });
  const dirty = status.trim() ? '*' : '';
  process.stdout.write(`goldsmith-erp [${branch}${dirty}]`);
} catch (e) {
  process.stdout.write('goldsmith-erp');
}
