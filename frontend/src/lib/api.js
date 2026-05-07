import axios from 'axios'

// Determine API base URL
const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
const API_BASE_URL = isDev ? 'http://localhost:7002' : ''

// Create axios instance with baseURL
const api = axios.create({
  baseURL: API_BASE_URL,
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
