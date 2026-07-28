import { client } from './generated/client.gen'

const runtimeOrigin =
  typeof window === 'undefined' ? 'http://127.0.0.1:5173' : window.location.origin
const baseUrl = import.meta.env.VITE_API_BASE_URL ?? runtimeOrigin

client.setConfig({
  baseUrl,
  fetch: (request) => globalThis.fetch(request),
})

export const apiClient = client
