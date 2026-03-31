#!/usr/bin/env node
/**
 * Session start hook for Goldsmith ERP.
 * Checks git status and shows last session context.
 */
const { execSync } = require('child_process');

try {
  const branch = execSync('git branch --show-current', { encoding: 'utf8' }).trim();
  console.log(`Branch: ${branch}`);

  const status = execSync('git status --porcelain', { encoding: 'utf8' });
  const changes = status.split('\n').filter(l => l.trim()).length;
  if (changes > 0) {
    console.log(`Uncommitted changes: ${changes} files`);
  }

  const lastCommit = execSync('git log -1 --format="%h %s" 2>/dev/null', { encoding: 'utf8' }).trim();
  console.log(`Last commit: ${lastCommit}`);
} catch (e) {
  // Silent fail — don't block session start
}
