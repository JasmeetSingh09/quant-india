import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import { AuthProvider } from './AuthContext.jsx'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    // Switching back to the browser tab used to refetch every query on the
    // page at once, which is what made returning to the app stutter. Data
    // with its own refresh interval still polls on that schedule.
    queries: { retry: 1, staleTime: 60_000, refetchOnWindowFocus: false }
  }
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
