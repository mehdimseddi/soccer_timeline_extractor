

import { Toaster } from '@/components/ui/sonner';
import './App.css';
import AnalysisForm from "./components/AnalysisForm";
import { Layout } from "@/components/layout"
import { ErrorBoundary } from "@/components/ErrorBoundary";

function App() {
  return (
    <>
      <Layout>
        <ErrorBoundary>
          <AnalysisForm />
        </ErrorBoundary>
      </Layout>
      <Toaster />
    </>
  )
}

export default App