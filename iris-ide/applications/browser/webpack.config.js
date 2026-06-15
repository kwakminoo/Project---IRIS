/**
 * Iris IDE webpack — frontend(gen) + 커스텀 backend(node-pty 없음).
 */
// @ts-check
const configs = require('./gen-webpack.config.js');
const nodeConfig = require('./iris-webpack.node.config.js');

module.exports = [...configs, nodeConfig.config];
