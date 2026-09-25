import React from 'react';
import { ShieldAlert, LogOut, User, Radio, FileText } from 'lucide-react';
import { useAuth0 } from '@auth0/auth0-react';

export default function Navbar({ activeTab, setActiveTab }) {
  const { user, logout, isAuthenticated } = useAuth0();

  return (
    <header className="h-16 bg-blue-950 text-white border-b-4 border-yellow-500 px-6 flex items-center justify-between shrink-0 shadow-lg z-20">
      <div className="flex items-center space-x-4">
        <div className="bg-yellow-500 text-blue-950 p-2 rounded font-black flex items-center space-x-2 shadow">
          <ShieldAlert className="w-6 h-6 stroke-[2.5]" />
          <span className="text-lg tracking-wider uppercase font-extrabold">GOVT OF WEST BENGAL</span>
        </div>
        <div>
          <h1 className="text-xl font-black text-white tracking-wide flex items-center gap-2">
            CROP SENTINEL AI <span className="text-xs bg-red-600 text-white px-2 py-0.5 rounded-full uppercase font-bold tracking-widest animate-pulse">EMERGENCY ACTIVE</span>
          </h1>
          <p className="text-xs text-blue-200 font-medium">Department of Agriculture & Disaster Management • Hooghly Basin Division</p>
        </div>
      </div>

      <div className="flex items-center space-x-6">
        <div className="flex bg-blue-900/80 p-1 rounded-lg border border-blue-800">
          <button
            onClick={() => setActiveTab('ledger')}
            className={`px-4 py-1.5 rounded-md font-bold text-sm flex items-center space-x-2 transition ${
              activeTab === 'ledger'
                ? 'bg-yellow-500 text-blue-950 font-extrabold shadow'
                : 'text-blue-100 hover:bg-blue-800'
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Emergency Ledger</span>
          </button>
          <button
            onClick={() => setActiveTab('dispatch')}
            className={`px-4 py-1.5 rounded-md font-bold text-sm flex items-center space-x-2 transition ${
              activeTab === 'dispatch'
                ? 'bg-yellow-500 text-blue-950 font-extrabold shadow'
                : 'text-blue-100 hover:bg-blue-800'
            }`}
          >
            <Radio className="w-4 h-4" />
            <span>Dispatch Control</span>
          </button>
        </div>

        <div className="flex items-center space-x-3 bg-blue-900 border border-blue-700 px-3 py-1.5 rounded-lg">
          <div className="w-8 h-8 rounded-full bg-yellow-500 text-blue-950 font-black flex items-center justify-center text-sm shadow">
            {user?.name ? user.name.charAt(0).toUpperCase() : <User className="w-4 h-4" />}
          </div>
          <div className="text-left hidden md:block">
            <div className="text-xs font-bold text-white truncate max-w-[120px]">
              {user?.name || 'Officer In-Charge'}
            </div>
            <div className="text-[10px] text-yellow-400 font-semibold uppercase">Authorized Field Officer</div>
          </div>
          <button
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
            className="p-1.5 text-blue-200 hover:text-white hover:bg-red-700 rounded transition"
            title="Sign Out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
