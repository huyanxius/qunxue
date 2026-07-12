import { Link, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import NewTask from './pages/NewTask'
import Workbench from './pages/Workbench'
import Report from './pages/Report'
import Concepts from './pages/Concepts'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route element={<AppShell />}>
        <Route path="/new" element={<NewTask />} />
        <Route path="/workbench" element={<Workbench />} />
        <Route path="/report" element={<Report />} />
        <Route path="/concepts" element={<Concepts />} />
      </Route>
    </Routes>
  )
}

function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="app-brand">
          <span className="seal">群学<br />致知</span>
          <span className="app-brand-name serif">第二编码者</span>
        </Link>
        <nav className="app-nav" aria-label="产品页面">
          <NavLink to="/new">建立任务</NavLink>
          <NavLink to="/workbench">编码工作台</NavLink>
          <NavLink to="/report">报告</NavLink>
          <NavLink to="/concepts">概念查询</NavLink>
        </nav>
        <span className="app-demo-tag">演示环境 · 材料为虚构</span>
      </header>
      <Outlet />
    </div>
  )
}
