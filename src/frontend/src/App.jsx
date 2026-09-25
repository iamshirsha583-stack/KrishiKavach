import React, { useState } from 'react';
import Navbar from './components/Navbar';
import LeftLedgerPanel, { mockVillages } from './components/LeftLedgerPanel';
import MapView from './components/MapView';
import RightDispatchPanel from './components/RightDispatchPanel';
import AuthGuard from './components/AuthGuard';

export default function App() {
  const [selectedVillage, setSelectedVillage] = useState(mockVillages[0]); // Default to Khanakul-I
  const [activeTab, setActiveTab] = useState('ledger');

  return (
    <AuthGuard>
      <div className="h-screen w-screen flex flex-col overflow-hidden bg-slate-900 font-sans select-none">
        {/* Top Government Header */}
        <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

        {/* Main 3-Column Layout: Left (w-96) | Center (Map) | Right (w-[400px]) */}
        <div className="flex-1 h-[calc(100vh-4rem)] w-screen flex flex-row overflow-hidden relative">
          {/* Left Panel: Emergency Ledger (w-96) */}
          <LeftLedgerPanel
            selectedVillage={selectedVillage}
            onSelectVillage={setSelectedVillage}
          />

          {/* Center Canvas: MapLibre GL (flex-1) */}
          <MapView
            selectedVillage={selectedVillage}
            onSelectVillage={setSelectedVillage}
          />

          {/* Right Panel: Dispatch Confirmation + Feature Phone + ElevenLabs Voice (w-[400px]) */}
          <RightDispatchPanel
            selectedVillage={selectedVillage}
          />
        </div>
      </div>
    </AuthGuard>
  );
}
