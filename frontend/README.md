# Frontend - Person Detection System

## Overview

Modern React SPA built with Vite and TailwindCSS for monitoring person detection system.

## Structure

```
frontend/
├── src/
│   ├── main.jsx              # Entry point
│   ├── App.jsx               # Main component with navigation
│   ├── components/           # UI components
│   │   ├── CameraGrid.jsx    # Camera status grid
│   │   ├── ConfigPanel.jsx   # Detection configuration
│   │   ├── AlertLog.jsx      # Alert history table
│   │   └── Dashboard.jsx     # Metrics and charts
│   ├── hooks/                # Custom React hooks
│   │   └── useWebSocket.js   # WebSocket connection
│   └── styles/               # Styles
│       └── index.css         # TailwindCSS
├── index.html                # HTML template
├── package.json              # Dependencies
├── vite.config.js            # Vite configuration
├── tailwind.config.js        # TailwindCSS config
└── postcss.config.js         # PostCSS config
```

## Components

### App.jsx
Main application component:
- Tab navigation (Cameras, Config, Alerts, Dashboard)
- WebSocket connection status
- Global layout
- TanStack Query provider

### CameraGrid.jsx
Display camera status:
- Grid of camera cards
- Online/offline status
- Person count
- FPS indicator
- Last alert timestamp
- Real-time WebSocket updates

### ConfigPanel.jsx
Configure detection settings:
- YOLO model selection (n/s)
- Confidence slider (0.1-0.9)
- Device selection (CUDA/CPU)
- Min persons threshold
- Alert cooldown
- Batch size
- Form validation

### AlertLog.jsx
Alert history table:
- Real-time alert updates
- Filter by camera
- Export to CSV
- Timestamp, camera, persons, confidence
- Pagination info

### Dashboard.jsx
System metrics and charts:
- Stat cards (FPS, GPU, Alerts, Uptime)
- FPS history chart (Recharts)
- FPS per camera chart (Bar)
- Alerts per camera
- System information

## Custom Hooks

### useWebSocket.js
WebSocket connection manager:
- Auto-connect on mount
- Auto-reconnect with exponential backoff
- Status tracking (connected/disconnected/error)
- Message sending
- JSON parsing
- Cleanup on unmount

Usage:
```javascript
const { data, status, sendMessage } = useWebSocket('/ws')
```

## Tech Stack

### Core
- React 18.2.0 - UI library
- Vite 5.0.11 - Build tool
- TailwindCSS 3.4.1 - Styling

### State & Data
- TanStack Query 5.17.0 - Server state
- Axios 1.6.5 - HTTP client

### UI Libraries
- Recharts 2.10.3 - Charts
- Lucide React 0.303.0 - Icons
- date-fns 3.0.6 - Date formatting

## Running

### Development
```bash
# Install dependencies
npm install

# Start dev server (with HMR)
npm run dev

# Access: http://localhost:5173
```

### Build
```bash
# Create production build
npm run build

# Output: dist/  (gitignored — must be rebuilt on each clone)
```

`npm run build` is required before end-users can open the app via FastAPI on
`http://<server-ip>:7002/`. FastAPI serves `frontend/dist/` as a SPA when it
exists; otherwise `/` returns a 503 with build instructions and the API
endpoints continue to work. `npm run dev` (Vite on :5173 with HMR) is still
the developer workflow — it proxies `/api`, `/ws`, and `/static` to
`:7002`.

### Preview
```bash
# Preview production build locally
npm run preview
```

## Configuration

### vite.config.js
```javascript
server: {
  port: 5173,
  proxy: {
    '/api': 'http://localhost:8000',  // Backend API
    '/ws': {
      target: 'ws://localhost:8000',  // WebSocket
      ws: true
    }
  }
}
```

### tailwind.config.js
```javascript
content: [
  "./index.html",
  "./src/**/*.{js,jsx}"
]
```

## API Integration

All API calls use Axios with TanStack Query:

