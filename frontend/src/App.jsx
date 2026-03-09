import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import CameraGrid from './components/CameraGrid'
import ConfigPanel from './components/ConfigPanel'
import AlertLog from './components/AlertLog'
import Dashboard from './components/Dashboard'
import Presets from './components/Presets'
import { useWebSocket } from './hooks/useWebSocket'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

function App() {
  // Get initial tab from URL hash or default to 'cameras'
  const getInitialTab = () => {
    const hash = window.location.hash.slice(1) // Remove '#'
    return hash || 'cameras'
  }

  const [activeTab, setActiveTab] = useState(getInitialTab)
  const { data: wsData, status } = useWebSocket('/ws')

  // Update URL hash when tab changes
  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    window.location.hash = tabId
  }

  const tabs = [
    { id: 'cameras', label: 'Cameras', icon: '📹' },
    { id: 'presets', label: 'Presets', icon: '🎯' },
    { id: 'config', label: 'Configuration', icon: '⚙️' },
    { id: 'alerts', label: 'Alerts', icon: '🔔' },
    { id: 'dashboard', label: 'Dashboard', icon: '📊' }
  ]

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-100">
        {/* Header */}
        <header className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-4 py-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <img
                  src="/evlos-logo.png"
                  alt="EVLOS Logo"
                  className="h-16 w-auto"
                />
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${
                    status === 'connected' ? 'bg-green-500 animate-pulse' : 'bg-red-500'
                  }`} />
                  <span className="text-sm font-medium text-gray-600">
                    {status === 'connected' ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </header>

        {/* Navigation */}
        <nav className="bg-white shadow-sm border-t border-gray-200">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex space-x-8">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <span className="mr-2">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 py-8">
          {activeTab === 'cameras' && <CameraGrid wsData={wsData} />}
          {activeTab === 'presets' && <Presets />}
          {activeTab === 'config' && <ConfigPanel />}
          {activeTab === 'alerts' && <AlertLog wsData={wsData} />}
          {activeTab === 'dashboard' && <Dashboard wsData={wsData} />}
        </main>

        {/* Footer */}
        <footer className="bg-white border-t border-gray-200 mt-12">
          <div className="max-w-7xl mx-auto px-4 py-6">
            <p className="text-center text-base font-bold text-gray-700 uppercase tracking-wide">
              EVLOS SAFETY v1.0.0 | Advanced Video Surveillance System
            </p>
          </div>
        </footer>
      </div>
    </QueryClientProvider>
  )
}

export default App
