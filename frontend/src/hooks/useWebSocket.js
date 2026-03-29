import { useEffect, useRef, useState, useCallback } from 'react';

export function useRunWebSocket(runId) {
  const [messages, setMessages] = useState([]);
  const [progress, setProgress] = useState(null);
  const [status, setStatus] = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!runId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.VITE_WS_URL || `${protocol}//${window.location.host}`;
    const ws = new WebSocket(`${host}/ws/runs/${runId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMessages((prev) => [...prev, data]);

      if (data.progress) setProgress(data.progress);
      if (data.type === 'captcha_required') setStatus('paused_captcha');
      if (data.type === 'captcha_resolved') setStatus('running');
      if (data.type === 'run_started') setStatus('running');
      if (data.type === 'run_completed') setStatus(data.status);
    };

    ws.onopen = () => {
      // Send a ping to keep connection alive
      const interval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 30000);
      ws._pingInterval = interval;
    };

    ws.onclose = () => {
      if (ws._pingInterval) clearInterval(ws._pingInterval);
    };

    return () => {
      if (ws._pingInterval) clearInterval(ws._pingInterval);
      ws.close();
    };
  }, [runId]);

  const reset = useCallback(() => {
    setMessages([]);
    setProgress(null);
    setStatus(null);
  }, []);

  return { messages, progress, status, reset };
}
