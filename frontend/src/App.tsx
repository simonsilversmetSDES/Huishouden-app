import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import FinanceLayout from './components/FinanceLayout'
import TransactionsLayout from './components/TransactionsLayout'
import AppLauncher from './pages/AppLauncher'
import Beleggingen from './pages/Beleggingen'
import Budget from './pages/Budget'
import ComingSoon from './pages/ComingSoon'
import Dashboard from './pages/Dashboard'
import Import from './pages/Import'
import Lening from './pages/Lening'
import Login from './pages/Login'
import Rules from './pages/Rules'
import Transactions from './pages/Transactions'
import Vermogen from './pages/Vermogen'
import { AppStateProvider } from './state/AppState'
import Beheer from './weekmenu/Beheer'
import RecipeDetail from './weekmenu/RecipeDetail'
import RecipeEdit from './weekmenu/RecipeEdit'
import RecipeList from './weekmenu/RecipeList'
import RecipeNew from './weekmenu/RecipeNew'
import WeekmenuLayout from './weekmenu/WeekmenuLayout'

// Layout-route: vereist login en stelt de gedeelde app-state (contexten) beschikbaar.
function AuthedArea() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-page text-ink-3">
        Laden…
      </div>
    )
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return (
    <AppStateProvider>
      <Outlet />
    </AppStateProvider>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AuthedArea />}>
            <Route path="/" element={<AppLauncher />} />
            <Route path="/lijstjes" element={<ComingSoon title="Lijstjes" />} />
            <Route path="/weekmenu" element={<WeekmenuLayout />}>
              <Route index element={<RecipeList />} />
              <Route path="recepten/nieuw" element={<RecipeNew />} />
              <Route path="recepten/:id" element={<RecipeDetail />} />
              <Route path="recepten/:id/bewerken" element={<RecipeEdit />} />
              <Route path="beheer" element={<Beheer />} />
            </Route>

            <Route path="/financien" element={<FinanceLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="transacties" element={<TransactionsLayout />}>
                <Route index element={<Transactions />} />
                <Route path="import" element={<Import />} />
                <Route path="regels" element={<Rules />} />
              </Route>
              <Route path="budget" element={<Budget />} />
              <Route path="vermogen" element={<Vermogen />} />
              <Route path="beleggingen" element={<Beleggingen />} />
              <Route path="lening" element={<Lening />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
