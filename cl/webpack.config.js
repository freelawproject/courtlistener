const path = require("path");
const webpack = require("webpack");
const BundleTracker = require("webpack-bundle-tracker");
const ReactRefreshWebpackPlugin = require('@pmmmwh/react-refresh-webpack-plugin')

const isDevelopment = process.env.NODE_ENV !== 'production'

module.exports = {
  mode: isDevelopment ? 'development' : 'production',
  context: __dirname,

  entry: [
    'webpack-dev-server/client?http://localhost:3000',
    "./assets/js/index", // entry point of our app. assets/js/index.js should require other js modules and dependencies it needs
  ],
  output: {
    path: path.resolve("./assets/bundles/"),
    filename: "[name]-[hash].js",
    // Tell django to use this URL to load packages and not use STATIC_URL + bundle_name
    publicPath: 'http://localhost:3000/assets/bundles/',
  },

  plugins: [
    isDevelopment && new ReactRefreshWebpackPlugin(),
    new BundleTracker({ filename: "./webpack-stats.json" }),
  ].filter(Boolean),

  module: {
    rules: [
      { test: /\.jsx?$/, exclude: /node_modules/, loader: "babel-loader" }, // to transform JSX into JS
    ],
  },

  resolve: {
    modules: ["node_modules", "bower_components"],
    extensions: [".js", ".jsx"],
  },
};
