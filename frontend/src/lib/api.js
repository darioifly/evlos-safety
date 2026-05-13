import axios from 'axios'

// API calls always go to the same origin that served the page.
// - Built mode: FastAPI on :7002 serves both the SPA and the API.
// - Vite dev mode (:5173): vite.config.js proxies /api and /ws to :7002.
const api = axios.create({
  baseURL: '',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// EVLOS API functions
export const evlosAPI = {
  // Get EVLOS configuration
  getConfig: async () => {
    const response = await api.get('/api/evlos/config')
    return response.data
  },

  // Test EVLOS connection
  testConnection: async () => {
    const response = await api.post('/api/evlos/test')
    return response.data
  },

  // Get failed alerts
  getFailedAlerts: async () => {
    const response = await api.get('/api/evlos/failed-alerts')
    return response.data
  },

  // Enable EVLOS
  enable: async () => {
    const response = await api.post('/api/evlos/enable')
    return response.data
  },

  // Disable EVLOS
  disable: async () => {
    const response = await api.post('/api/evlos/disable')
    return response.data
  }
}

export default api
