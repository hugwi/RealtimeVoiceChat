// Voice Gateway UI - Webpack config for single-spa build

const path = require('path');

module.exports = {
  mode: 'development',
  entry: './single-spa/index.tsx',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'voice-settings.js',
    libraryTarget: 'module',
    clean: true,
  },
  experiments: {
    outputModule: true,
  },
  externals: {
    react: 'react',
    'react-dom': 'react-dom',
  },
  resolve: {
    extensions: ['.tsx', '.ts', '.js'],
    alias: {
      '@voice-gateway/ui': path.resolve(__dirname, 'core'),
      '@voice-gateway/ui/react': path.resolve(__dirname, 'react'),
    },
  },
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: {
          loader: 'ts-loader',
          options: {
            transpileOnly: true,
          },
        },
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
    ],
  },
  devServer: {
    port: 3001,
    static: {
      directory: path.resolve(__dirname, 'dist'),
    },
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
    hot: true,
  },
  devtool: 'source-map',
};
