import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import { Bell, Download, Filter, Trash2 } from 'lucide-react'
import api from '../lib/api'
import axios from 'axios'

export default function AlertLog({ wsData }) {
  const queryClient = useQueryClient()
  const [alerts, setAlerts] = useState([])
  const [filterCamera, setFilterCamera] = useState('')

  // Fetch initial alerts
  const { data: alertsData, isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: async () => {
      const res = await api.get('/api/alerts/recent?limit=100')
      return res.data
    },
    refetchInterval: 30000
  })

  // Mutation to delete single alert
  const deleteAlertMutation = useMutation({
    mutationFn: (alertId) => api.delete(`/api/alerts/${alertId}`),
    onSuccess: () => {
      queryClient.invalidateQueries(['alerts'])
    },
    onError: (error) => {
      console.error('Error deleting alert:', error)
      alert('Error deleting alert. Please try again.')
    }
  })

  // Mutation to delete all alerts
  const deleteAllAlertsMutation = useMutation({
    mutationFn: () => api.delete('/api/alerts'),
    onSuccess: () => {
      queryClient.invalidateQueries(['alerts'])
      setAlerts([])
    },
    onError: (error) => {
      console.error('Error deleting all alerts:', error)
      alert('Error deleting all alerts. Please try again.')
    }
  })

  // Handle delete all with confirmation
  const handleDeleteAll = () => {
    if (window.confirm(`Are you sure you want to delete all ${filteredAlerts.length} alerts? This action cannot be undone.`)) {
      deleteAllAlertsMutation.mutate()
    }
  }

  // Initialize alerts from query
  useEffect(() => {
    if (alertsData) {
      setAlerts(alertsData)
    }
  }, [alertsData])

  // Update from WebSocket
  useEffect(() => {
    if (wsData?.type === 'alert') {
      setAlerts(prev => [wsData.data, ...prev].slice(0, 100))
    }
  }, [wsData])

  // Show UI even while loading with empty state
  const displayAlerts = Array.isArray(alerts) ? alerts : []

  // Get unique cameras for filter
  const uniqueCameras = [...new Set(displayAlerts.map(a => a.camera_id))]

  // Filter alerts
  const filteredAlerts = filterCamera
    ? displayAlerts.filter(a => a.camera_id === filterCamera)
    : displayAlerts

  // Export to CSV
  const handleExport = async () => {
    try {
      const url = filterCamera
        ? `/api/alerts/export?camera_id=${filterCamera}`
        : '/api/alerts/export'

      const response = await axios.get(url, {
        responseType: 'blob'
      })

      const blob = new Blob([response.data], { type: 'text/csv' })
      const downloadUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = `alerts_${format(new Date(), 'yyyyMMdd_HHmmss')}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(downloadUrl)
    } catch (error) {
      console.error('Error exporting alerts:', error)
      alert('Error exporting alerts. Please try again.')
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-md">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bell className="text-orange-500" size={24} />
            <div>
              <h2 className="text-2xl font-bold text-gray-900">Alert Log</h2>
              <p className="text-sm text-gray-500">
                {filteredAlerts.length} alerts
                {filterCamera && ` from ${filteredAlerts.find(a => a.camera_id === filterCamera)?.camera_name || filterCamera}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Filter */}
            <div className="flex items-center gap-2">
              <Filter size={16} className="text-gray-500" />
              <select
                value={filterCamera}
                onChange={(e) => setFilterCamera(e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">All Cameras</option>
                {uniqueCameras.map(camera => {
                  const cameraName = alerts.find(a => a.camera_id === camera)?.camera_name || camera
                  return <option key={camera} value={camera}>{cameraName}</option>
                })}
              </select>
            </div>

            {/* Export Button */}
            <button
              onClick={handleExport}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              <Download size={16} />
              Export CSV
            </button>

            {/* Delete All Button */}
            <button
              onClick={handleDeleteAll}
              disabled={deleteAllAlertsMutation.isPending || filteredAlerts.length === 0}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                deleteAllAlertsMutation.isPending || filteredAlerts.length === 0
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-red-600 text-white hover:bg-red-700'
              }`}
            >
              <Trash2 size={16} />
              {deleteAllAlertsMutation.isPending ? 'Deleting...' : 'Delete All'}
            </button>
          </div>
        </div>
      </div>

      {/* Alert Table */}
      <div className="overflow-x-auto">
        {filteredAlerts.length === 0 ? (
          <div className="text-center py-12">
            <Bell className="mx-auto text-gray-400 mb-3" size={48} />
            <p className="text-gray-500">No alerts to display</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Timestamp
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Camera
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Persons
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Confidence
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Images
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredAlerts.map((alert, idx) => (
                <tr key={idx} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {format(new Date(alert.timestamp), 'yyyy-MM-dd HH:mm:ss')}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {alert.camera_name || alert.camera_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {alert.person_count} person{alert.person_count !== 1 ? 's' : ''}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    <div className="flex items-center">
                      <div className="w-full bg-gray-200 rounded-full h-2 mr-2" style={{width: '100px'}}>
                        <div
                          className="bg-green-500 h-2 rounded-full"
                          style={{width: `${alert.avg_confidence * 100}%`}}
                        />
                      </div>
                      <span className="text-xs font-medium">
                        {(alert.avg_confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    <div className="flex gap-2">
                      {alert.full_image_path && (
                        <a
                          href={alert.full_image_path}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 underline"
                        >
                          Full
                        </a>
                      )}
                      {alert.cropped_image_path && (
                        <a
                          href={alert.cropped_image_path}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 underline"
                        >
                          Annotated
                        </a>
                      )}
                      {!alert.full_image_path && !alert.cropped_image_path && (
                        <span className="text-gray-400 text-xs">No images</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    <button
                      onClick={() => {
                        if (window.confirm('Are you sure you want to delete this alert?')) {
                          deleteAlertMutation.mutate(alert.id)
                        }
                      }}
                      disabled={deleteAlertMutation.isPending}
                      className="text-red-600 hover:text-red-800 disabled:text-gray-400 transition-colors"
                      title="Delete alert"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Info */}
      {filteredAlerts.length > 0 && (
        <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
          <p className="text-sm text-gray-500">
            Showing {filteredAlerts.length} most recent alerts
          </p>
        </div>
      )}
    </div>
  )
}
