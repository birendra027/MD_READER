import { useEffect, useRef, useState, useCallback } from 'react';

// Derive WebSocket URL from the current page host so this works both
// in local dev (proxied by Vite) and in the Docker/nginx production build.
const _proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${_proto}//${window.location.host}/ws`;

export type WSStatus = 'connecting' | 'connected' | 'disconnected';

export function useMarkdownWS() {
  const [html, setHtml] = useState<string>('');
  const [status, setStatus] = useState<WSStatus>('connecting');
  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    const connect = () => {
      if (!mountedRef.current) return;
      setStatus('connecting');
      const socket = new WebSocket(WS_URL);
      wsRef.current = socket;

      socket.onopen = () => {
        if (!mountedRef.current) { socket.close(); return; }
        setStatus('connected');
        if (pendingRef.current !== null) {
          socket.send(pendingRef.current);
          pendingRef.current = null;
        }
      };

      socket.onmessage = (e) => {
        if (mountedRef.current) setHtml(e.data as string);
      };

      socket.onclose = () => {
        if (!mountedRef.current) return;
        setStatus('disconnected');
        setTimeout(connect, 3000);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, []);

  const send = useCallback((markdown: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(markdown);
      } else {
        pendingRef.current = markdown;
      }
    }, 200);
  }, []);

  return { html, status, send };
}
