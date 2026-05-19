#!/usr/bin/env node
// update-check.mjs — wind-skills 升级感知探活脚本 v2(installedAt-反查方案)
// 由 cli.mjs 异步 spawn,读 lock 条目 → 反查"装时刻"的远端 tree SHA → 跟当前远端 tree SHA 对比
// 设计: 完全静默,绝不阻塞主流程,任何异常吞掉
//
// 与 v1(baseline)的区别:
//   - v1: 用 baseline 文件存"上次远端 SHA",远端自比,首次 check 把当下当基准 → "装老版本"漏报
//   - v2: 不用 baseline 文件,反查 lock.updatedAt 时刻的真实 commit,精确对比
// 输出 schema 与 cli.mjs L119 collectUpdateNotices 保持兼容

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_NAME = 'wind-mcp-skill';

const CACHE_DIR = join(homedir(), '.cache', 'wind-aimarket');
const CACHE_FILE = join(CACHE_DIR, 'update-state.json');
const CACHE_SCHEMA_VERSION = 3;  // bump: v2 → v3,旧 cache 自动失效

const TTL_UP_TO_DATE_MS    = 60 * 60 * 1000;        // 60 min
const TTL_AVAILABLE_MS     = 12 * 60 * 60 * 1000;   // 12 h
const TTL_UNKNOWN_MS       = 24 * 60 * 60 * 1000;   // 24 h
const TTL_TRANSIENT_MS     =  5 * 60 * 1000;        //  5 min
const TTL_RATE_LIMIT_MS    = 60 * 60 * 1000;        // 60 min(撞 rate limit 直接退化为长 TTL)

const NETWORK_TIMEOUT_MS = 5_000;
const INSTALLED_AT_TOLERANCE_MS = 60 * 60 * 1000;   // installedAt + 1h 容差,防时钟偏移

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));

// ───── cache ─────

function readCache() {
  if (!existsSync(CACHE_FILE)) return null;
  try {
    const data = JSON.parse(readFileSync(CACHE_FILE, 'utf8'));
    if (data?.schemaVersion !== CACHE_SCHEMA_VERSION) return null;
    return data;
  } catch { return null; }
}

function writeCache(state) {
  try {
    if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
    const prev = readCache();
    const merged = { ...state, schemaVersion: CACHE_SCHEMA_VERSION, lastCheck: new Date().toISOString() };
    if (prev?.snoozedUntil) merged.snoozedUntil = prev.snoozedUntil;
    if (typeof prev?.snoozeLevel === 'number') merged.snoozeLevel = prev.snoozeLevel;
    writeFileSync(CACHE_FILE, JSON.stringify(merged, null, 2));
  } catch {}
}

function isCacheFresh(cache, currentSignature) {
  if (!cache?.lastCheck || !cache?.ttlMs) return false;
  if (cache.lockSignature !== currentSignature) return false;
  return Date.now() - new Date(cache.lastCheck).getTime() < cache.ttlMs;
}

function buildLockSignature(entries) {
  if (!entries || entries.length === 0) return null;
  return entries
    .map(({ entry, lockPath }) => `${lockPath}|${entry.updatedAt || entry.installedAt || ''}`)
    .sort()
    .join('\n');
}

// ───── lock 文件探测(3 路径策略,沿用 v1)─────

