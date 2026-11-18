import type { CreateClientConfig } from './client/client.gen';

/**
 * Runtime config for the Hey API fetch client.
 * Empty baseUrl keeps relative `/api/...` paths so Vite proxy / nginx can route.
 */
export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: '',
});
