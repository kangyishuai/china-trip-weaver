'use strict';

const os = require('node:os');
const isolatedHome = process.env.CTW_RAIL_HOME;

if (!isolatedHome || !isolatedHome.startsWith('/')) {
  throw new Error('CTW_RAIL_HOME must be an absolute isolated path');
}

Object.defineProperty(os, 'homedir', {
  configurable: true,
  value: () => isolatedHome,
  writable: false,
});
