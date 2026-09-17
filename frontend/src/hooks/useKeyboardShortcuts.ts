'use client';

import { useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';

export interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  description: string;
  action: () => void;
  preventDefault?: boolean;
}

interface UseKeyboardShortcutsOptions {
  shortcuts: KeyboardShortcut[];
  enabled?: boolean;
}

/**
 * Hook para gerenciar atalhos de teclado globais
 * Ignora atalhos quando usuário está em inputs/textareas
 */
export function useKeyboardShortcuts({ shortcuts, enabled = true }: UseKeyboardShortcutsOptions) {
  const router = useRouter();
  const shortcutsRef = useRef(shortcuts);

  // Atualiza ref quando shortcuts mudam
  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Ignorar se estiver em input, textarea ou elemento editável
    const target = event.target as HTMLElement;
    const isInput = target.tagName === 'INPUT' ||
                   target.tagName === 'TEXTAREA' ||
                   target.isContentEditable;

    // Permitir ESC mesmo em inputs
    if (isInput && event.key !== 'Escape') {
      return;
    }

    // Procurar atalho correspondente
    const shortcut = shortcutsRef.current.find(s => {
      const keyMatch = s.key.toLowerCase() === event.key.toLowerCase();
      const ctrlMatch = s.ctrl ? event.ctrlKey || event.metaKey : !event.ctrlKey && !event.metaKey;
      const altMatch = s.alt ? event.altKey : !event.altKey;
      const shiftMatch = s.shift ? event.shiftKey : !event.shiftKey;

      return keyMatch && ctrlMatch && altMatch && shiftMatch;
    });

    if (shortcut) {
      if (shortcut.preventDefault !== false) {
        event.preventDefault();
        event.stopPropagation();
      }
      shortcut.action();
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [enabled, handleKeyDown]);

  // Não retornamos shortcutsRef.current aqui para evitar acesso a ref durante render
  // Os shortcuts são passados como parâmetro, então o caller já tem acesso
  return { shortcuts };
}

/**
 * Hook para atalhos globais do sistema
 */
export function useGlobalShortcuts({
  onSearchOpen,
  onCommandPaletteOpen,
  onSidebarToggle,
  onHelpOpen,
  onModalClose,
}: {
  onSearchOpen?: () => void;
  onCommandPaletteOpen?: () => void;
  onSidebarToggle?: () => void;
  onHelpOpen?: () => void;
  onModalClose?: () => void;
}) {
  const router = useRouter();

  const shortcuts: KeyboardShortcut[] = [
    // Busca Global
    {
      key: '/',
      description: 'Abrir busca global',
      action: () => onSearchOpen?.(),
    },
    // Command Palette
    {
      key: 'k',
      ctrl: true,
      description: 'Abrir command palette',
      action: () => onCommandPaletteOpen?.(),
    },
    // Toggle Sidebar
    {
      key: 'b',
      ctrl: true,
      description: 'Alternar sidebar',
      action: () => onSidebarToggle?.(),
    },
    // ESC - Fechar modal/dropdown
    {
      key: 'Escape',
      description: 'Fechar modal/dropdown',
      action: () => onModalClose?.(),
      preventDefault: false,
    },
    // Navegação entre módulos
    {
      key: '1',
      alt: true,
      description: 'Dashboard',
      action: () => router.push('/redesign'),
    },
    {
      key: '2',
      alt: true,
      description: 'Operacional',
      action: () => router.push('/modulos/operacional/postos'),
    },
    {
      key: '3',
      alt: true,
      description: 'Financeiro',
      action: () => router.push('/modulos/financeiro'),
    },
    {
      key: '4',
      alt: true,
      description: 'CRM',
      action: () => router.push('/modulos/crm'),
    },
    // Help Overlay
    {
      key: '?',
      shift: true,
      description: 'Mostrar atalhos disponíveis',
      action: () => onHelpOpen?.(),
    },
  ];

  useKeyboardShortcuts({ shortcuts });

  return shortcuts;
}
