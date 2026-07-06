'use client'

import { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  FileText,
  Palmtree,
  FolderOpen,
  GraduationCap,
  Bell,
  User,
  PenLine,
  Clock,
  CalendarDays,
  Heart,
  Shield,
} from 'lucide-react'

const portalLinks = [
  { href: '/modulos/portal', label: 'Início', icon: LayoutDashboard },
  { href: '/modulos/portal/perfil', label: 'Meu Perfil', icon: User },
  { href: '/modulos/portal/contracheque', label: 'Contracheques', icon: FileText },
  { href: '/modulos/portal/ferias', label: 'Férias', icon: Palmtree },
  { href: '/modulos/portal/ponto', label: 'Ponto', icon: Clock },
  { href: '/modulos/portal/escalas', label: 'Escalas', icon: CalendarDays },
  { href: '/modulos/portal/beneficios', label: 'Benefícios', icon: Heart },
  { href: '/modulos/portal/cct', label: 'Direitos CCT', icon: Shield },
  { href: '/modulos/portal/documentos', label: 'Documentos', icon: FolderOpen },
  { href: '/modulos/portal/assinatura', label: 'Assinatura Digital', icon: PenLine },
  { href: '/modulos/portal/treinamentos', label: 'Treinamentos', icon: GraduationCap },
  { href: '/modulos/portal/notificacoes', label: 'Notificações', icon: Bell },
  { href: '/modulos/portal/dados-pessoais', label: 'Meus Dados', icon: User },
]

export default function PortalLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-4 border-b pb-4">
        <h1 className="font-display text-2xl font-semibold text-gray-900">Portal do Funcionário</h1>
      </div>
      <div className="flex flex-wrap gap-2 mb-4">
        {portalLinks.map((link) => {
          const Icon = link.icon
          const isActive = pathname === link.href
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              <Icon className="w-4 h-4" />
              {link.label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}
