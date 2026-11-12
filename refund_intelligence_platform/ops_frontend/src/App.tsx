import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { OpsLayout } from './components/OpsLayout';
import { AgentsPage } from './pages/AgentsPage';
import { AuditPage } from './pages/AuditPage';
import { CasesPage } from './pages/CasesPage';
import { CompliancePage } from './pages/CompliancePage';
import { DashboardPage } from './pages/DashboardPage';
import { EtaPage } from './pages/EtaPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { IssuerSimulatorPage } from './pages/IssuerSimulatorPage';
import { RegulatoryPage } from './pages/RegulatoryPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/operations/dashboard" replace />} />
        <Route path="/operations" element={<OpsLayout />}>
          <Route index element={<Navigate to="/operations/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="cases" element={<CasesPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="eta" element={<EtaPage />} />
          <Route path="issuer-simulator" element={<IssuerSimulatorPage />} />
          <Route path="regulatory" element={<RegulatoryPage />} />
          <Route path="compliance" element={<CompliancePage />} />
          <Route path="audit" element={<AuditPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/operations/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
