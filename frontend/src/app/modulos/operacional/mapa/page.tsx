import { redirect } from 'next/navigation';

// Unificado 2026-07-09: "Mapa ao Vivo" e "Cobertura ao Vivo" liam os MESMOS dados
// (useCoverageReport + usePosts). Mantida a Cobertura (tabela completa por posto).
export default function MapaRedirect() {
  redirect('/modulos/operacional/cobertura');
}
