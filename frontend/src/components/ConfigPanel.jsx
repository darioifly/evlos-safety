import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { Settings, Save, CheckCircle, XCircle, RefreshCw, Send, AlertTriangle } from 'lucide-react'
import api, { evlosAPI } from '../lib/api'

export default function ConfigPanel() {
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState({})
  const [saveStatus, setSaveStatus] = useState(null)
  const [restartStatus, setRestartStatus] = useState(null)
  const [evlosTestStatus, setEvlosTestStatus] = useState(null)
  const [evlosToggleStatus, setEvlosToggleStatus] = useState(null)

  // Fetch current config
  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: async () => {
      const res = await api.get('/api/detection/config')
      return res.data
    }
  })

  // Update form when config loads
  useEffect(() => {
    if (config) {
      setFormData(config)
    }
  }, [config])

  // Mutation to update config
  const mutation = useMutation({
    mutationFn: (data) => api.post('/api/detection/config', data),
    onSuccess: (response) => {
      queryClient.invalidateQueries(['config'])
      setSaveStatus('success')
      setTimeout(() => setSaveStatus(null), 3000)
      console.log('Configuration updated:', response.data)
    },
    onError: (error) => {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus(null), 3000)
      console.error('Error updating config:', error)
    }
  })

  // Mutation to restart video worker
  const restartMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/api/worker/restart')
      return res.data
    },
    onSuccess: (response) => {
      setRestartStatus('success')
      setTimeout(() => setRestartStatus(null), 3000)
      console.log('Worker restarted:', response)
    },
    onError: (error) => {
      setRestartStatus('error')
      setTimeout(() => setRestartStatus(null), 3000)
      console.error('Error restarting worker:', error)
    }
  })

  // Fetch EVLOS configuration
  const { data: evlosConfig, refetch: refetchEvlos } = useQuery({
    queryKey: ['evlosConfig'],
    queryFn: evlosAPI.getConfig,
    refetchInterval: 5000 // Refresh every 5 seconds
  })

  // Test EVLOS connection
  const handleEvlosTest = async () => {
    setEvlosTestStatus('testing')
    try {
      const result = await evlosAPI.testConnection()
      if (result.success) {
        setEvlosTestStatus('success')
      } else {
        setEvlosTestStatus('error')
      }
      setTimeout(() => setEvlosTestStatus(null), 5000)
    } catch (error) {
      setEvlosTestStatus('error')
      setTimeout(() => setEvlosTestStatus(null), 5000)
      console.error('EVLOS test failed:', error)
    }
  }

  // Toggle EVLOS enable/disable
  const handleEvlosToggle = async (enable) => {
    setEvlosToggleStatus('loading')
    try {
      if (enable) {
        await evlosAPI.enable()
      } else {
        await evlosAPI.disable()
      }
      refetchEvlos()
      setEvlosToggleStatus('success')
      setTimeout(() => setEvlosToggleStatus(null), 3000)
    } catch (error) {
      setEvlosToggleStatus('error')
      setTimeout(() => setEvlosToggleStatus(null), 3000)
      console.error('EVLOS toggle failed:', error)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    mutation.mutate(formData)
  }

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // Use default values if config is still loading
  const displayConfig = formData && Object.keys(formData).length > 0 ? formData : {
    model: 'yolov8n.pt',
    confidence: 0.5,
    device: 'cuda:0',
    minPersons: 1,
    cooldown: 5,
    batchSize: 8,
    streamWidth: 640,
    streamHeight: 480,
    frameSampling: 10
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center gap-3 mb-6">
          <Settings className="text-blue-500" size={32} />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Detection Configuration</h2>
            <p className="text-sm text-gray-500">
              Configure detection parameters and alert settings
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Model Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Detection Model
            </label>
            <select
              value={displayConfig.model || 'models/ppe/construction_safety.pt'}
              onChange={(e) => handleChange('model', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="models/ppe/construction_safety.pt">PPE Detection - Construction Safety (Recommended)</option>
              <option value="models/ppe/workspace_safety.pt">PPE Detection - Workspace Safety (23k+ images)</option>
              <option value="models/ppe/helmet_vest.pt">PPE Detection - Helmet + Vest</option>
              <option value="yolov8n.pt">Person Detection - Intrusion Only</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              {displayConfig.model?.includes('construction_safety')
                ? 'Direct NO-Safety Vest & NO-Hardhat detection. 10 classes, 2.8k images.'
                : displayConfig.model?.includes('workspace_safety')
                ? 'Best for varied vest colors (orange, yellow). 17 classes including helmet/vest.'
                : displayConfig.model?.includes('ppe')
                ? 'Detects helmet, vest, and PPE violations (5 classes)'
                : 'Detects only persons for intrusion monitoring'}
            </p>
          </div>

          {/* Detection Mode (only if PPE model selected) */}
          {displayConfig.model?.includes('ppe') && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Detection Mode
              </label>
              <select
                value={displayConfig.detectionMode || 'dual'}
                onChange={(e) => handleChange('detectionMode', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
              >
                <option value="dual">Dual Mode - Auto Switch Day/Night (Recommended)</option>
                <option value="ppe">PPE Mode - Always Check Safety Equipment</option>
                <option value="person">Person Mode - Always Check Intrusion Only</option>
              </select>
              <p className="mt-2 text-xs text-gray-600">
                <strong>Dual Mode:</strong> Day = PPE check (helmet+vest), Night = Intrusion detection
              </p>

              {/* Schedule Settings (only if dual mode) */}
              {displayConfig.detectionMode === 'dual' && (
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Day Start Hour
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="23"
                      value={displayConfig.schedule?.dayStartHour || 6}
                      onChange={(e) => handleChange('schedule', {
                        ...displayConfig.schedule,
                        dayStartHour: parseInt(e.target.value)
                      })}
                      className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Day End Hour
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="23"
                      value={displayConfig.schedule?.dayEndHour || 18}
                      onChange={(e) => handleChange('schedule', {
                        ...displayConfig.schedule,
                        dayEndHour: parseInt(e.target.value)
                      })}
                      className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              )}

              {/* PPE Rules */}
              {(displayConfig.detectionMode === 'ppe' || displayConfig.detectionMode === 'dual') && (
                <div className="mt-4 space-y-2">
                  <p className="text-xs font-medium text-gray-600">PPE Requirements:</p>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={displayConfig.ppeRules?.requireHelmet !== false}
                      onChange={(e) => handleChange('ppeRules', {
                        ...displayConfig.ppeRules,
                        requireHelmet: e.target.checked
                      })}
                      className="rounded text-blue-600"
                    />
                    <span className="text-sm text-gray-700">Require Safety Helmet</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={displayConfig.ppeRules?.requireVest !== false}
                      onChange={(e) => handleChange('ppeRules', {
                        ...displayConfig.ppeRules,
                        requireVest: e.target.checked
                      })}
                      className="rounded text-blue-600"
                    />
                    <span className="text-sm text-gray-700">Require Safety Vest</span>
                  </label>
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={displayConfig.ppeRules?.alwaysAlertOnPerson === true}
                        onChange={(e) => handleChange('ppeRules', {
                          ...displayConfig.ppeRules,
                          alwaysAlertOnPerson: e.target.checked
                        })}
                        className="rounded text-orange-600"
                      />
                      <span className="text-sm text-orange-700 font-medium">
                        Test Mode: Alert on Any Person Detection
                      </span>
                    </label>
                    <p className="text-xs text-gray-500 ml-6 mt-1">
                      Enable this to test if detection is working. Alerts will trigger on any person, even if wearing PPE.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* NxWitness Alerts Configuration */}
          <div className="bg-cyan-50 border border-cyan-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  NxWitness Alert Integration
                </label>
                <p className="text-xs text-gray-600 mt-1">
                  Send HTTP alerts and create bookmarks on NxWitness timeline
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={displayConfig.nxWitnessAlerts?.enabled === true}
                  onChange={(e) => handleChange('nxWitnessAlerts', {
                    ...displayConfig.nxWitnessAlerts,
                    enabled: e.target.checked
                  })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-cyan-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-600"></div>
              </label>
            </div>

            {displayConfig.nxWitnessAlerts?.enabled && (
              <div className="mt-3 pt-3 border-t border-cyan-200 space-y-3">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={displayConfig.nxWitnessAlerts?.sendEvents !== false}
                    onChange={(e) => handleChange('nxWitnessAlerts', {
                      ...displayConfig.nxWitnessAlerts,
                      sendEvents: e.target.checked
                    })}
                    className="rounded text-cyan-600"
                  />
                  <span className="text-sm text-gray-700">Send Event Notifications (HTTP POST)</span>
                </label>

                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={displayConfig.nxWitnessAlerts?.createBookmarks !== false}
                    onChange={(e) => handleChange('nxWitnessAlerts', {
                      ...displayConfig.nxWitnessAlerts,
                      createBookmarks: e.target.checked
                    })}
                    className="rounded text-cyan-600"
                  />
                  <span className="text-sm text-gray-700">Create Timeline Bookmarks</span>
                </label>

                {displayConfig.nxWitnessAlerts?.createBookmarks !== false && (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Bookmark Duration (seconds)
                    </label>
                    <input
                      type="number"
                      min="30"
                      max="600"
                      step="30"
                      value={displayConfig.nxWitnessAlerts?.bookmarkDuration || 300}
                      onChange={(e) => handleChange('nxWitnessAlerts', {
                        ...displayConfig.nxWitnessAlerts,
                        bookmarkDuration: parseInt(e.target.value)
                      })}
                      className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                    />
                    <p className="text-xs text-gray-500 mt-1">Duration of video bookmark (30-600s, default 300s = 5 min)</p>
                  </div>
                )}

                <div className="text-xs text-cyan-700 bg-cyan-100 rounded p-3 space-y-1">
                  <p><strong>ℹ️ What this does:</strong></p>
                  <ul className="list-disc list-inside space-y-1 ml-2">
                    <li><strong>Events:</strong> Sends HTTP POST to NxWitness /api/createEvent with detection data</li>
                    <li><strong>Bookmarks:</strong> Creates timeline markers for easy video review in NxWitness</li>
                    <li>Includes bounding box coordinates and confidence scores</li>
                    <li>Check backend logs for [ALERT SEND] messages to verify delivery</li>
                  </ul>
                </div>

                <div className="text-xs text-orange-700 bg-orange-100 rounded p-2 border border-orange-200">
                  <strong>⚠️ Note:</strong> Ensure NxWitness API is accessible at the configured server URL. Check logs for HTTP response status (200 = success).
                </div>
              </div>
            )}
          </div>

          {/* EVLOS External Integration */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  EVLOS External Platform Integration
                </label>
                <p className="text-xs text-gray-600 mt-1">
                  Send alert images and metadata to external EVLOS monitoring platform
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={evlosConfig?.enabled === true}
                  onChange={(e) => handleEvlosToggle(e.target.checked)}
                  disabled={evlosToggleStatus === 'loading'}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-amber-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-600 peer-disabled:opacity-50"></div>
              </label>
            </div>

            {/* EVLOS Configuration Details */}
            {evlosConfig && (
              <div className="space-y-3">
                <div className="text-xs bg-white rounded p-3 border border-gray-200">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <span className="text-gray-500">Status:</span>
                      <span className={`ml-2 font-medium ${evlosConfig.enabled ? 'text-green-600' : 'text-gray-500'}`}>
                        {evlosConfig.enabled ? '✓ Enabled' : '○ Disabled'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Timeout:</span>
                      <span className="ml-2 font-medium">{evlosConfig.timeout}s</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-gray-500">API URL:</span>
                      <span className="ml-2 font-mono text-xs break-all">{evlosConfig.api_url}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Max Retries:</span>
                      <span className="ml-2 font-medium">{evlosConfig.max_retries}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Backoff:</span>
                      <span className="ml-2 text-xs">2s, 4s, 8s</span>
                    </div>
                  </div>
                </div>

                {/* Test Connection Button */}
                <button
                  type="button"
                  onClick={handleEvlosTest}
                  disabled={evlosTestStatus === 'testing' || !evlosConfig.enabled}
                  className={`w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg font-medium text-sm transition-colors ${
                    evlosTestStatus === 'testing'
                      ? 'bg-gray-400 cursor-not-allowed text-white'
                      : !evlosConfig.enabled
                      ? 'bg-gray-200 cursor-not-allowed text-gray-500'
                      : 'bg-amber-600 hover:bg-amber-700 text-white'
                  }`}
                >
                  <Send size={16} className={evlosTestStatus === 'testing' ? 'animate-pulse' : ''} />
                  {evlosTestStatus === 'testing' ? 'Testing Connection...' : 'Test EVLOS Connection'}
                </button>

                {/* Test Status Messages */}
                {evlosTestStatus === 'success' && (
                  <div className="flex items-center gap-2 text-green-600 bg-green-50 p-2 rounded text-sm">
                    <CheckCircle size={16} />
                    <span className="font-medium">EVLOS connection successful!</span>
                  </div>
                )}

                {evlosTestStatus === 'error' && (
                  <div className="flex items-center gap-2 text-red-600 bg-red-50 p-2 rounded text-sm">
                    <XCircle size={16} />
                    <span className="font-medium">Connection failed. Check EVLOS API endpoint.</span>
                  </div>
                )}

                {/* Toggle Status Messages */}
                {evlosToggleStatus === 'success' && (
                  <div className="flex items-center gap-2 text-green-600 bg-green-50 p-2 rounded text-sm">
                    <CheckCircle size={16} />
                    <span className="font-medium">EVLOS {evlosConfig.enabled ? 'enabled' : 'disabled'} successfully!</span>
                  </div>
                )}

                {evlosToggleStatus === 'error' && (
                  <div className="flex items-center gap-2 text-red-600 bg-red-50 p-2 rounded text-sm">
                    <XCircle size={16} />
                    <span className="font-medium">Failed to toggle EVLOS. Please try again.</span>
                  </div>
                )}

                {/* Info Box */}
                <div className="text-xs text-amber-700 bg-amber-100 rounded p-3 space-y-1">
                  <p><strong>ℹ️ How EVLOS works:</strong></p>
                  <ul className="list-disc list-inside space-y-1 ml-2">
                    <li>Sends alert images + metadata to external platform</li>
                    <li>Auto-retry with exponential backoff (3 attempts)</li>
                    <li>Failed alerts saved locally for manual retry</li>
                    <li>Fully asynchronous - doesn't block video processing</li>
                  </ul>
                </div>

                {/* Alert Mapping Info */}
                <div className="text-xs bg-white rounded p-3 border border-amber-200">
                  <p className="font-medium text-gray-700 mb-2">Alert Type Mapping:</p>
                  <div className="space-y-1 text-gray-600">
                    <div className="flex justify-between">
                      <span>1-2 persons detected</span>
                      <span className="font-mono text-amber-700">→ intrusion</span>
                    </div>
                    <div className="flex justify-between">
                      <span>3+ persons detected</span>
                      <span className="font-mono text-amber-700">→ crowd</span>
                    </div>
                    <div className="flex justify-between">
                      <span>PPE violation (future)</span>
                      <span className="font-mono text-amber-700">→ no_ppe</span>
                    </div>
                  </div>
                </div>

                {/* Warning when disabled */}
                {!evlosConfig.enabled && (
                  <div className="flex items-start gap-2 text-orange-700 bg-orange-100 rounded p-3 text-xs border border-orange-200">
                    <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium mb-1">EVLOS is currently disabled</p>
                      <p>Enable the toggle above to start sending alerts to the external platform. Make sure the EVLOS API is reachable before enabling.</p>
                    </div>
                  </div>
                )}

                {/* Runtime vs Config Note */}
                <div className="text-xs text-gray-600 bg-gray-50 rounded p-2 border border-gray-200">
                  <strong>Note:</strong> Toggle changes are runtime-only. To persist, set <code className="bg-gray-200 px-1 rounded">EVLOS_ENABLED=true</code> in backend config and restart.
                </div>
              </div>
            )}
          </div>

          {/* Confidence Threshold */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Confidence Threshold: {(displayConfig.confidence || 0.5).toFixed(2)}
            </label>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={displayConfig.confidence || 0.5}
              onChange={(e) => handleChange('confidence', parseFloat(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0.1 (Low)</span>
              <span>0.5 (Medium)</span>
              <span>0.9 (High)</span>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Lower values detect more but may have false positives
            </p>
          </div>

          {/* Stream Quality Selection */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Stream Quality
            </label>
            <select
              value={displayConfig.streamQuality || 'medium'}
              onChange={(e) => handleChange('streamQuality', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-green-500 focus:border-transparent bg-white"
            >
              <option value="low">Low Quality (~352x240) - Faster, lower accuracy</option>
              <option value="medium">Medium Quality (~640x480) - Balanced</option>
              <option value="high">High Quality (~1280x720) - Better PPE detection</option>
              <option value="highest">Highest Quality (Max resolution) - Best accuracy</option>
            </select>
            <p className="mt-2 text-xs text-green-700 bg-green-100 rounded p-2">
              <strong>Recommendation:</strong> Use <strong>High</strong> or <strong>Highest</strong> quality for better PPE detection at distance.
              Higher quality uses more CPU/GPU but improves detection accuracy significantly.
            </p>
            <div className="mt-2 text-xs text-gray-600">
              <p><strong>Current resolution:</strong> {displayConfig.streamWidth || '?'}x{displayConfig.streamHeight || '?'} (read-only)</p>
              <p className="mt-1 text-gray-500">Resolution is automatically determined by stream quality setting</p>
            </div>
          </div>

          {/* Device Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Processing Device
            </label>
            <select
              value={displayConfig.device || 'cuda:0'}
              onChange={(e) => handleChange('device', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="cuda:0">CUDA (GPU - RTX 3090)</option>
              <option value="cpu">CPU</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              GPU is recommended for best performance
            </p>
          </div>

          {/* Minimum Persons */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Minimum Persons for Alert
            </label>
            <input
              type="number"
              min="1"
              max="10"
              value={displayConfig.minPersons || 1}
              onChange={(e) => handleChange('minPersons', parseInt(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              Alert will trigger when at least this many persons are detected
            </p>
          </div>

          {/* Cooldown */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Alert Cooldown (seconds)
            </label>
            <input
              type="number"
              min="1"
              max="60"
              value={displayConfig.cooldown || 5}
              onChange={(e) => handleChange('cooldown', parseInt(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              Minimum time between alerts for the same camera
            </p>
          </div>

          {/* Batch Size */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Batch Size
            </label>
            <input
              type="number"
              min="1"
              max="16"
              value={displayConfig.batchSize || 8}
              onChange={(e) => handleChange('batchSize', parseInt(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              Number of frames processed together (higher = better GPU utilization)
            </p>
          </div>

          {/* Submit Button */}
          <div className="pt-4 border-t border-gray-200">
            <button
              type="submit"
              disabled={mutation.isPending}
              className={`w-full flex items-center justify-center gap-2 py-3 px-4 rounded-lg font-semibold text-white transition-colors ${
                mutation.isPending
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800'
              }`}
            >
              <Save size={20} />
              {mutation.isPending ? 'Saving...' : 'Apply Configuration'}
            </button>

            {/* Restart Worker Button */}
            <button
              type="button"
              onClick={() => restartMutation.mutate()}
              disabled={restartMutation.isPending}
              className={`w-full flex items-center justify-center gap-2 py-3 px-4 rounded-lg font-semibold text-white transition-colors mt-3 ${
                restartMutation.isPending
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-orange-600 hover:bg-orange-700 active:bg-orange-800'
              }`}
            >
              <RefreshCw size={20} className={restartMutation.isPending ? 'animate-spin' : ''} />
              {restartMutation.isPending ? 'Restarting Worker...' : 'Restart Video Worker'}
            </button>

            {/* Status Messages */}
            {saveStatus === 'success' && (
              <div className="mt-4 flex items-center gap-2 text-green-600 bg-green-50 p-3 rounded-lg">
                <CheckCircle size={20} />
                <span className="font-medium">Configuration saved successfully!</span>
              </div>
            )}

            {saveStatus === 'error' && (
              <div className="mt-4 flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-lg">
                <XCircle size={20} />
                <span className="font-medium">Error saving configuration. Please try again.</span>
              </div>
            )}

            {restartStatus === 'success' && (
              <div className="mt-4 flex items-center gap-2 text-green-600 bg-green-50 p-3 rounded-lg">
                <CheckCircle size={20} />
                <span className="font-medium">Video worker restarted successfully!</span>
              </div>
            )}

            {restartStatus === 'error' && (
              <div className="mt-4 flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-lg">
                <XCircle size={20} />
                <span className="font-medium">Error restarting worker. Please try manually.</span>
              </div>
            )}
          </div>
        </form>

        {/* Read-only Info */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Current Stream Settings</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Stream Quality:</span>
              <span className="ml-2 font-medium capitalize">{displayConfig.streamQuality || 'medium'}</span>
              <span className="ml-2 text-xs text-gray-400">
                {displayConfig.streamQuality === 'low' && '(~352x240)'}
                {displayConfig.streamQuality === 'medium' && '(~640x480)'}
                {displayConfig.streamQuality === 'high' && '(~848x480 or 1280x720)'}
                {displayConfig.streamQuality === 'highest' && '(1080p or higher)'}
                {!displayConfig.streamQuality && '(~640x480)'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Frame Sampling:</span>
              <span className="ml-2 font-medium">1 / {displayConfig.frameSampling}</span>
            </div>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            Note: Actual resolution depends on camera capabilities and NX Witness settings. Check logs for exact resolution.
          </p>
        </div>
      </div>
    </div>
  )
}
