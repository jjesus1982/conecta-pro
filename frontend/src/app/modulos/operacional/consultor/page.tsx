import { redirect } from 'next/navigation';

// Consultor clássico aposentado → Consultor IA unificado do redesign, lente presetada.
export default function Page() {
  redirect('/redesign/consultor-ia?persona=operacional');
}
