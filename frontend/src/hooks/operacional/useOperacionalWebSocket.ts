/**
 * useOperacionalWebSocket
 *
 * Hook especializado para WebSocket do módulo operacional.
 * Conecta ao endpoint /ws/notifications/operacional e expõe
 * eventos em tempo real para o AI Command Center.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type OperacionalEventType =
  | 'coverage_alert'
  | 'shift_reminder'
  | 'absence_alert'
  | 'field_event'
  | 'anomaly_detected'
  | 'coverage_report'
  | 'time_bank_expired'
  | 'ping'
  | 'connected';

export interface OperacionalEvent {
  type: OperacionalEventType;
  data: Record<string, unknown>;
  timestamp: string;
  room?: string;
}

export interface UseOperacionalWebSocketOptions {
  room?: string;
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onEvent?: (event: OperacionalEvent) => void;
}

export interface UseOperacionalWebSocketReturn {
  isConnected: boolean;
  lastEvent: OperacionalEvent | null;
  events: OperacionalEvent[];
  connect: () => void;
  disconnect: () => void;
  clearEvents: () => void;
}

const MAX_EVENTS = 50;

export function useOperacionalWebSocket(
  options: UseOperacionalWebSocketOptions = {}
): UseOperacionalWebSocketReturn {
  const {
    room = 'operacional',
    autoConnect = true,
    reconnectInterval = 30000,
    maxReconnectAttempts = 3,
    onEvent,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<OperacionalEvent | null>(null);
  const [events, setEvents] = useState<OperacionalEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const getWsUrl = useCallback((): string => {
    if (typeof window === 'undefined') return '';
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || window.location.origin;
    const parsed = new URL(apiUrl);
    const proto = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    // Endpoint real do backend (o caminho sem /api/v1/operacional não existe)
    return `${proto}//${parsed.host}/api/v1/operacional/ws/notifications/${room}`;
  }, [room]);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const url = getWsUrl();
      if (!url) return;

      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        setIsConnected(true);
        reconnectCountRef.current = 0;
        // Envia subscribe para a sala operacional
        wsRef.current?.send(JSON.stringify({ type: 'subscribe', room }));
      };

      wsRef.current.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;

        if (reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      wsRef.current.onerror = () => {
        // silencioso — onclose vai tratar a reconexão
      };

      wsRef.current.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(ev.data) as OperacionalEvent;
          if (parsed.type === 'ping') return; // ignora heartbeat

          setLastEvent(parsed);
          setEvents((prev) => [parsed, ...prev].slice(0, MAX_EVENTS));
          onEventRef.current?.(parsed);
        } catch {
          // ignora mensagens malformadas
        }
      };
    } catch {
      // WebSocket não disponível no ambiente
    }
  }, [getWsUrl, room, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectCountRef.current = maxReconnectAttempts; // impede reconexão automática
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
  }, [maxReconnectAttempts]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLastEvent(null);
  }, []);

  useEffect(() => {
    if (autoConnect) connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnect]);

  return { isConnected, lastEvent, events, connect, disconnect, clearEvents };
}
