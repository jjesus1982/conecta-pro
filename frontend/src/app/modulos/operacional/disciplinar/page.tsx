import { redirect } from 'next/navigation';

// Unificado 2026-07-09: "Processos Disciplinares" e "Medidas Administrativas" eram a MESMA
// tela (mesmos endpoints/hooks). Mantida a versão canônica em /medidas-administrativas.
export default function DisciplinarRedirect() {
  redirect('/modulos/operacional/medidas-administrativas');
}