function walkUp(startDir) {
  const dirs = [];
  let dir = resolve(startDir);
  while (true) {
    dirs.push(dir);
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return dirs;
}

function findLockFiles() {
  const candidates = new Set();
  const xdg = process.env.XDG_STATE_HOME;
  candidates.add(xdg
    ? join(xdg, 'skills', '.skill-lock.json')
    : join(homedir(), '.agents', '.skill-lock.json'));
  for (const dir of walkUp(SCRIPT_DIR)) {
    candidates.add(join(dir, 'skills-lock.json'));
  }
  for (const dir of walkUp(process.cwd())) {
    candidates.add(join(dir, 'skills-lock.json'));
  }
  return [...candidates].filter(p => existsSync(p));
}

function collectEntries() {
  const found = [];
  for (const lockPath of findLockFiles()) {
    try {
      const lock = JSON.parse(readFileSync(lockPath, 'utf8'));
      const entry = lock?.skills?.[SKILL_NAME];
      if (entry) found.push({ entry, lockPath });
    } catch {}
  }
  return found;
}

// ───── 条目解析 ─────

function parseSourceUrl(sourceUrl) {
  if (typeof sourceUrl !== 'string' || !sourceUrl) return null;
  let host = null;
  if (sourceUrl.includes('github.com')) host = 'github';
  else if (sourceUrl.includes('gitee.com')) host = 'gitee';
  else return null;
  const m = sourceUrl.match(/(?:github\.com|gitee\.com)[:/]([^/]+)\/([^/]+?)(?:\.git)?(?:$|[/?#])/);
  if (!m) return null;
  return { host, owner: m[1], repo: m[2] };
}

function normalizeSkillDir(skillPath) {
  return String(skillPath || '')
    .replace(/\\/g, '/')
    .replace(/\/?SKILL\.md$/i, '')
    .replace(/\/+$/, '');
}

// ───── HTTP ─────

async function fetchJson(url) {
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'wind-mcp-skill-update-check' },
      signal: AbortSignal.timeout(NETWORK_TIMEOUT_MS),
    });
    if (!resp.ok) {
      if (resp.status === 403 || resp.status === 429) {
        const remaining = resp.headers.get('x-ratelimit-remaining');
        if (remaining === '0' || resp.status === 429) return { error: 'rate_limit' };
      }
      return { error: `http_${resp.status}` };
    }
    return { data: await resp.json() };
  } catch (e) {
    return { error: e?.name === 'TimeoutError' ? 'timeout' : 'network' };
  }
}

// ───── 远端 API(GitHub + Gitee 路径统一)─────

function apiBase(host) {
  return host === 'github' ? 'https://api.github.com' : 'https://gitee.com/api/v5';
}

async function fetchTreeBySha({ host, owner, repo }, sha) {
  const r = await fetchJson(`${apiBase(host)}/repos/${owner}/${repo}/git/trees/${encodeURIComponent(sha)}?recursive=1`);
  if (r.error) return { error: r.error };
  if (r.data && Array.isArray(r.data.tree)) return { tree: r.data };
  return { error: 'shape' };
}

async function fetchCurrentTree(parsed, ref) {
  const branches = ref ? [ref] : (parsed.host === 'gitee' ? ['main', 'master'] : ['HEAD', 'main', 'master']);
  let lastError = null;
  for (const branch of branches) {
    const r = await fetchTreeBySha(parsed, branch);
    if (r.tree) return r;
    lastError = r.error;
    if (r.error === 'rate_limit') return r;  // 撞 rate limit 立刻停,别浪费
  }
  return { error: lastError || 'shape' };
}

// 反查"装时刻"前的最新 commit(影响 skillDir 的)
// GitHub & Gitee 都支持 /commits?path=&until=&sha=&per_page=1
async function fetchCommitAtTime({ host, owner, repo }, ref, skillDir, installedAt) {
  const until = new Date(new Date(installedAt).getTime() + INSTALLED_AT_TOLERANCE_MS).toISOString();
  const params = new URLSearchParams({ until, per_page: '1' });
  if (skillDir) params.set('path', skillDir);
  if (ref) params.set('sha', ref);
  const url = `${apiBase(host)}/repos/${owner}/${repo}/commits?${params.toString()}`;
  const r = await fetchJson(url);
  if (r.error) return { error: r.error };
  if (!Array.isArray(r.data) || r.data.length === 0) return { error: 'no_commit_at_time' };
  const sha = r.data[0]?.sha;
  if (typeof sha !== 'string') return { error: 'commit_shape' };
  return { sha };
}

function findSkillSha(tree, skillDir) {
  if (!skillDir) return tree.sha || null;
  return tree.tree.find(t => t.type === 'tree' && t.path === skillDir)?.sha || null;
}

function shortHash(h) {
  return typeof h === 'string' ? h.slice(0, 7) : '';
}

// ───── 主逻辑 ─────

