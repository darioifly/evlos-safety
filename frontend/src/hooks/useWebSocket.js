import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * Custom hook for WebSocket connection with auto-reconnect
 * @param {string} url - WebSocket URL
 * @returns {object} - { data, status, sendMessage }
 */
export function useWebSocket(url) {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('disconnected')
  const ws = useRef(null)
  const reconnectTimeout = useRef(null)
  const reconnectAttempts = useRef(0)

  const connect = useCallback(() => {
    try {
      // Determine WebSocket URL — always same-origin as the page.
      // Built mode: FastAPI on :7002 serves both the page and /ws.
      // Vite dev mode (:5173): vite.config.js proxies /ws to :7002.
      let wsUrl
      if (url.startsWith('ws')) {
        wsUrl = url
      } else {
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        wsUrl = `${proto}//${window.location.host}${url}`
      }

      console.log('Connecting to WebSocket:', wsUrl)

      ws.current = new WebSocket(wsUrl)

      ws.current.onopen = () => {
        console.log('WebSocket connected')
        setStatus('connected')
        reconnectAttempts.current = 0
      }

      ws.current.onclose = () => {
        console.log('WebSocket disconnected')
        setStatus('disconnected')

        // Auto-reconnect with exponential backoff
        // Start with 500ms for first few attempts, then increase
        let delay
        if (reconnectAttempts.current < 3) {
          delay = 500  // Fast retry for first 3 attempts (500ms)
        } else {
          delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current - 3), 30000)
        }
        reconnectAttempts.current++

        reconnectTimeout.current = setTimeout(() => {
          console.log(`Reconnecting... (attempt ${reconnectAttempts.current})`)
          connect()
        }, delay)
      }

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error)
        console.error('WebSocket readyState:', ws.current?.readyState)
        console.error('WebSocket URL:', wsUrl)
        setStatus('error')
      }

      ws.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          setData(message)
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }

    } catch (error) {
      console.error('Error creating WebSocket:', error)
      setStatus('error')
    }
  }, [url])

  const sendMessage = useCallback((message) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(typeof message === 'string' ? message : JSON.stringify(message))
    }
  }, [])

  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current)
      }
      if (ws.current) {
        ws.current.close()
      }
    }
  }, [connect])

  return { data, status, sendMessage }
}
