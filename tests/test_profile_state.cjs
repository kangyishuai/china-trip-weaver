const assert = require('node:assert/strict');
const { transition, timeVisibility, focusTarget, capturePrintState } = require('../plugins/china-trip-weaver/assets/profile.js');

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
assert.equal(focusTarget('overview', false), 'day');
assert.equal(focusTarget('adjacent', false), 'trigger');
assert.equal(focusTarget('adjacent', true), 'day');
assert.equal(focusTarget('preview', false), 'undo');
assert.equal(focusTarget('undo', false), 'try');
const saved = capturePrintState(null, { day: 2, preview: true }, [false, true, false]);
assert.deepEqual(saved, { state: { day: 2, preview: true }, detailsOpen: [false, true, false] });
assert.equal(capturePrintState(saved, { day: 0, preview: false }, [true, true, true]), saved);
assert.deepEqual(saved.state, { day: 2, preview: true });
console.log('8 state, 6 clock, 5 focus, and 3 print snapshot checks passed');
