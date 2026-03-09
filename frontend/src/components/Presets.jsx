import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Plus, Edit2, Trash2, Save, X } from 'lucide-react'
import api from '../lib/api'

export default function Presets() {
  const queryClient = useQueryClient()
  const [editingId, setEditingId] = useState(null)
  const [isCreating, setIsCreating] = useState(false)
  const [formData, setFormData] = useState(getEmptyForm())

  // Fetch presets
  const { data: presetsData, isLoading } = useQuery({
    queryKey: ['presets'],
    queryFn: async () => {
      const res = await api.get('/api/presets')
      return res.data
    }
  })

  const presets = presetsData?.presets || []

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data) => api.post('/api/presets', data),
    onSuccess: () => {
      // Invalidate both presets and cameras queries to update all dropdowns
      queryClient.invalidateQueries({ queryKey: ['presets'] })
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      setIsCreating(false)
      setFormData(getEmptyForm())
    }
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => api.put(`/api/presets/${id}`, data),
    onSuccess: () => {
      // Invalidate both presets and cameras queries to update all dropdowns
      queryClient.invalidateQueries({ queryKey: ['presets'] })
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      setEditingId(null)
    }
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id) => api.delete(`/api/presets/${id}`),
    onSuccess: () => {
      // Invalidate both presets and cameras queries to update all dropdowns
      queryClient.invalidateQueries({ queryKey: ['presets'] })
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
    },
    onError: (error) => {
      alert(error.response?.data?.detail || 'Error deleting preset')
    }
  })

  function getEmptyForm() {
    return {
      name: '',
      description: '',
      mode: 'intrusion',
      intrusion_min_persons: 1,
      intrusion_confidence: 0.5,
      ppe_require_helmet: true,
      ppe_require_vest: true,
      ppe_confidence: 0.6,
      cooldown_seconds: 5
    }
  }

  const handleCreate = () => {
    createMutation.mutate(formData)
  }

  const handleUpdate = (id) => {
    const preset = presets.find(p => p.id === id)
    updateMutation.mutate({ id, data: formData })
  }

  const handleEdit = (preset) => {
    setEditingId(preset.id)
    setFormData({
      name: preset.name,
      description: preset.description || '',
      mode: preset.mode,
      intrusion_min_persons: preset.intrusion_min_persons,
      intrusion_confidence: preset.intrusion_confidence,
      ppe_require_helmet: preset.ppe_require_helmet,
      ppe_require_vest: preset.ppe_require_vest,
      ppe_confidence: preset.ppe_confidence,
      cooldown_seconds: preset.cooldown_seconds
    })
  }

  const handleCancel = () => {
    setEditingId(null)
    setIsCreating(false)
    setFormData(getEmptyForm())
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading presets...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Detection Presets</h2>
        <button
          onClick={() => setIsCreating(true)}
          disabled={isCreating}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus size={20} />
          New Preset
        </button>
      </div>

      {/* Create Form */}
      {isCreating && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Create New Preset</h3>
          <PresetForm
            formData={formData}
            setFormData={setFormData}
            onSave={handleCreate}
            onCancel={handleCancel}
            isSaving={createMutation.isPending}
          />
        </div>
      )}

      {/* Presets List */}
      <div className="space-y-4">
        {presets.map(preset => (
          <div key={preset.id} className="bg-white rounded-lg shadow p-6">
            {editingId === preset.id ? (
              <div>
                <h3 className="text-lg font-semibold mb-4">Edit Preset</h3>
                <PresetForm
                  formData={formData}
                  setFormData={setFormData}
                  onSave={() => handleUpdate(preset.id)}
                  onCancel={handleCancel}
                  isSaving={updateMutation.isPending}
                />
              </div>
            ) : (
              <div>
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-lg font-semibold text-gray-900">{preset.name}</h3>
                      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                        preset.mode === 'intrusion'
                          ? 'bg-blue-100 text-blue-800'
                          : 'bg-orange-100 text-orange-800'
                      }`}>
                        {preset.mode === 'intrusion' ? 'Intrusion' : 'PPE'}
                      </span>
                    </div>
                    {preset.description && (
                      <p className="text-sm text-gray-600 mt-1">{preset.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleEdit(preset)}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    >
                      <Edit2 size={18} />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete preset "${preset.name}"?`)) {
                          deleteMutation.mutate(preset.id)
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  {preset.mode === 'intrusion' ? (
                    <>
                      <div>
                        <span className="font-medium text-gray-700">Min Persons:</span>
                        <span className="ml-2 text-gray-600">{preset.intrusion_min_persons}</span>
                      </div>
                      <div>
                        <span className="font-medium text-gray-700">Confidence:</span>
                        <span className="ml-2 text-gray-600">{(preset.intrusion_confidence * 100).toFixed(0)}%</span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <span className="font-medium text-gray-700">Require Helmet:</span>
                        <span className="ml-2 text-gray-600">{preset.ppe_require_helmet ? 'Yes' : 'No'}</span>
                      </div>
                      <div>
                        <span className="font-medium text-gray-700">Require Vest:</span>
                        <span className="ml-2 text-gray-600">{preset.ppe_require_vest ? 'Yes' : 'No'}</span>
                      </div>
                      <div>
                        <span className="font-medium text-gray-700">Confidence:</span>
                        <span className="ml-2 text-gray-600">{(preset.ppe_confidence * 100).toFixed(0)}%</span>
                      </div>
                    </>
                  )}
                  <div>
                    <span className="font-medium text-gray-700">Cooldown:</span>
                    <span className="ml-2 text-gray-600">{preset.cooldown_seconds}s</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {presets.length === 0 && !isCreating && (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">No presets found. Create your first preset!</p>
        </div>
      )}
    </div>
  )
}

function PresetForm({ formData, setFormData, onSave, onCancel, isSaving }) {
  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  return (
    <div className="space-y-4">
      {/* Basic Info */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Name *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => handleChange('name', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Mode *
          </label>
          <select
            value={formData.mode}
            onChange={(e) => handleChange('mode', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="intrusion">Intrusion</option>
            <option value="ppe">PPE</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Description
        </label>
        <input
          type="text"
          value={formData.description}
          onChange={(e) => handleChange('description', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Mode-specific settings */}
      {formData.mode === 'intrusion' ? (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Minimum Persons
            </label>
            <input
              type="number"
              min="1"
              value={formData.intrusion_min_persons}
              onChange={(e) => handleChange('intrusion_min_persons', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Confidence Threshold
            </label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={formData.intrusion_confidence}
                onChange={(e) => handleChange('intrusion_confidence', parseFloat(e.target.value))}
                className="flex-1"
              />
              <span className="text-sm font-medium text-gray-700 w-12">
                {(formData.intrusion_confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="require_helmet"
                checked={formData.ppe_require_helmet}
                onChange={(e) => handleChange('ppe_require_helmet', e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="require_helmet" className="text-sm font-medium text-gray-700">
                Require Helmet
              </label>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="require_vest"
                checked={formData.ppe_require_vest}
                onChange={(e) => handleChange('ppe_require_vest', e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="require_vest" className="text-sm font-medium text-gray-700">
                Require Vest
              </label>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Confidence Threshold
            </label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={formData.ppe_confidence}
                onChange={(e) => handleChange('ppe_confidence', parseFloat(e.target.value))}
                className="flex-1"
              />
              <span className="text-sm font-medium text-gray-700 w-12">
                {(formData.ppe_confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Alert Cooldown (seconds)
        </label>
        <input
          type="number"
          min="1"
          value={formData.cooldown_seconds}
          onChange={(e) => handleChange('cooldown_seconds', parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4 border-t border-gray-200">
        <button
          onClick={onSave}
          disabled={isSaving || !formData.name}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save size={18} />
          {isSaving ? 'Saving...' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          disabled={isSaving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
        >
          <X size={18} />
          Cancel
        </button>
      </div>
    </div>
  )
}
