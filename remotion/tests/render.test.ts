import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {expect, test, vi} from 'vitest';

vi.mock('node:child_process', () => ({spawnSync: vi.fn(() => ({status: 0}))}));

test('launches through Node with file props, preserving spaces and large scripts', async () => {
  const original = process.argv;
  const directory = mkdtempSync(join(tmpdir(), 'avf-render-'));
  const output = join(directory, 'output with spaces.mp4');
  const fixture = join(directory, 'large edit.json');
  const edit = JSON.parse(readFileSync(resolve('../fixtures/synthetic-edit.json'), 'utf8'));
  edit.scenes[0].caption = 'A'.repeat(80000);
  writeFileSync(fixture, JSON.stringify(edit));
  const browser = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  process.argv = [process.execPath, 'render.ts', '--props', fixture, output, '--browser-executable', browser];
  try {
    await import('../render');
  } finally {
    process.argv = original;
  }
  const [program, args, options] = vi.mocked(spawnSync).mock.calls[0];
  expect(program).toBe(process.execPath);
  expect(args?.[0]).toMatch(/remotion-cli\.js$/);
  expect(args).toContain(output);
  expect(args?.[args.indexOf('--props') + 1] === fixture).toBe(true);
  expect(args?.join(' ').length).toBeLessThan(32000);
  expect(args?.at(-1)).toBe(browser);
  expect(options).toMatchObject({windowsHide: true});
});
