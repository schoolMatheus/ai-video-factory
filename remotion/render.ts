import {mkdirSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {parseEditDocument} from './src/schema.js';

const usage = 'Usage: npm run render -- --props <edit.json> <output.mp4> --browser-executable <local-browser>';
const args = process.argv.slice(2);

if (args.length !== 5 || args[0] !== '--props' || args[3] !== '--browser-executable') {
  throw new Error(usage);
}

const [ , propsPath, outputPath, , browserExecutable] = args;
const propsFile = resolve(propsPath);
parseEditDocument(JSON.parse(readFileSync(propsFile, 'utf8')));
const output = resolve(outputPath);
mkdirSync(dirname(output), {recursive: true});

const require = createRequire(import.meta.url);
const cli = resolve(dirname(require.resolve('@remotion/cli/package.json')), 'remotion-cli.js');
const render = spawnSync(
  process.execPath,
  [
    cli,
    'render', 'src/index.ts', 'SyntheticVideo', output, '--muted', '--props', propsFile,
    '--browser-executable', browserExecutable,
  ],
  {stdio: 'inherit', windowsHide: true},
);

if (render.error) {
  throw render.error;
}
if (render.status !== 0) {
  process.exit(render.status ?? 1);
}