```javascript
const { data } = useQuery({
  queryKey: ['cameras'],
  queryFn: async () => {
    const res = await axios.get('/api/cameras/status')
    return res.data
  },
  refetchInterval: 5000  // Auto-refetch every 5s
})
```

Mutations for updates:
```javascript
const mutation = useMutation({
  mutationFn: (data) => axios.post('/api/detection/config', data),
  onSuccess: () => {
    queryClient.invalidateQueries(['config'])
  }
})
```

## WebSocket

Connect to `/ws` for real-time updates:

Message types:
- `initial_status` - Initial camera status
- `camera_status_update` - All cameras update
- `camera_status` - Single camera update
- `alert` - New alert
- `metrics_update` - System metrics

Example:
```javascript
useEffect(() => {
  if (wsData?.type === 'alert') {
    // Handle new alert
    setAlerts(prev => [wsData.data, ...prev])
  }
}, [wsData])
```

## Styling

### TailwindCSS
Utility-first CSS framework:
```jsx
<div className="bg-white rounded-lg shadow-md p-6">
  <h2 className="text-2xl font-bold text-gray-900">Title</h2>
</div>
```

### Responsive Design
```jsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4">
  {/* Cards */}
</div>
```

### Colors
- Primary: Blue (500-700)
- Success: Green (500-700)
- Warning: Orange (500-700)
- Error: Red (500-700)
- Gray: Neutral (50-900)

## Icons

Using Lucide React:
```jsx
import { Camera, Users, AlertCircle } from 'lucide-react'

<Camera size={24} className="text-blue-500" />
<Users size={16} />
```

## Charts

Using Recharts:
```jsx
<ResponsiveContainer width="100%" height={300}>
  <LineChart data={data}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="time" />
    <YAxis />
    <Tooltip />
    <Line dataKey="fps" stroke="#3b82f6" />
  </LineChart>
</ResponsiveContainer>
```

## Adding New Components

1. Create file in `src/components/`
2. Import in `App.jsx`
3. Add to navigation if needed
4. Style with TailwindCSS

Example:
```jsx
// src/components/NewComponent.jsx
export default function NewComponent() {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold">New Component</h2>
    </div>
  )
}
```

```jsx
// App.jsx
import NewComponent from './components/NewComponent'

{activeTab === 'new' && <NewComponent />}
```

## State Management

Using React hooks + TanStack Query:
- **Local State**: `useState`, `useEffect`
- **Server State**: TanStack Query
- **WebSocket State**: Custom hook

No Redux/MobX needed for this app.

## Performance

### Code Splitting
Vite automatically splits code for production.

### Image Optimization
Images are optimized during build.

### Bundle Size
Production build: ~500KB (gzipped)

### Optimization Tips
- Use `React.memo()` for expensive components
- Use `useCallback` for event handlers
- Lazy load components if needed
- Enable production mode for build

## Debugging

### React DevTools
Install browser extension for component inspection.

### Vite Inspector
Built into dev server - see errors in browser console.

### Network Tab
Monitor API calls and WebSocket messages.

### Console Logging
```javascript
console.log('WebSocket data:', wsData)
```

## Building for Production

```bash
# Build
npm run build

# Output files in dist/
# - index.html
# - assets/
#   - index-[hash].js
#   - index-[hash].css

# These files are served by FastAPI backend
```

## Environment Variables

Vite uses `import.meta.env`:
```javascript
const apiUrl = import.meta.env.VITE_API_URL || '/api'
```

Create `.env.local`:
```
VITE_API_URL=http://localhost:8000/api
```

## Testing (Future)

Planned for v1.1+:
```bash
# Unit tests
npm run test

# Component tests
npm run test:component

# E2E tests
npm run test:e2e
```

## Troubleshooting

### Port 5173 in use
Change port in `vite.config.js`:
```javascript
server: { port: 5174 }
```

### API calls fail
Check proxy configuration in `vite.config.js`.

### Build fails
```bash
rm -rf node_modules
npm install
npm run build
```

### WebSocket not connecting
1. Check backend is running
2. Verify WebSocket endpoint
3. Check browser console for errors

---

For more information, see [../README.md](../README.md)
