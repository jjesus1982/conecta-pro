import { redirect } from 'next/navigation';

// Unificado 2026-07-09: "Agentes" duplicava a lista de colaboradores (useEmployees) com nome
// enganoso ("Agentes IA"). Mantida a versão completa em /colaboradores (detalhe + abas).
export default function AgentesRedirect() {
  redirect('/modulos/operacional/colaboradores');
}
