'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
// Recrutamento migrado para dentro do RH (/modulos/rh/recrutamento). Redirect p/ não quebrar links antigos.
export default function RedirectRecrutamento() {
  const router = useRouter();
  useEffect(() => { router.replace('/modulos/rh/recrutamento'); }, [router]);
  return null;
}
