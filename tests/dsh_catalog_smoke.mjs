// Optional independent compatibility check with the official published catalog.
// JSON record array on stdin; catalog node_modules path is the sole argument.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const modules = process.argv[2];
if (!modules) throw new Error('Expected official catalog node_modules path');
const {createSessionFormatCatalogWithChildren} = await import(pathToFileURL(
  join(modules, '@deepseek-ai/dsh-session-format-catalog/lib/index.js')).href);
const records = JSON.parse(readFileSync(0, 'utf8'));
const restore = createSessionFormatCatalogWithChildren([]).createRestore(records[0], {
  recovery:'strict', validation:'current',
});
for (const record of records.slice(1)) restore.decodeRow(record);
const result = restore.finish();
assert.equal(result.header.version, 4);
const tools = result.events.filter(event => event.type === 'tool/result');
assert.equal(tools.length, 1);
assert.equal(tools[0].data.message.role, 'tool');
assert.equal(tools[0].data.message.content[0].text, '你好\n第二行');
console.log('PASS: official catalog strictly migrates the imported v0 history to v4');
