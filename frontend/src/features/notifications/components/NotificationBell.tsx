/**
 * NotificationBell - Componente de sino de notificações com badge
 *
 * Sprint: Módulo Operacional - Sistema de Notificações Push
 */

'use client';

;
import { Bell } from 'lucide-react';
import { useState } from 'react';
import { useNotifications } from '../hooks/useNotifications';
import { NotificationCenter } from './NotificationCenter';

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const { unreadCount } = useNotifications();

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors"
        aria-label="Notificações push do app"
        title={`Notificações push do app: ${unreadCount} não lida${unreadCount === 1 ? '' : 's'} — contagem independente da tela Notificações do Operacional`}
      >
        <Bell className="w-6 h-6" />
        {unreadCount > 0 && (
          <span className="absolute top-0 right-0 inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-red-500 rounded-full">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <NotificationCenter onClose={() => setIsOpen(false)} />
      )}
    </div>
  );
}
