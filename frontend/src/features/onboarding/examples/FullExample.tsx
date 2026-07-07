'use client';

/**
 * EXEMPLO COMPLETO DE IMPLEMENTAÇÃO DO TOUR GUIADO
 *
 * Este arquivo demonstra todas as formas de usar o sistema de onboarding.
 */

import { useState } from 'react';
import {
  OperacionalTourProvider,
  TourTrigger,
  FloatingTourTrigger,
  TourProgress,
  TourNotification,
  useTour,
  useShouldShowTour,
  useTourProgress,
} from '@/features/onboarding';

// ========================================
// EXEMPLO 1: Uso Básico com Provider
// ========================================

export function BasicExample() {
  return (
    <OperacionalTourProvider
      userRole="USUARIO"
      autoStart={true}
      showNotification={true}
    >
      <div className="p-8">
        <h1>Minha Página</h1>

        {/* Elementos com data-tour */}
        <div data-tour="dashboard-kpis" className="my-4">
          Dashboard de KPIs
        </div>

        <nav data-tour="sidebar-nav" className="my-4">
          Navegação
        </nav>

        {/* Botão para refazer tour */}
        <TourTrigger variant="button" />
      </div>
    </OperacionalTourProvider>
  );
}

// ========================================
// EXEMPLO 2: Tour com Hook Personalizado
// ========================================

export function CustomHookExample() {
  const {
    isCompleted,
    isActive,
    currentStep,
    totalSteps,
    startTour,
    resetTour,
    cancelTour,
  } = useTour('GERENTE', false); // false = não auto-start

  return (
    <div className="p-8">
      <div className="mb-4">
        <h2>Status do Tour</h2>
        <ul>
          <li>Completado: {isCompleted ? 'Sim' : 'Não'}</li>
          <li>Ativo: {isActive ? 'Sim' : 'Não'}</li>
          {isActive && (
            <li>Progresso: Step {currentStep! + 1} de {totalSteps}</li>
          )}
        </ul>
      </div>

      <div className="flex gap-2">
        <button onClick={startTour} className="px-4 py-2 bg-blue-600 text-white rounded">
          Iniciar Tour
        </button>
        <button onClick={resetTour} className="px-4 py-2 bg-gray-600 text-white rounded">
          Resetar
        </button>
        {isActive && (
          <button onClick={cancelTour} className="px-4 py-2 bg-red-600 text-white rounded">
            Cancelar
          </button>
        )}
      </div>

      {/* Elementos do tour */}
      <div data-tour="dashboard-kpis" className="mt-8 p-4 border">
        Conteúdo aqui
      </div>
    </div>
  );
}

// ========================================
// EXEMPLO 3: Detecção de Novo Usuário
// ========================================

export function NewUserDetection() {
  const shouldShow = useShouldShowTour();

  if (!shouldShow) {
    return (
      <div className="p-8">
        <p>Você já fez o tour! ✓</p>
        <TourTrigger variant="button" />
      </div>
    );
  }

  return (
    <OperacionalTourProvider autoStart={true}>
      <div className="p-8">
        <p>Bem-vindo! O tour será iniciado automaticamente.</p>
        <div data-tour="dashboard-kpis">KPIs</div>
      </div>
    </OperacionalTourProvider>
  );
}

// ========================================
// EXEMPLO 4: Tours por Perfil
// ========================================

export function RoleBasedTourExample() {
  const [selectedRole, setSelectedRole] = useState<'CEO' | 'GERENTE' | 'SUPERVISOR' | 'USUARIO'>('USUARIO');

  return (
    <div className="p-8">
      <div className="mb-4">
        <label className="block mb-2">Selecione seu perfil:</label>
        <select
          value={selectedRole}
          onChange={(e) => setSelectedRole(e.target.value as any)}
          className="px-4 py-2 border rounded"
        >
          <option value="USUARIO">Usuário</option>
          <option value="SUPERVISOR">Supervisor</option>
          <option value="GERENTE">Gerente</option>
          <option value="CEO">CEO</option>
        </select>
      </div>

      <OperacionalTourProvider
        userRole={selectedRole}
        autoStart={false}
      >
        {/* Conteúdo específico por role */}
        <div data-tour="dashboard-kpis" className="p-4 border mb-4">
          Dashboard KPIs (todos)
        </div>

        {selectedRole === 'CEO' && (
          <div data-tour="analytics-charts" className="p-4 border mb-4">
            Analytics Avançados (CEO)
          </div>
        )}

        {selectedRole === 'GERENTE' && (
          <div data-tour="team-panel" className="p-4 border mb-4">
            Gestão de Equipe (Gerente)
          </div>
        )}

        {selectedRole === 'SUPERVISOR' && (
          <div data-tour="operations-panel" className="p-4 border mb-4">
            Operações Diárias (Supervisor)
          </div>
        )}

        <TourTrigger variant="button" role={selectedRole} />
      </OperacionalTourProvider>
    </div>
  );
}

// ========================================
// EXEMPLO 5: Tracking Avançado
// ========================================

