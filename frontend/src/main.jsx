import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles/tailwind.css';
import App from './App.jsx';
import { ScanProvider } from './context/ScanContext.js';

createRoot(document.getElementById('root')).render(
  <ScanProvider>
    <App />
  </ScanProvider>
);
