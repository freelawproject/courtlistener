const path = require('path');
const webpack = require('webpack');
const CompressionPlugin = require('compression-webpack-plugin');

const isDevelopment = process.env.NODE_ENV !== 'production';

module.exports = {
  context: __dirname,
  mode: isDevelopment ? 'development' : 'production',

  entry: [
    './assets/react/index', // entry point of our app. assets/js/index.js should require other js modules and dependencies it needs
  ],
  output: {
    path: path.resolve(__dirname, 'assets/static-global/js/react'), // Should be in STATICFILES_DIRS
    publicPath: '/static/', // Should match Django STATIC_URL
    filename: '[name].js', // No filename hashing, Django takes care of this
    chunkFilename: '[id]-[chunkhash].js', // DO have Webpack hash chunk filename, see below
  },
  optimization: {
    removeAvailableModules: true,
    splitChunks: {
      chunks: 'all',
      name: 'vendor',
      filename: '[name].js',
    },
  },
  plugins: [].filter(Boolean),
  module: {
    rules: [
      {
        test: /\.(jsx|ts|tsx)?$/,
        include: path.join(__dirname, 'assets', 'react'),
        loader: 'babel-loader',
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
    ],
  },
  resolve: {
    modules: ['node_modules'],
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
  },
  devServer: {
    devMiddleware: {
      writeToDisk: true,
    },
    compress: true,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
      'Access-Control-Allow-Headers': 'X-Requested-With, content-type, Authorization',
      'Accept-Encoding': 'gzip',
    },
    port: 3000,
  },
  devtool: 'cheap-module-source-map',
};