async function main() {
  const cache = readCache();
  const entries = collectEntries();
  const lockSignature = buildLockSignature(entries);
  if (isCacheFresh(cache, lockSignature)) return;

  if (entries.length === 0) {
    writeCache({ status: 'unknown', reason: 'lock_missing', ttlMs: TTL_UNKNOWN_MS, lockSignature });
    return;
  }

  const outdated = [];
  const unknownDetails = [];
  let transientError = null;
  let rateLimited = false;

  for (const { entry, lockPath } of entries) {
    const sourceUrl = entry.sourceUrl;
    if (!sourceUrl) {
      unknownDetails.push({ reason: 'no_source_url', lockPath, source: entry.source });
      continue;
    }

    const parsed = parseSourceUrl(sourceUrl);
    if (!parsed) {
      unknownDetails.push({ reason: 'unsupported_host', lockPath, sourceUrl });
      continue;
    }

    // 优先 updatedAt(用户最近一次升级时间),退化到 installedAt
    const installedAt = entry.updatedAt || entry.installedAt;
    if (!installedAt) {
      unknownDetails.push({ reason: 'no_installed_at', lockPath });
      continue;
    }

    const skillDir = normalizeSkillDir(entry.skillPath);
    const ref = entry.ref || null;

    // A: 当前远端 tree
    const currentTreeResult = await fetchCurrentTree(parsed, ref);
    if (currentTreeResult.error) {
      if (currentTreeResult.error === 'rate_limit') { rateLimited = true; break; }
      transientError = { reason: currentTreeResult.error, sourceUrl, host: parsed.host };
      continue;
    }
    const currentSha = findSkillSha(currentTreeResult.tree, skillDir);
    if (!currentSha) {
      unknownDetails.push({ reason: 'path_missing', lockPath, sourceUrl, skillPath: entry.skillPath });
      continue;
    }

    // B: 反查装时刻的 commit → tree
    const installCommit = await fetchCommitAtTime(parsed, ref, skillDir, installedAt);
    if (installCommit.error) {
      if (installCommit.error === 'rate_limit') { rateLimited = true; break; }
      // 反查失败(no_commit_at_time 等)→ 保守报 unknown,不误报
      unknownDetails.push({ reason: `commit_lookup_${installCommit.error}`, lockPath, sourceUrl });
      continue;
    }

    const installedTreeResult = await fetchTreeBySha(parsed, installCommit.sha);
    if (installedTreeResult.error) {
      if (installedTreeResult.error === 'rate_limit') { rateLimited = true; break; }
      transientError = { reason: installedTreeResult.error, sourceUrl, host: parsed.host };
      continue;
    }
    const installedSha = findSkillSha(installedTreeResult.tree, skillDir);
    if (!installedSha) {
      unknownDetails.push({ reason: 'path_missing_at_install', lockPath, sourceUrl });
      continue;
    }

    if (currentSha === installedSha) continue;  // up_to_date for this entry

    outdated.push({
      name: SKILL_NAME,
      current: shortHash(installedSha),
      latest: shortHash(currentSha),
      sourceUrl,
      host: parsed.host,
    });
  }

  // ───── 聚合写 cache ─────

  if (rateLimited) {
    writeCache({
      status: 'transient_error',
      reason: 'rate_limit',
      ttlMs: TTL_RATE_LIMIT_MS,
      lockSignature,
    });
    return;
  }

  if (outdated.length > 0) {
    writeCache({
      status: 'update_available',
      outdated,
      ttlMs: TTL_AVAILABLE_MS,
      lockSignature,
    });
    return;
  }

  // 任一条 entry 完整对比成功(没进 unknown 也没进 transient)→ up_to_date
  const totalHandled = unknownDetails.length + (transientError ? 1 : 0);
  if (totalHandled < entries.length) {
    writeCache({ status: 'up_to_date', ttlMs: TTL_UP_TO_DATE_MS, lockSignature });
    return;
  }

  if (transientError) {
    writeCache({
      status: 'transient_error',
      reason: transientError.reason,
      sourceUrl: transientError.sourceUrl,
      ttlMs: TTL_TRANSIENT_MS,
      lockSignature,
    });
    return;
  }

  writeCache({
    status: 'unknown',
    reason: unknownDetails[0].reason,
    details: unknownDetails,
    ttlMs: TTL_UNKNOWN_MS,
    lockSignature,
  });
}

main().catch(() => {});
