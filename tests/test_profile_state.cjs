const assert = require('node:assert/strict');
const { transition } = require('../plugins/china-trip-weaver/assets/profile.js');

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
console.log('8 profile state transitions passed');
