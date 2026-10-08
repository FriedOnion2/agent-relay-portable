// Opt-in test against an installed DSH release; only use a synthetic fixture home.
// node tests/dsh_native_smoke.mjs <dsh-node_modules> <fixture-home> <session-id>
import assert from 'node:assert/strict';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const [modules, home, id] = process.argv.slice(2);
if (!modules || !home || !id) throw new Error('Expected DSH node_modules, synthetic fixture home and session ID');
const load = name => import(pathToFileURL(join(modules, '@deepseek-ai', name, 'lib/index.js')).href);
const {Context} = await load('cordis');
const {default:Store} = await load('dsh-session');
const {default:Persistence} = await load('dsh-session-persistence-jsonl');
const ctx = new Context();
await ctx.plugin(Store);
await ctx.plugin(Persistence, {root:join(home, 'sessions'), compression:'zstd'});
if (typeof ctx.sessionPersistence.prepare !== 'function') {
  // DSH >= 0.2 moved session restore to ctx.sessions.prepare() and returns data folds instead of a Session,
  // so only check that DSH lists, migrates (v0 -> v4) and restores the imported session.
  try {
    assert((await ctx.sessionPersistence.list()).some(entry => (entry.header ?? entry).id === id));
    const stat = await ctx.sessionPersistence.stat(id);
    assert.equal(stat.header.version, 4, 'DSH should migrate the imported v0 log to v4');
    const prepared = await ctx.sessions.prepare(id);
    assert.equal(prepared.header.id, id);
    console.log('PASS: native DSH (>=0.2) list, v0->v4 migration and restore');
  } finally {
    await ctx.fiber.dispose();
  }
  process.exit(0);
}
try {
  assert((await ctx.sessionPersistence.list()).some(entry => (entry.header ?? entry).id === id)); // 0.2 wraps the header in {header, revision}
  const prepared = await ctx.sessionPersistence.prepare(id);
  const session = prepared.session;
  const messages = session.deriveMessages();
  assert.equal(messages[0].content[0].text, '请读取文件');
  assert.equal(messages.at(-1).content[0].text, '下一步');
  assert.equal(messages.flatMap(message => message.content).filter(block => block.type === 'tool-call').length, 1);
  const results = messages.flatMap(message => message.content).filter(block => block.type === 'tool-result');
  assert.equal(results.length, 1);
  assert.equal(results[0].content[0].text, '你好\n第二行');
  assert.equal(results[0].isError, true);
  ctx.sessions.enter(session);
  ctx.sessions.announce(session);
  session.append('user/message', {id:'continue-user', role:'user', source:{kind:'user'},
    content:[{type:'text', text:'继续导入的会话'}]}, {surfaceOp:'append'});
  prepared[Symbol.dispose]();
} finally {
  // The real backend drains its writes on disposal, just as DSH does at exit.
  await ctx.fiber.dispose();
}
const reopened = new Context();
await reopened.plugin(Store);
await reopened.plugin(Persistence, {root:join(home, 'sessions'), compression:'zstd'});
try {
  const stored = await reopened.sessionPersistence.inspect(id);
  assert.equal(stored.events.at(-1).data.content[0].text, '继续导入的会话');
  console.log('PASS: native DSH list, restore, message projection, continuation write and reload');
} finally {
  await reopened.fiber.dispose();
}
