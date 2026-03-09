import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { Activity, Zap, AlertTriangle, Clock, TrendingUp } from 'lucide-react'
import api from '../lib/api'

export default function Dashboard({ wsData }) {
  const [metricsData, setMetricsData] = useState(null)

  // Fetch metrics
  const { data: metrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: async () => {
      const res = await api.get('/api/metrics')
      return res.data
    },
    refetchInterval: 5000
  })

  // Fetch alert stats
  const { data: stats } = useQuery({
    queryKey: ['alert-stats'],
    queryFn: async () => {
      const res = await api.get('/api/alerts/stats')
      return res.data
    },
    refetchInterval: 10000
  })

  // Update from query
  useEffect(() => {
    if (metrics) {
      setMetricsData(metrics)
    }
  }, [metrics])

  // Update from WebSocket
  useEffect(() => {
    if (wsData?.type === 'metrics_update') {
      setMetricsData(wsData.data)
    }
  }, [wsData])

  // Use default values if data is still loading
  const displayMetrics = metricsData || {
    avgFps: 0,
    gpuUsage: 0,
    alertsToday: 0,
    uptime: 0,
    totalDetections: 0,
    cameraFps: {},
    history: [],
    avgProcessingTime: 0
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          icon={<Activity className="text-blue-500" size={32} />}
          title="Average FPS"
          value={displayMetrics.avgFps?.toFixed(1) || '0.0'}
          subtitle="Frames per second"
          color="blue"
        />

        <StatCard
          icon={<Zap className="text-green-500" size={32} />}
          title="GPU Usage"
          value={`${displayMetrics.gpuUsage || 0}%`}
          subtitle={displayMetrics.gpuMemory ? `${displayMetrics.gpuMemory.toFixed(1)} / ${displayMetrics.gpuMemoryTotal.toFixed(1)} GB` : 'Not available'}
          color="green"
        />

        <StatCard
          icon={<AlertTriangle className="text-orange-500" size={32} />}
          title="Alerts Today"
          value={displayMetrics.alertsToday || 0}
          subtitle={`${stats?.total_alerts || 0} total`}
          color="orange"
        />

        <StatCard
          icon={<Clock className="text-purple-500" size={32} />}
          title="Uptime"
          value={`${displayMetrics.uptime?.toFixed(1) || 0}h`}
          subtitle="System running time"
          color="purple"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* FPS History Chart */}
        <ChartCard title="Detection Performance" icon={<TrendingUp size={20} />}>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={displayMetrics.history || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="time"
                stroke="#6b7280"
                style={{ fontSize: '12px' }}
              />
              <YAxis
                stroke="#6b7280"
                style={{ fontSize: '12px' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px'
                }}
              />
              <Line
                type="monotone"
                dataKey="fps"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="FPS"
              />
              <Line
                type="monotone"
                dataKey="detections"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                name="Detections"
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Camera FPS Chart */}
        <ChartCard title="FPS per Camera" icon={<Activity size={20} />}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={Object.entries(displayMetrics.cameraFps || {}).map(([camera, fps]) => ({
              camera: camera.slice(0, 10),
              fps: fps
            }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="camera"
                stroke="#6b7280"
                style={{ fontSize: '10px' }}
                angle={-45}
                textAnchor="end"
                height={80}
              />
              <YAxis
                stroke="#6b7280"
                style={{ fontSize: '12px' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px'
                }}
              />
              <Bar dataKey="fps" fill="#3b82f6" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Alerts per Camera */}
      {stats?.alerts_per_camera && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Alerts per Camera
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {Object.entries(stats.alerts_per_camera)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 10)
              .map(([camera, count]) => (
                <div
                  key={camera}
                  className="bg-gray-50 rounded-lg p-4 border border-gray-200"
                >
                  <div className="text-sm font-medium text-gray-700 truncate mb-1" title={camera}>
                    {camera}
                  </div>
                  <div className="text-2xl font-bold text-blue-600">
                    {count}
                  </div>
                  <div className="text-xs text-gray-500">alerts</div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* System Info */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          System Information
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <InfoItem
            label="Total Detections"
            value={displayMetrics.totalDetections || 0}
          />
          <InfoItem
            label="Active Cameras"
            value={Object.keys(displayMetrics.cameraFps || {}).length}
          />
          <InfoItem
            label="Avg Processing Time"
            value={`${displayMetrics.avgProcessingTime?.toFixed(1) || 0} ms`}
          />
          <InfoItem
            label="Cameras with Alerts"
            value={stats?.cameras_with_alerts || 0}
          />
          <InfoItem
            label="Buffered Alerts"
            value={stats?.buffer_status?.buffered_alerts || 0}
          />
          <InfoItem
            label="Buffer Capacity"
            value={stats?.buffer_status?.buffer_capacity || 0}
          />
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon, title, value, subtitle, color }) {
  const colorClasses = {
    blue: 'bg-blue-50 border-blue-200',
    green: 'bg-green-50 border-green-200',
    orange: 'bg-orange-50 border-orange-200',
    purple: 'bg-purple-50 border-purple-200'
  }

  return (
    <div className={`rounded-lg shadow-md p-6 border ${colorClasses[color] || 'bg-gray-50 border-gray-200'}`}>
      <div className="flex items-center justify-between mb-4">
        <div>{icon}</div>
        <div className="text-right">
          <p className="text-sm text-gray-600">{title}</p>
        </div>
      </div>
      <div className="text-3xl font-bold text-gray-900 mb-1">
        {value}
      </div>
      <p className="text-sm text-gray-500">{subtitle}</p>
    </div>
  )
}

function ChartCard({ title, icon, children }) {
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex items-center gap-2 mb-4">
        {icon}
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
      </div>
      {children}
    </div>
  )
}

function InfoItem({ label, value }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-gray-200">
      <span className="text-sm text-gray-600">{label}</span>
      <span className="text-sm font-semibold text-gray-900">{value}</span>
    </div>
  )
}
