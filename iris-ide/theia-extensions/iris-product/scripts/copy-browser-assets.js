/** tsc는 .css를 lib/로 복사하지 않음 — webpack 번들 전에 browser 자산 동기화 */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const srcDir = path.join(root, 'src', 'browser');
const outDir = path.join(root, 'lib', 'browser');

fs.mkdirSync(outDir, { recursive: true });

for (const name of fs.readdirSync(srcDir)) {
  if (!name.endsWith('.css')) {
    continue;
  }
  fs.copyFileSync(path.join(srcDir, name), path.join(outDir, name));
}
