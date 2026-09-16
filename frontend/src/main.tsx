import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// desktop/preload.js exposes this on Electron only; a browser tab never has `window.arp`, so
// dataset.material is simply never set and index.css's [data-material="on"] block never matches.
declare global {
  interface Window {
    arp?: { material: 'acrylic' | 'none'; platform: string; version: string }
  }
}

if (window.arp?.material === 'acrylic') {
  document.documentElement.dataset.material = 'on'
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
