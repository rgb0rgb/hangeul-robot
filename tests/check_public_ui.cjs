// Run with node tests/check_public_ui.cjs. No browser or robot connection.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('console/web/simple.js', 'utf8');
const ctx = {lang: 'ko', formatUiValue: (_, v) => String(v),
  fetch() { throw new Error('Excluded tracking must not request the backend'); },
  setInterval() { throw new Error('Excluded tracking must not create timers'); }};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function motionFailureReason'), source.indexOf('function jogJoint(')), ctx);
assert.strictEqual(ctx.motionFailureMessage({reason:'연결 실패'},11,undefined), '이동 확인 실패: 연결 실패');
assert(!ctx.motionFailureMessage({reason:'연결 실패'},11,1500).includes('목표 미도달'));
assert(ctx.motionFailureMessage({present:{11:1400},error:'도달 실패'},11,1500).includes('목표 1500, 실제 1400'));
for (const name of ['refreshColorTrackingStatus','startColorTrackingStatusPolling','_trackPoll','refreshTargetTracking']) {
  const start = source.indexOf('function '+name+'() {');
  const end = source.indexOf('\n}',start)+2;
  vm.runInContext(source.slice(start,end),ctx);
  ctx[name]();
}
console.log('Public UI error and disabled tracking checks passed');
