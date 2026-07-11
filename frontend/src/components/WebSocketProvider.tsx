'use client';
// Provides WebSocket context for real-time alerts in the operacional module

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

export interface WebSocketAlert {
  id: string;
  title: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
  timestamp: string;
  read: boolean;
}

interface WebSocketContextValue {
  alerts: WebSocketAlert[];
  unreadCount: number;
  markAllRead: () => void;
  isConnected: boolean;
}

interface WebSocketProviderProps {
  children: React.ReactNode;
  token: string | null;
  apiUrl: string;
}

const WebSocketCtx = createContext<WebSocketContextValue>({
  alerts: [],
  unreadCount: 0,
  markAllRead: () => {},
  isConnected: false,
});

const MAX_ALERTS = 20;
const MAX_BACKOFF_MS = 30_000;

export function WebSocketProvider({ children, token, apiUrl }: WebSocketProviderProps) {
  const [alerts, setAlerts] = useState<WebSocketAlert[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef<number>(1_000);
  // Track whether the current connection attempt should be aborted (token changed / unmount)
  const cancelledRef = useRef<boolean>(false);

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const closeWs = (ws: WebSocket) => {
    // Prevent any further events from being processed
    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close(1000, 'cleanup');
    }
  };

  const connect = useCallback(
    (currentToken: string, wsUrl: string) => {
      if (cancelledRef.current) return;

      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl);
      } catch {
        // Invalid URL or browser restriction — schedule retry
        reconnectTimerRef.current = setTimeout(() => {
          backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
          connect(currentToken, wsUrl);
        }, backoffRef.current);
        return;
      }

      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelledRef.current) {
          closeWs(ws);
          return;
        }
        setIsConnected(true);
        backoffRef.current = 1_000; // reset backoff on successful connection
      };

      ws.onmessage = (event: MessageEvent) => {
        if (cancelledRef.current) return;
        try {
          const msg = JSON.parse(event.data as string);
          if (msg.type === 'alert' && msg.data) {
            const { id, title, message, severity, timestamp } = msg.data as {
              id: string;
              title: string;
              message: string;
              severity: 'info' | 'warning' | 'critical';
              timestamp: string;
            };
            const newAlert: WebSocketAlert = {
              id: id ?? String(Date.now()),
              title: title ?? '',
              message: message ?? '',
              severity: severity ?? 'info',
              timestamp: timestamp ?? new Date().toISOString(),
              read: false,
            };
            setAlerts((prev) => [newAlert, ...prev].slice(0, MAX_ALERTS));
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        // onerror is always followed by onclose; let onclose handle reconnect
      };

      ws.onclose = (event: CloseEvent) => {
        setIsConnected(false);
        if (cancelledRef.current) return;
        // 1000 = normal closure — do not reconnect
        if (event.code === 1000) return;
        reconnectTimerRef.current = setTimeout(() => {
          backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
          connect(currentToken, wsUrl);
        }, backoffRef.current);
      };
    },
    [],
  );

  useEffect(() => {
    // Tear down previous connection when token changes
    cancelledRef.current = true;
    clearReconnectTimer();
    if (wsRef.current) {
      closeWs(wsRef.current);
      wsRef.current = null;
    }
    setIsConnected(false);

    if (!token) return;

    // Start fresh
    cancelledRef.current = false;
    backoffRef.current = 1_000;

    // Conectar direto o WebSocket — sem "health check" HTTP: GET/HEAD numa rota
    // WS sempre responde 404 e só polui o console. O connect() já faz retry com
    // backoff exponencial (1s → 2s → 4s … máx 30s) e reseta ao conectar.
    const wsUrl =
      apiUrl.replace(/^http/, 'ws') +
      '/api/v1/operacional/comunicacao/ws/operacional/alertas?token=' +
      token;
    connect(token, wsUrl);

    return () => {
      cancelledRef.current = true;
      clearReconnectTimer();
      if (wsRef.current) {
        closeWs(wsRef.current);
        wsRef.current = null;
      }
      setIsConnected(false);
    };
  }, [token, apiUrl, connect]);

  const markAllRead = useCallback(() => {
    setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
  }, []);

  const unreadCount = alerts.filter((a) => !a.read).length;

  return (
    <WebSocketCtx.Provider value={{ alerts, unreadCount, markAllRead, isConnected }}>
      {children}
    </WebSocketCtx.Provider>
  );
}

export const useWebSocketContext = () => useContext(WebSocketCtx);
