import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Camera, Users, AlertCircle, Wifi, WifiOff, Play, StopCircle, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import api from '../lib/api'
import { format } from 'date-fns'

export default function CameraGrid({ wsData }) {
  const [wsUpdates, setWsUpdates] = useState({})
  const [sortField, setSortField] = useState('online') // Default sort by online status
  const [sortDirection, setSortDirection] = useState('desc') // desc = online first

  // Fetch initial camera status
  const { data: cameras, isLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: async () => {
      const res = await api.get('/api/cameras/status')
      return res.data
    },
    refetchInterval: 30000,  // Increased from 10s to 30s to reduce load
    staleTime: 10000  // Consider data fresh for 10 seconds
  })

  // Update from WebSocket - only store incremental updates
  useEffect(() => {
    if (wsData?.type === 'camera_status_update') {
      // Full update - clear WS updates since we have fresh data
      setWsUpdates({})
    } else if (wsData?.type === 'camera_status') {
      // Single camera update - merge with existing WS updates
      setWsUpdates(prev => ({
        ...prev,
        [wsData.data.cameraId]: {
          ...prev[wsData.data.cameraId],
          persons: wsData.data.persons,
          online: wsData.data.online
        }
      }))
    }
  }, [wsData])

  // Merge cameras data with websocket updates
  const cameraStatus = cameras ? {
    ...cameras,
    ...Object.keys(wsUpdates).reduce((acc, cameraId) => {
      acc[cameraId] = {
        ...(cameras[cameraId] || {}),
        ...wsUpdates[cameraId]
      }
      return acc
    }, {})
  } : {}

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading cameras...</div>
      </div>
    )
  }

  // Sort camera list
  const handleSort = (field) => {
    if (sortField === field) {
      // Toggle direction if same field
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      // New field, default to desc for most fields, asc for name
      setSortField(field)
      setSortDirection(field === 'camera_name' ? 'asc' : 'desc')
    }
  }

  const cameraList = Object.entries(cameraStatus).sort(([idA, statusA], [idB, statusB]) => {
    let valueA, valueB

    switch (sortField) {
      case 'camera_name':
        valueA = statusA.camera_name || idA
        valueB = statusB.camera_name || idB
        break
      case 'online':
        valueA = statusA.online ? 1 : 0
        valueB = statusB.online ? 1 : 0
        break
      case 'stream_connected':
        valueA = statusA.stream_connected ? 1 : 0
        valueB = statusB.stream_connected ? 1 : 0
        break
      case 'person_count':
        valueA = statusA.person_count || 0
        valueB = statusB.person_count || 0
        break
      case 'last_detection':
        valueA = statusA.last_detection ? new Date(statusA.last_detection).getTime() : 0
        valueB = statusB.last_detection ? new Date(statusB.last_detection).getTime() : 0
        break
      default:
        return 0
    }

    // String comparison
    if (typeof valueA === 'string') {
      const comparison = valueA.localeCompare(valueB)
      return sortDirection === 'asc' ? comparison : -comparison
    }

    // Number comparison
    if (sortDirection === 'asc') {
      return valueA - valueB
    } else {
      return valueB - valueA
    }
  })

  if (cameraList.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-8 text-center">
        <Camera className="mx-auto text-gray-400 mb-4" size={48} />
        <h3 className="text-lg font-semibold text-gray-900 mb-2">No Cameras Found</h3>
        <p className="text-gray-500">
          No cameras are currently available. Check your camera system connection.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">
          Camera Status ({cameraList.length})
        </h2>
        <div className="text-sm text-gray-500">
          {cameraList.filter(([_, s]) => s.online).length} online • {' '}
          {cameraList.filter(([_, s]) => !s.online).length} offline
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <SortableHeader
                label="Camera"
                field="camera_name"
                currentSort={sortField}
                direction={sortDirection}
                onSort={handleSort}
              />
              <SortableHeader
                label="Status"
                field="online"
                currentSort={sortField}
                direction={sortDirection}
                onSort={handleSort}
              />
              <SortableHeader
                label="Stream"
                field="stream_connected"
                currentSort={sortField}
                direction={sortDirection}
                onSort={handleSort}
              />
              <SortableHeader
                label="Persons"
                field="person_count"
                currentSort={sortField}
                direction={sortDirection}
                onSort={handleSort}
              />
              <SortableHeader
                label="Last Alert"
                field="last_detection"
                currentSort={sortField}
                direction={sortDirection}
                onSort={handleSort}
              />
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Mode
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Preset
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Worker
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {cameraList.map(([id, status]) => (
              <CameraRow key={id} cameraId={id} status={status} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CameraRow({ cameraId, status }) {
  const queryClient = useQueryClient()

  // Use API status as source of truth for online/offline
  const isOnline = status?.online || false
  const workerAnalyzing = status?.worker_analyzing || false
  const streamConnected = status?.stream_connected || false
  const persons = status?.person_count || 0
  const lastAlert = status?.last_detection
  const fps = status?.fps || 0
  const confidence = status?.avg_confidence || 0
  const cameraName = status?.camera_name || cameraId
  const isEnabled = status?.enabled !== undefined ? status.enabled : true
  const currentMode = status?.detection_mode || 'intrusion'
  const currentPresetId = status?.detection_preset_id

  // Fetch all presets
  const { data: presetsData } = useQuery({
    queryKey: ['presets'],
    queryFn: async () => {
      const res = await api.get('/api/presets')
      return res.data
    },
    staleTime: 60000  // Cache for 1 minute
  })

  // Show all presets (selecting a preset automatically changes the mode)
  const availablePresets = presetsData?.presets || []

  // Mutation to toggle camera
  const toggleMutation = useMutation({
    mutationFn: () => api.post(`/api/cameras/${cameraId}/toggle`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      queryClient.refetchQueries({ queryKey: ['cameras'] })
    },
    onError: (error) => {
      console.error('Error toggling camera:', error)
    }
  })

  // Mutation to change preset
  const presetMutation = useMutation({
    mutationFn: (presetId) => api.post(`/api/presets/camera/${cameraId}/set-preset`, null, {
      params: { preset_id: presetId }
    }),
    onSuccess: () => {
      // Force immediate refetch of camera data
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      queryClient.refetchQueries({ queryKey: ['cameras'] })
    },
    onError: (error) => {
      console.error('Error changing preset:', error)
    }
  })

  return (
    <tr className={`hover:bg-gray-50 transition-colors ${isOnline ? 'bg-white' : 'bg-gray-50'}`}>
      {/* Camera Name */}
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="flex items-center">
          <Camera
            className={isOnline ? 'text-green-500' : 'text-gray-400'}
            size={20}
          />
          <span className="ml-3 text-sm font-medium text-gray-900">
            {cameraName}
          </span>
        </div>
      </td>

      {/* Status */}
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="flex items-center gap-2">
          {isOnline ? (
            <Wifi className="text-green-500" size={16} />
          ) : (
            <WifiOff className="text-gray-400" size={16} />
          )}
          <span
            className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
              isOnline
                ? 'bg-green-100 text-green-800'
                : 'bg-gray-100 text-gray-800'
            }`}
          >
            {isOnline ? 'Online' : 'Offline'}
          </span>
        </div>
      </td>

      {/* Stream Status */}
      <td className="px-6 py-4 whitespace-nowrap">
        {isOnline ? (
          streamConnected ? (
            <span className="inline-flex px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">
              Connected
            </span>
          ) : (
            <span className="inline-flex px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800">
              No Stream
            </span>
          )
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>

      {/* Persons */}
      <td className="px-6 py-4 whitespace-nowrap">
        {streamConnected ? (
          <div className="flex items-center gap-2">
            <Users size={16} className="text-blue-500" />
            <span className="text-sm font-medium text-gray-900">
              {persons}
            </span>
          </div>
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>

      {/* Last Alert */}
      <td className="px-6 py-4 whitespace-nowrap">
        {lastAlert ? (
          <div className="flex items-center gap-1 text-xs text-orange-600">
            <AlertCircle size={12} />
            <span>{format(new Date(lastAlert), 'HH:mm:ss')}</span>
          </div>
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>

      {/* Detection Mode - Informational only, set by preset */}
      <td className="px-6 py-4 whitespace-nowrap">
        {status?.detection_mode ? (
          <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
            status.detection_mode === 'intrusion'
              ? 'bg-blue-100 text-blue-800'
              : 'bg-orange-100 text-orange-800'
          }`}>
            {status.detection_mode === 'intrusion' ? 'Intrusion' : 'PPE'}
          </span>
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>

      {/* Preset Selector */}
      <td className="px-6 py-4 whitespace-nowrap">
        {isOnline && availablePresets.length > 0 ? (
          <select
            value={currentPresetId || ''}
            onChange={(e) => {
              const value = e.target.value
              if (value) {
                presetMutation.mutate(parseInt(value))
              }
            }}
            disabled={presetMutation.isPending}
            className={`text-sm border border-gray-300 rounded-md px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              presetMutation.isPending ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
            }`}
          >
            <option value="">-- Select Preset --</option>
            <optgroup label="Intrusion Detection">
              {availablePresets.filter(p => p.mode === 'intrusion').map(preset => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </optgroup>
            <optgroup label="PPE Detection">
              {availablePresets.filter(p => p.mode === 'ppe').map(preset => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </optgroup>
          </select>
        ) : status?.preset_name ? (
          <span className="text-sm text-gray-700">{status.preset_name}</span>
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>

      {/* Worker Toggle */}
      <td className="px-6 py-4 whitespace-nowrap">
        {isOnline ? (
          <button
            onClick={() => toggleMutation.mutate()}
            disabled={toggleMutation.isPending}
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              isEnabled && streamConnected
                ? 'bg-red-50 text-red-700 hover:bg-red-100 border border-red-200'
                : isEnabled && !streamConnected
                  ? 'bg-yellow-50 text-yellow-700 hover:bg-yellow-100 border border-yellow-200'
                  : 'bg-green-50 text-green-700 hover:bg-green-100 border border-green-200'
            } ${toggleMutation.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {streamConnected && isEnabled ? (
              <StopCircle size={14} />
            ) : isEnabled ? (
              <Play size={14} className="animate-pulse" />
            ) : (
              <Play size={14} />
            )}
            {toggleMutation.isPending
              ? 'Wait...'
              : streamConnected && isEnabled
                ? 'Stop'
                : isEnabled && !streamConnected
                  ? 'Starting'
                  : 'Start'}
          </button>
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>
    </tr>
  )
}

function SortableHeader({ label, field, currentSort, direction, onSort }) {
  const isActive = currentSort === field

  return (
    <th
      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-2">
        <span>{label}</span>
        {isActive ? (
          direction === 'asc' ? (
            <ArrowUp size={14} className="text-gray-700" />
          ) : (
            <ArrowDown size={14} className="text-gray-700" />
          )
        ) : (
          <ArrowUpDown size={14} className="text-gray-400" />
        )}
      </div>
    </th>
  )
}
