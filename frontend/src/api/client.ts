import { client } from './generated/client.gen'
import { notifySessionRejected } from './sessionEvents'

const runtimeOrigin =
  typeof window === 'undefined' ? 'http://127.0.0.1:5173' : window.location.origin
const baseUrl = import.meta.env.VITE_API_BASE_URL ?? runtimeOrigin

client.setConfig({
  baseUrl,
  credentials: 'include',
  fetch: (request) => globalThis.fetch(request),
})

client.interceptors.response.use((response) => {
  if (response.status === 401) notifySessionRejected()
  return response
})

export const apiClient = client
