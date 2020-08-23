module.exports = function (api) {
  // cache babel config by environment
  api.cache.using(() => process.env.NODE_ENV);

  const presets = ['@babel/preset-env', '@babel/preset-react', '@babel/preset-typescript'];
  const plugins = [!api.env('production') && 'react-refresh/babel'].filter(Boolean);
  return {
    plugins,
    presets,
  };
};

