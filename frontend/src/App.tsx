import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { Layout } from './components/layout/Layout';
import { Login } from './pages/Login';
import { AssistantChat } from './pages/AssistantChat';
import { Dashboard } from './pages/Dashboard';
import { Customers } from './pages/Customers';
import { Invoices } from './pages/Invoices';
import { Reminders } from './pages/Reminders';
import { Commitments } from './pages/Commitments';
import { Agents } from './pages/Agents';
import { AudioStudio } from './pages/AudioStudio';
import { Settings } from './pages/Settings';

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />

          {/* Protected App Routes */}
          <Route element={<Layout />}>
            <Route path="/" element={<AssistantChat />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/invoices" element={<Invoices />} />
            <Route path="/reminders" element={<Reminders />} />
            <Route path="/commitments" element={<Commitments />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/audio" element={<AudioStudio />} />
            <Route path="/settings" element={<Settings />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
