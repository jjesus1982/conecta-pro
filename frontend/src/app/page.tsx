import { redirect } from 'next/navigation';

// Cutover 2026-07-19: a raiz do domínio leva ao redesign (novo visual).
// O clássico segue acessível em /dashboard (botão "Clássico" no redesign).
export default function Home() {
  redirect('/redesign');
}
