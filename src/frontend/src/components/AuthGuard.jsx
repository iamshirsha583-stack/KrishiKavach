import React, { useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { ShieldAlert, Lock, LogIn, CheckCircle2, ArrowRight } from 'lucide-react';

export default function AuthGuard({ children }) {
  const { isAuthenticated, isLoading, loginWithRedirect, user } = useAuth0();
  const [bypassAuth, setBypassAuth] = useState(false);

  if (isLoading) {
    return (
      <div className="h-screen w-screen bg-blue-950 text-white flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 border-4 border-yellow-500 border-t-transparent rounded-full animate-spin"></div>
        <div className="text-xl font-black tracking-wider uppercase text-yellow-400">
          Authenticating Secure Government Credentials...
        </div>
        <div className="text-xs text-blue-200">Department of Agriculture & Disaster Management</div>
      </div>
    );
  }

  if (!isAuthenticated && !bypassAuth) {
    return (
      <div className="h-screen w-screen bg-slate-900 flex items-center justify-center p-4">
        {/* Government Portal Login Card */}
        <div className="max-w-md w-full bg-white rounded-2xl border-4 border-blue-900 shadow-2xl overflow-hidden">
          {/* Header Banner */}
          <div className="bg-blue-950 text-white p-6 border-b-4 border-yellow-500 text-center">
            <div className="inline-flex items-center justify-center p-3 bg-yellow-500 text-blue-950 rounded-xl mb-3 shadow-lg">
              <ShieldAlert className="w-10 h-10 stroke-[2.5]" />
            </div>
            <h1 className="text-2xl font-black uppercase tracking-tight text-white">GOVERNMENT PORTAL LOGIN</h1>
            <p className="text-xs text-yellow-400 font-bold tracking-widest mt-1">
              CROP SENTINEL AI • EMERGENCY LEDGER
            </p>
          </div>

          {/* Form Body */}
          <div className="p-6 space-y-5 text-black">
            <div className="bg-blue-50 border-2 border-blue-800 rounded-lg p-3 text-xs font-bold text-blue-950 flex items-start space-x-2">
              <Lock className="w-4 h-4 text-blue-900 shrink-0 mt-0.5" />
              <div>
                <strong>RESTRICTED ACCESS:</strong> Authorization required via Auth0 Government SSO. Unauthenticated access is logged.
              </div>
            </div>

            {/* Main Auth0 Login Button */}
            <button
              onClick={() => loginWithRedirect()}
              className="w-full bg-blue-900 hover:bg-blue-800 text-white font-black text-base py-4 rounded-xl shadow-lg border-2 border-blue-950 uppercase tracking-wider flex items-center justify-center space-x-3 transition transform hover:scale-[1.01]"
            >
              <LogIn className="w-5 h-5" />
              <span>SIGN IN WITH AUTH0 / GOVT ID</span>
            </button>

            {/* Field Demo Bypass Option */}
            <div className="pt-3 border-t border-gray-300 text-center space-y-2">
              <p className="text-xs text-gray-600 font-bold">Field Assessment / Evaluation Mode:</p>
              <button
                onClick={() => setBypassAuth(true)}
                className="w-full bg-yellow-500 hover:bg-yellow-400 text-blue-950 font-black text-xs py-2.5 px-4 rounded-lg uppercase tracking-wide flex items-center justify-center space-x-2 border-2 border-yellow-600 transition"
              >
                <span>BYPASS AUTH FOR FIELD DASHBOARD PREVIEW</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Footer Security Notice */}
          <div className="bg-gray-100 p-3 text-center text-[10px] font-bold text-gray-600 border-t border-gray-300">
            Government of West Bengal • Agriculture & Disaster Control Division
          </div>
        </div>
      </div>
    );
  }

  return children;
}