export function AdvancedTrackingExample() {
  const {
    progress,
    markStarted,
    markCompleted,
    incrementCancelCount,
  } = useTourProgress();

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Tracking do Tour</h2>

      <div className="space-y-2">
        <p>Iniciado: {progress.started ? 'Sim' : 'Não'}</p>
        {progress.startedAt && (
          <p>Data de Início: {new Date(progress.startedAt).toLocaleString()}</p>
        )}

        <p>Completado: {progress.completed ? 'Sim' : 'Não'}</p>
        {progress.completedAt && (
          <p>Data de Conclusão: {new Date(progress.completedAt).toLocaleString()}</p>
        )}

        <p>Cancelamentos: {progress.cancelCount}</p>
      </div>

      <div className="flex gap-2 mt-4">
        <button onClick={markStarted} className="px-4 py-2 bg-blue-600 text-white rounded">
          Marcar Iniciado
        </button>
        <button onClick={markCompleted} className="px-4 py-2 bg-green-600 text-white rounded">
          Marcar Completado
        </button>
        <button onClick={incrementCancelCount} className="px-4 py-2 bg-red-600 text-white rounded">
          Incrementar Cancelamentos
        </button>
      </div>
    </div>
  );
}

// ========================================
// EXEMPLO 6: Variações de Triggers
// ========================================

export function TriggerVariantsExample() {
  return (
    <div className="p-8 space-y-8">
      <div>
        <h3 className="font-bold mb-2">Variante Button</h3>
        <TourTrigger variant="button" />
      </div>

      <div>
        <h3 className="font-bold mb-2">Variante Menu Item</h3>
        <div className="bg-white border rounded-lg p-2 w-64">
          <TourTrigger variant="menu-item" />
        </div>
      </div>

      <div>
        <h3 className="font-bold mb-2">Variante Badge</h3>
        <TourTrigger variant="badge" />
      </div>

      <div>
        <h3 className="font-bold mb-2">Floating Trigger</h3>
        <FloatingTourTrigger />
      </div>
    </div>
  );
}

// ========================================
// EXEMPLO 7: Página Completa
// ========================================

export function CompletePageExample() {
  const { user } = { user: { role: 'USUARIO' } }; // Mock - substituir por useAuth()

  return (
    <OperacionalTourProvider
      userRole={user.role as any}
      autoStart={true}
      showNotification={true}
    >
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white border-b p-4">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <h1 className="text-xl font-bold">Módulo Operacional</h1>

            <div className="flex items-center gap-3">
              <div data-tour="global-search">
                <input
                  type="search"
                  placeholder="Buscar..."
                  className="px-4 py-2 border rounded"
                 aria-label="Buscar..." />
              </div>

              <div data-tour="notifications">
                <button className="relative p-2">
                  🔔
                  <span className="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full" />
                </button>
              </div>

              <div data-tour="quick-actions">
                <button className="px-4 py-2 bg-blue-600 text-white rounded">
                  + Ações
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* Sidebar */}
        <div className="flex">
          <aside className="w-64 bg-white border-r min-h-screen p-4" data-tour="sidebar-nav">
            <nav>
              <ul className="space-y-2">
                <li className="p-2 hover:bg-gray-100 rounded">Dashboard</li>
                <li className="p-2 hover:bg-gray-100 rounded">Postos</li>
                <li className="p-2 hover:bg-gray-100 rounded">Colaboradores</li>
                <li className="p-2 hover:bg-gray-100 rounded">Escalas</li>
              </ul>
            </nav>

            {/* Trigger no menu */}
            <div className="mt-8">
              <TourTrigger variant="menu-item" />
            </div>
          </aside>

          {/* Main Content */}
          <main className="flex-1 p-8">
            {/* KPIs */}
            <div data-tour="dashboard-kpis" className="mb-8">
              <h2 className="text-lg font-bold mb-4">KPIs Principais</h2>
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-white p-4 rounded-lg border">
                  <p className="font-data text-2xl font-semibold tabular-nums">42</p>
                  <p className="text-sm text-gray-600">Postos Ativos</p>
                </div>
                <div className="bg-white p-4 rounded-lg border">
                  <p className="font-data text-2xl font-semibold tabular-nums">156</p>
                  <p className="text-sm text-gray-600">Colaboradores</p>
                </div>
                <div className="bg-white p-4 rounded-lg border">
                  <p className="font-data text-2xl font-semibold tabular-nums">8</p>
                  <p className="text-sm text-gray-600">Escalas Ativas</p>
                </div>
                <div className="bg-white p-4 rounded-lg border">
                  <p className="font-data text-2xl font-semibold tabular-nums">95%</p>
                  <p className="text-sm text-gray-600">Taxa Cobertura</p>
                </div>
              </div>
            </div>

            {/* Content */}
            <div className="bg-white rounded-lg border p-6">
              <h2 className="text-lg font-bold mb-4">Conteúdo Principal</h2>
              <p className="text-gray-600">
                Este é um exemplo completo de página com tour guiado.
              </p>
            </div>
          </main>
        </div>

        {/* Progress Bar (auto) */}
        <TourProgress />

        {/* Notification (auto se não completado) */}
        <TourNotification role={user.role as any} />
      </div>
    </OperacionalTourProvider>
  );
}
