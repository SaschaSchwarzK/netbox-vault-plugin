import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { composeProjectName } from './config.js';

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../..');
const workdir = path.join(repoRoot, '.e2e-artifacts', 'netbox-docker');

function composeArgs(extraArgs: string[]) {
  return [
    'compose',
    '-p',
    composeProjectName,
    '-f',
    path.join(workdir, 'docker-compose.yml'),
    '-f',
    path.join(workdir, 'docker-compose.override.yml'),
    ...extraArgs,
  ];
}

export function dockerCompose(extraArgs: string[]) {
  return execFileSync('docker', composeArgs(extraArgs), {
    cwd: repoRoot,
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
}

export function netboxShell(code: string) {
  return dockerCompose([
    'exec',
    '-T',
    'netbox',
    '/opt/netbox/venv/bin/python',
    '/opt/netbox/netbox/manage.py',
    'shell',
    '-c',
    code,
  ]);
}

export function netboxManage(...args: string[]) {
  return dockerCompose([
    'exec',
    '-T',
    'netbox',
    '/opt/netbox/venv/bin/python',
    '/opt/netbox/netbox/manage.py',
    ...args,
  ]);
}

export function netboxPython(code: string) {
  return dockerCompose([
    'exec',
    '-T',
    'netbox',
    '/opt/netbox/venv/bin/python',
    '-c',
    code,
  ]);
}

export function installNetboxScript(moduleName: string, content: string) {
  return netboxPython(
    `from pathlib import Path; path = Path('/opt/netbox/netbox/scripts') / ${JSON.stringify(moduleName + '.py')}; path.write_text(${JSON.stringify(content)}, encoding='utf-8'); print(path)`
  );
}

export function removeNetboxScript(moduleName: string) {
  return netboxPython(
    `from pathlib import Path; path = Path('/opt/netbox/netbox/scripts') / ${JSON.stringify(moduleName + '.py')}; path.unlink(missing_ok=True); print('ok')`
  );
}

export function runNetboxScript(scriptName: string, user = 'admin', data?: Record<string, unknown>) {
  const args = ['runscript', '--commit', '--user', user];
  if (data) {
    args.push('--data', JSON.stringify(data));
  }
  args.push(scriptName);
  const stdout = netboxManage(...args);
  const jobData = netboxShell(`import json
from core.models import Job
job = Job.objects.order_by('-created').first()
print(json.dumps(job.data))`);
  return {
    stdout,
    jobData: JSON.parse(jobData.trim().split('\n').filter(Boolean).at(-1) ?? '{}'),
  };
}
