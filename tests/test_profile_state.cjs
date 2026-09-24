const assert = require('node:assert/strict');
const { transition, timeVisibility } = require('../plugins/china-trip-weaver/assets/profile.js');

const model = { days: [
  { scenario: { available: true } },
  { scenario: { available: false } },
  { scenario: { available: true } },
] };
const baseline = { day: 0, preview: false };
assert.deepEqual(transition(baseline, { type: 'try' }, model), { day: 0, preview: true });
assert.deepEqual(transition({ day: 0, preview: true }, { type: 'undo' }, model), baseline);
assert.deepEqual(transition({ day: 0, preview: true }, { type: 'select', index: 2 }, model), { day: 2, preview: false });
assert.deepEqual(transition({ day: 0, preview: true }, { type: 'select', index: 1 }, model), { day: 1, preview: false });
assert.deepEqual(transition({ day: 1, preview: false }, { type: 'try' }, model), { day: 1, preview: false });
assert.deepEqual(transition(baseline, { type: 'select', index: -1 }, model), baseline);
assert.deepEqual(transition(baseline, { type: 'select', index: 3 }, model), baseline);
assert.deepEqual(transition(baseline, { type: 'unknown' }, model), baseline);
assert.deepEqual(timeVisibility(true, false), { originalHidden: false, shiftedHidden: true });
assert.deepEqual(timeVisibility(true, true), { originalHidden: true, shiftedHidden: false });
assert.deepEqual(timeVisibility(false, false), { originalHidden: false, shiftedHidden: true });
assert.deepEqual(timeVisibility(false, true), { originalHidden: false, shiftedHidden: true });
assert.deepEqual(timeVisibility(true, transition({ day: 0, preview: true }, { type: 'undo' }, model).preview),
  { originalHidden: false, shiftedHidden: true });
assert.deepEqual(timeVisibility(true, transition({ day: 0, preview: true }, { type: 'select', index: 1 }, model).preview),
  { originalHidden: false, shiftedHidden: true });
console.log('8 profile state transitions and 6 clock visibility checks passed');
