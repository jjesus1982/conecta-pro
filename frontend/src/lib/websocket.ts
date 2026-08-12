/**
 * WebSocket Client para Comunicacao em Tempo Real
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

type MessageHandler = (data: unknown) => void;
type ConnectionHandler = () => void;

interface WebSocketMessage {
  type: string;
  data: unknown;
  timestamp: string;
}

interface WebSocketConfig {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
  debug?: boolean;
}

class WebSocketClient {
  private ws: WebSocket | null = null;
  private config: Required<WebSocketConfig>;
  private reconnectAttempts = 0;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private messageHandlers: Map<string, Set<MessageHandler>> = new Map();
  private connectionHandlers: Set<ConnectionHandler> = new Set();
  private disconnectionHandlers: Set<ConnectionHandler> = new Set();
  private isConnecting = false;
  private shouldReconnect = true;

  constructor(config: WebSocketConfig) {
    this.config = {
      reconnectInterval: 5000,
      maxReconnectAttempts: 10,
      heartbeatInterval: 30000,
      debug: false,
      ...config,
    };
  }

  private log(...args: unknown[]) {
    // Logging silencioso em produção - usar config.debug para ativar logs
    void args;
  }

  /**
   * Conecta ao servidor WebSocket
   */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.log('Ja conectado');
        resolve();
        return;
      }

      if (this.isConnecting) {
        this.log('Conexao em andamento');
        return;
      }

      this.isConnecting = true;
      this.shouldReconnect = true;

      try {
        // Adiciona token de autenticacao na URL
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
        const url = token ? `${this.config.url}?token=${token}` : this.config.url;

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          this.log('Conectado');
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          this.startHeartbeat();
          this.connectionHandlers.forEach((handler) => handler());
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            this.log('Mensagem recebida:', message.type);
            this.handleMessage(message);
          } catch (error) {
            this.log('Erro ao parsear mensagem:', error);
          }
        };

        this.ws.onerror = (error) => {
          this.log('Erro:', error);
          this.isConnecting = false;
        };

        this.ws.onclose = (event) => {
          this.log('Desconectado:', event.code, event.reason);
          this.isConnecting = false;
          this.stopHeartbeat();
          this.disconnectionHandlers.forEach((handler) => handler());

          if (this.shouldReconnect && this.reconnectAttempts < this.config.maxReconnectAttempts) {
            this.scheduleReconnect();
          }
        };
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  /**
   * Desconecta do servidor
   */
  disconnect() {
    this.shouldReconnect = false;
    this.stopHeartbeat();

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.close(1000, 'Desconexao manual');
      this.ws = null;
    }

    this.log('Desconectado manualmente');
  }

  /**
   * Agenda reconexao
   */
  private scheduleReconnect() {
    if (this.reconnectTimeout) {
      return;
    }

    this.reconnectAttempts++;
    const delay = this.config.reconnectInterval * Math.min(this.reconnectAttempts, 5);

    this.log(`Reconectando em ${delay}ms (tentativa ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect().catch(() => {
        // Erro ja logado
      });
    }, delay);
  }

  /**
   * Inicia heartbeat
   */
  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping', data: {} });
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * Para heartbeat
   */
  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Envia mensagem
   */
  send(message: { type: string; data: unknown }) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      this.log('Nao conectado, mensagem nao enviada');
      return false;
    }

    try {
      this.ws.send(
        JSON.stringify({
          ...message,
          timestamp: new Date().toISOString(),
        })
      );
      this.log('Mensagem enviada:', message.type);
      return true;
    } catch (error) {
      this.log('Erro ao enviar mensagem:', error);
      return false;
    }
  }

  /**
   * Processa mensagem recebida
   */
  private handleMessage(message: WebSocketMessage) {
    // Pong do heartbeat
    if (message.type === 'pong') {
      return;
    }

    // Notifica handlers registrados
    const handlers = this.messageHandlers.get(message.type);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(message.data);
        } catch (error) {
          this.log('Erro no handler:', error);
        }
      });
    }

    // Handler generico para todos os tipos
    const allHandlers = this.messageHandlers.get('*');
    if (allHandlers) {
      allHandlers.forEach((handler) => {
        try {
          handler(message);
        } catch (error) {
          this.log('Erro no handler generico:', error);
        }
      });
    }
  }

  /**
   * Registra handler para tipo de mensagem
   */
  on(type: string, handler: MessageHandler): () => void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, new Set());
    }
    this.messageHandlers.get(type)!.add(handler);

    // Retorna funcao para remover handler
    return () => {
      this.messageHandlers.get(type)?.delete(handler);
    };
  }

  /**
   * Remove handler
   */
  off(type: string, handler: MessageHandler) {
    this.messageHandlers.get(type)?.delete(handler);
  }

  /**
   * Handler para conexao estabelecida
   */
  onConnect(handler: ConnectionHandler): () => void {
    this.connectionHandlers.add(handler);
    return () => this.connectionHandlers.delete(handler);
  }

  /**
   * Handler para desconexao
   */
  onDisconnect(handler: ConnectionHandler): () => void {
    this.disconnectionHandlers.add(handler);
    return () => this.disconnectionHandlers.delete(handler);
  }

  /**
   * Verifica se esta conectado
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Estado da conexao
   */
  get state(): string {
    if (!this.ws) return 'CLOSED';
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'CONNECTING';
      case WebSocket.OPEN:
        return 'OPEN';
      case WebSocket.CLOSING:
        return 'CLOSING';
      case WebSocket.CLOSED:
        return 'CLOSED';
      default:
        return 'UNKNOWN';
    }
  }
}

// =============================================================================
// INSTANCIAS PRE-CONFIGURADAS
// =============================================================================

const getWebSocketURL = (): string => {
  // Derivar URL WebSocket da variável NEXT_PUBLIC_API_URL
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';
  const parsed = typeof window !== 'undefined' ? new URL(apiUrl) : null;

  if (!parsed) {
    // SSR: usar a env var convertida para ws
    return apiUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  }

  const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${parsed.host}`;
};

// Cliente para alertas operacionais
export const alertsWebSocket = new WebSocketClient({
  url: `${getWebSocketURL()}/ws/operacional/alertas`,
  debug: process.env.NODE_ENV === 'development',
});

// Cliente para notificacoes em tempo real
export const notificationsWebSocket = new WebSocketClient({
  url: `${getWebSocketURL()}/ws/operacional/notifications`,
  debug: process.env.NODE_ENV === 'development',
});

// =============================================================================
// HOOKS PARA REACT
// =============================================================================

import { useEffect, useState, useCallback } from 'react';

/**
 * Hook para usar WebSocket de alertas
 */
export function useAlertsWebSocket() {
  const [isConnected, setIsConnected] = useState(alertsWebSocket.isConnected);
  const [lastAlert, setLastAlert] = useState<unknown>(null);

  useEffect(() => {
    // Conecta se nao estiver conectado
    if (!alertsWebSocket.isConnected) {
      alertsWebSocket.connect().catch(() => {});
    }

    // Handlers
    const unsubConnect = alertsWebSocket.onConnect(() => setIsConnected(true));
    const unsubDisconnect = alertsWebSocket.onDisconnect(() => setIsConnected(false));
    const unsubAlert = alertsWebSocket.on('alert', (data) => setLastAlert(data));

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubAlert();
    };
  }, []);

  const sendAcknowledge = useCallback((alertId: string) => {
    alertsWebSocket.send({ type: 'acknowledge', data: { alert_id: alertId } });
  }, []);

  return {
    isConnected,
    lastAlert,
    sendAcknowledge,
  };
}

/**
 * Hook para usar WebSocket de notificacoes
 */
export function useNotificationsWebSocket() {
  const [isConnected, setIsConnected] = useState(notificationsWebSocket.isConnected);
  const [lastNotification, setLastNotification] = useState<unknown>(null);

  useEffect(() => {
    // Conecta se nao estiver conectado
    if (!notificationsWebSocket.isConnected) {
      notificationsWebSocket.connect().catch(() => {});
    }

    // Handlers
    const unsubConnect = notificationsWebSocket.onConnect(() => setIsConnected(true));
    const unsubDisconnect = notificationsWebSocket.onDisconnect(() => setIsConnected(false));
    const unsubNotification = notificationsWebSocket.on('notification', (data) =>
      setLastNotification(data)
    );

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubNotification();
    };
  }, []);

  const markAsRead = useCallback((notificationId: string) => {
    notificationsWebSocket.send({ type: 'mark_read', data: { notification_id: notificationId } });
  }, []);

  return {
    isConnected,
    lastNotification,
    markAsRead,
  };
}

export default WebSocketClient;
