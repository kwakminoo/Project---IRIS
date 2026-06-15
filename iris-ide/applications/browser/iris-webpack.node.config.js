/**
 * Iris IDE backend webpack — node-pty 비활성 (Windows Node 22 네이티브 빌드 회피).
 */
// @ts-check
const path = require('path');
const yargs = require('yargs');
const webpack = require('webpack');
const TerserPlugin = require('terser-webpack-plugin');
const NativeWebpackPlugin = require('@theia/native-webpack-plugin');

const { mode } = yargs.option('mode', {
    description: 'Mode to use',
    choices: ['development', 'production'],
    default: 'production',
}).argv;

const production = mode === 'production';

/** @type {import('webpack').EntryObject} */
const commonJsLibraries = {};
for (const [entryPointName, entryPointPath] of Object.entries({
    'parcel-watcher': '@theia/filesystem/lib/node/parcel-watcher',
})) {
    commonJsLibraries[entryPointName] = {
        import: require.resolve(entryPointPath),
        library: { type: 'commonjs2' },
    };
}

const ignoredResources = new Set();
if (process.platform !== 'win32') {
    ignoredResources.add('@vscode/windows-ca-certs');
    ignoredResources.add('@vscode/windows-ca-certs/build/Release/crypt32.node');
}

const nativePlugin = new NativeWebpackPlugin({
    out: 'native',
    trash: true,
    ripgrep: true,
    pty: false,
    nativeBindings: {
        drivelist: 'drivelist/build/Release/drivelist.node',
    },
});

/** @type {import('webpack').Configuration} */
const config = {
    mode,
    devtool: mode === 'development' ? 'source-map' : false,
    target: 'node',
    node: { global: false, __filename: false, __dirname: false },
    output: {
        filename: '[name].js',
        path: path.resolve(__dirname, 'lib', 'backend'),
        devtoolModuleFilenameTemplate: 'webpack:///[absolute-resource-path]?[loaders]',
    },
    entry: {
        main: require.resolve('./src-gen/backend/main'),
        'ipc-bootstrap': require.resolve('@theia/core/lib/node/messaging/ipc-bootstrap'),
        ...commonJsLibraries,
    },
    module: {
        rules: [
            {
                test: /\.node$/,
                loader: 'node-loader',
                options: { name: 'native/[name].[ext]' },
            },
            { test: /\.js$/, enforce: 'pre', loader: 'source-map-loader' },
            {
                test: /node_modules[\\/](jsonc-parser)/,
                loader: 'umd-compat-loader',
            },
        ],
    },
    plugins: [
        nativePlugin,
        new webpack.IgnorePlugin({
            checkResource: (resource) => ignoredResources.has(resource),
        }),
    ],
    optimization: {
        splitChunks: { chunks: 'all' },
        minimize: production,
        minimizer: [new TerserPlugin({ exclude: /^(lib|builtins)\// })],
    },
    ignoreWarnings: [
        /Failed to parse source map/,
        /require function is used in a way in which dependencies cannot be statically extracted/,
        { module: /yargs/ },
        { module: /node-pty/ },
        { module: /require-main-filename/ },
        { module: /ws/ },
        { module: /express/ },
        { module: /cross-spawn/ },
        { module: /@parcel\/watcher/ },
    ],
};

module.exports = { config, nativePlugin, ignoredResources };
