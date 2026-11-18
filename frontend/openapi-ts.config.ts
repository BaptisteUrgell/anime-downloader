import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: './openapi.json',
  output: {
    path: './src/api/client',
    clean: true,
  },
  plugins: [
    {
      name: '@hey-api/client-fetch',
      // Path relative to this config file (frontend/)
      runtimeConfigPath: './src/api/hey-api.ts',
    },
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
  ],
});
