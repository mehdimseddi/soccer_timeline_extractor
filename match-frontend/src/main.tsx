// src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from "@/components/theme-provider"
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import { Layout } from "@/components/layout"
import AnalysisForm from './components/AnalysisForm'
import HistoryPage from '@/components/HistoryPage'
import MatchHistoryDetail from '@/components/MatchHistoryDetail'
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Toaster } from '@/components/ui/sonner'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <Routes>
          <Route
            path="/"
            element={
              <Layout>
                <ErrorBoundary>
                  <AnalysisForm />
                </ErrorBoundary>
              </Layout>
            }
          />
          <Route
            path="/history"
            element={
              <Layout>
                <ErrorBoundary>
                  <HistoryPage />
                </ErrorBoundary>
              </Layout>
            }
          />
          <Route
            path="/history/:matchId"
            element={
              <Layout>
                <ErrorBoundary>
                  <MatchHistoryDetail />
                </ErrorBoundary>
              </Layout>
            }
          />
        </Routes>
        <Toaster />
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)