import { NavLink, Outlet } from 'react-router-dom'

const SUBNAV = [
  { to: '/financien/transacties', end: true, label: 'Transacties' },
  { to: '/financien/transacties/import', end: false, label: 'Import' },
  { to: '/financien/transacties/regels', end: false, label: 'Regels' },
]

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm transition-colors pointer-coarse:py-2 ${
    isActive ? 'bg-surface text-ink shadow-sm' : 'text-ink-3 hover:text-ink-2'
  }`

export default function TransactionsLayout() {
  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-xl border border-edge bg-raised/50 p-1">
        {SUBNAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </div>
      <Outlet />
    </div>
  )
}
