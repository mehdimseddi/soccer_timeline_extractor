import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from "@/components/theme-provider"
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import HistoryPage from '@/components/HistoryPage'
import MatchHistoryDetail from '@/components/MatchHistoryDetail'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/history/:matchId" element={<MatchHistoryDetail />} />
        </Routes>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)