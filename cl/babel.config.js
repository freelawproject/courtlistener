module.exports = function (api) {
  // cache babel config by environment
  api.cache.using(() => process.env.NODE_ENV)

  const presets = ['@babel/preset-env', '@babel/preset-react']
  const plugins = [
    !api.env('production') && 'react-refresh/babel'
  ]
  return {
    plugins,
    presets
  }
}