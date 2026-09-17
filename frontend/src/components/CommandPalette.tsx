'use client';

import { Search, FileText, Users, Calendar, AlertTriangle, Download, X } from 'lucide-react';
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useTelasDoRedesign, titulo as tituloModulo, casaTermo } from './redesign/BuscaTelas';
;

interface Command {
  id: string;
  title: string;
  description?: string;
  icon: React.ReactNode;
  action: () => void;
  category: 'navigation' | 'action' | 'search';
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const comandosBase: Command[] = useMemo(() => [
    // Navegação
    {
      id: 'novo-posto',
      title: 'Novo Posto',
      description: 'Cadastrar novo posto de trabalho',
      icon: <FileText className="w-4 h-4" />,
      category: 'navigation',
      action: () => {
        router.push('/redesign/operacional?t=postos');
        onClose();
      },
    },
    {
      id: 'novo-colaborador',
      title: 'Novo Colaborador',
      description: 'Cadastrar novo colaborador',
      icon: <Users className="w-4 h-4" />,
      category: 'navigation',
      action: () => {
        router.push('/modulos/dp/funcionarios?novo=1');
        onClose();
      },
    },
    {
      id: 'nova-escala',
      title: 'Nova Escala',
      description: 'Criar nova escala de trabalho',
      icon: <Calendar className="w-4 h-4" />,
      category: 'action',
      action: () => {
        router.push('/redesign/operacional?t=escalas');
        onClose();
      },
    },
    {
      id: 'nova-ocorrencia',
      title: 'Nova Ocorrência',
      description: 'Registrar nova ocorrência',
      icon: <AlertTriangle className="w-4 h-4" />,
      category: 'navigation',
      action: () => {
        router.push('/redesign/operacional?t=ocorrencias');
        onClose();
      },
    },
    {
      id: 'buscar-colaborador',
      title: 'Buscar Colaborador',
      description: 'Buscar colaborador por nome ou CPF',
      icon: <Search className="w-4 h-4" />,
      category: 'search',
      action: () => {
        router.push('/modulos/dp/funcionarios?search=true');
        onClose();
      },
    },
    {
      id: 'exportar-dados',
      title: 'Exportar Dados',
      description: 'Exportar dados para Excel/PDF',
      icon: <Download className="w-4 h-4" />,
      category: 'action',
      action: () => {
        // TODO: Implementar lógica de exportação
        onClose();
      },
    },
  ], [router, onClose]);

  // ── As telas do redesign entram aqui ────────────────────────────────────────
  // Origem: 17/09/2026. Eu tinha construído um SEGUNDO painel de busca no Ctrl+K e os dois
  // abriram juntos — só vi no navegador. Um atalho, um painel: as 476 telas viram comandos
  // deste, que já existe, em vez de competir com ele.
  const telas = useTelasDoRedesign();
  const comandosTela: Command[] = useMemo(
    () => telas.map((t) => ({
      id: `tela:${t.slug}:${t.id}`,
      title: t.label,
      description: tituloModulo(t.slug),
      icon: <Search className="w-4 h-4" />,
      category: 'navigation' as const,
      action: () => { router.push(`/redesign/${t.slug}?t=${t.id}`); onClose(); },
    })),
    [telas, router, onClose],
  );
  const commands = useMemo(() => [...comandosBase, ...comandosTela], [comandosBase, comandosTela]);

  // Busca fuzzy simples
  const filteredCommands = useMemo(() => {
    if (!query.trim()) return commands;

    const lowerQuery = query.toLowerCase();
    return commands.filter(cmd => {
      // `casaTermo` tolera acento e raiz: quem digita "diaria" acha "Diaristas", e "ferias"
      // acha "Férias". `includes` cru não faz nem uma coisa nem outra.
      if (casaTermo(`${cmd.title} ${cmd.description ?? ''}`, query)) return true;
      const titleMatch = cmd.title.toLowerCase().includes(lowerQuery);
      const descMatch = cmd.description?.toLowerCase().includes(lowerQuery);
      return titleMatch || descMatch;
    });
  }, [commands, query]);

  // Reset selected index quando filtros mudarem - usando queueMicrotask
  useEffect(() => {
    queueMicrotask(() => {
      setSelectedIndex(prev => prev >= filteredCommands.length ? 0 : prev);
    });
  }, [filteredCommands.length]);

  // Navegação com teclado
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev =>
          prev < filteredCommands.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : prev);
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          filteredCommands[selectedIndex].action();
        }
        break;
      case 'Escape':
        e.preventDefault();
        onClose();
        break;
    }
  }, [filteredCommands, selectedIndex, onClose]);

  // Auto-focus no input quando abrir - usando queueMicrotask para evitar setState síncrono
  useEffect(() => {
    if (isOpen) {
      queueMicrotask(() => {
        setQuery('');
        setSelectedIndex(0);
      });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const categoryLabels = {
    navigation: 'Navegação',
    action: 'Ações',
    search: 'Busca',
  };

  // Agrupar comandos por categoria
  const groupedCommands = filteredCommands.reduce((acc, cmd) => {
    return {
      ...acc,
      [cmd.category]: [...(acc[cmd.category] || []), cmd],
    };
  }, {} as Record<string, Command[]>);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-[hsl(var(--background))] rounded-lg shadow-2xl border border-[hsl(var(--border))]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header com busca */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[hsl(var(--border))]">
          <Search className="w-5 h-5 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Digite um comando ou busca..."
            className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
            autoFocus
          />
          <button
            onClick={onClose}
            className="p-1 hover:bg-accent rounded transition-colors"
            aria-label="Fechar"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Comandos */}
        <div className="max-h-[400px] overflow-y-auto">
          {Object.entries(groupedCommands).length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              Nenhum comando encontrado
            </div>
          ) : (
            Object.entries(groupedCommands).map(([category, cmds]) => (
              <div key={category}>
                <div className="px-4 py-2 text-xs font-semibold text-muted-foreground bg-muted/50">
                  {categoryLabels[category as keyof typeof categoryLabels]}
                </div>
                {cmds.map((cmd, idx) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;

                  return (
                    <button
                      key={cmd.id}
                      onClick={cmd.action}
                      onMouseEnter={() => setSelectedIndex(globalIndex)}
                      className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                        isSelected
                          ? 'bg-accent text-accent-foreground'
                          : 'hover:bg-accent/50'
                      }`}
                    >
                      <div className="flex-shrink-0 text-muted-foreground">
                        {cmd.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium">{cmd.title}</div>
                        {cmd.description && (
                          <div className="text-xs text-muted-foreground truncate">
                            {cmd.description}
                          </div>
                        )}
                      </div>
                      {isSelected && (
                        <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono bg-background border border-border rounded">
                          Enter
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer com dicas */}
        <div className="flex items-center gap-4 px-4 py-2 text-xs text-muted-foreground border-t border-[hsl(var(--border))]">
          <div className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">↑↓</kbd>
            <span>Navegar</span>
          </div>
          <div className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">Enter</kbd>
            <span>Executar</span>
          </div>
          <div className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">Esc</kbd>
            <span>Fechar</span>
          </div>
        </div>
      </div>
    </div>
  );
}
