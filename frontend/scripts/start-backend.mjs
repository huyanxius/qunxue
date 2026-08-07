import { execSync, spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '../..');
const backendDir = path.join(rootDir, 'backend');
const dbPath = path.join(backendDir, 'tmp', 'e2e_test.db');

// 1. 准备隔离数据库
fs.mkdirSync(path.dirname(dbPath), { recursive: true });
if (fs.existsSync(dbPath)) {
  fs.unlinkSync(dbPath);
}

const varDbPath = path.join(backendDir, 'var', 'qunxue.db');
if (!fs.existsSync(varDbPath)) {
  console.log('[E2E] Creating default database via Alembic...');
  execSync('uv run alembic upgrade head', { cwd: backendDir, stdio: 'inherit' });
}

fs.copyFileSync(varDbPath, dbPath);
const dbUrl = `sqlite:///${dbPath.replace(/\\/g, '/')}`;
console.log(`[E2E] Using isolated database: ${dbUrl}`);

// 2. 启动后端
const backend = spawn('uv', ['run', 'uvicorn', 'qunxue_api.main:app', '--port', '8000', '--host', '127.0.0.1'], {
  cwd: backendDir,
  env: { ...process.env, QUNXUE_DATABASE_URL: dbUrl },
  stdio: 'inherit',
  shell: true,
});

// 3. 优雅退出
['SIGTERM', 'SIGINT'].forEach((sig) => {
  process.on(sig, () => {
    console.log(`[E2E] ${sig} received, stopping backend...`);
    backend.kill();
  });
});