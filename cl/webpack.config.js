const path = require('path');
const webpack = require('webpack');
const TerserPlugin = require("terser-webpack-plugin");

module.exports = {
  context: __dirname,
  mode: 'none',

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
    minimizer: [new TerserPlugin({
        extractComments: false,
        terserOptions: {
          compress: true,
        },
      })],
  },
  devtool: 'inline-source-map',
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
};
