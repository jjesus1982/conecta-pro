import { redirect } from 'next/navigation';

// F2-a: a tela CFO dedicada foi FUNDIDA no chat único (Hermes/FloatingChat), que já assume
// a lente CFO na rota /redesign/financeiro. Esta rota antiga passa a redirecionar pra lá,
// preservando bookmarks. O cérebro é o mesmo (cfo_service.consultar).
export default function CfoRedirect() {
  redirect('/redesign/financeiro');
}
