const path = require('path');
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const ReactRefreshWebpackPlugin = require('@pmmmwh/react-refresh-webpack-plugin');

const isDevelopment = process.env.NODE_ENV !== 'production';

const baseOutput = {
  path: path.resolve('./assets/bundles/'),
  filename: '[name]-[hash].js',
};

module.exports = {
  context: __dirname,
  mode: isDevelopment ? 'development' : 'production',

  entry: [
    './assets/react/index', // entry point of our app. assets/js/index.js should require other js modules and dependencies it needs
  ],
  output: isDevelopment
    ? // Tell django to use this URL to load packages and not use STATIC_URL + bundle_name
      { ...baseOutput, publicPath: 'http://localhost:3000/assets/bundles/' }
    : { ...baseOutput },

  optimization: {
    removeAvailableModules: true,
    splitChunks: {
      chunks: 'all',
      name: 'vendor',
    },
  },
  plugins: [
    isDevelopment && new ReactRefreshWebpackPlugin(),
    new BundleTracker({ filename: './webpack-stats.json' }),
  ].filter(Boolean),

  module: {
    rules: [
      {
        test: /\.(jsx|ts|tsx)?$/,
        include: path.join(__dirname, 'assets', 'react'),
        loader: 'babel-loader',
      },
    ],
  },

  resolve: {
    modules: ['node_modules'],
    extensions: ['.js', '.jsx', '.ts', '.tsx'],
  },
  devServer: {
    compress: true,
    port: 3000,
  },
};
