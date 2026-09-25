import React, { useState, useRef } from 'react';
import { Send, Volume2, Play, Pause, PhoneCall, CheckCircle, ShieldAlert, Sparkles, MessageSquare } from 'lucide-react';

export default function RightDispatchPanel({ selectedVillage }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isDispatched, setIsDispatched] = useState(false);
  const [dispatchLoading, setDispatchLoading] = useState(false);
  const audioRef = useRef(null);

  const village = selectedVillage || {
    id: "V-101",
    name: "Khanakul-I",
    block: "Khanakul",
    district: "Hooghly",
    threat_level: "CRITICAL",
    flood_depth_cm: 145,
    crop_loss_pct: 82,
    farmers_affected: 1240,
    primary_crop: "Aman Paddy",
    pradhan_phone: "+91 98310 74821",
  };

  const geminiBengaliMessage = `জরুরি বন্যা সতর্কতা (EMERGENCY ALERT):
হুগলি নদী অববাহিকায় ${village.name} গ্রামে বাঁধ ভাঙার কারণে পরবর্তী ২৪ ঘণ্টায় ${village.flood_depth_cm} সেমি প্লাবনের আশঙ্কা।
অবিলম্বে নিচু এলাকার ${village.primary_crop} ফসল কেটে নিন এবং গবাদি পশু উঁচুতে নিয়ে যান।
জরুরি সহায়তার জন্য ডায়াল করুন ১০৭।`;

  const toggleAudioPlay = () => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play().catch(() => {
          // Synthetic audio tone fallback if audio file is not present
          const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          const osc = audioCtx.createOscillator();
          const gain = audioCtx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(440, audioCtx.currentTime);
          gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
          osc.connect(gain);
          gain.connect(audioCtx.destination);
          osc.start();
          setTimeout(() => {
            osc.stop();
            setIsPlaying(false);
          }, 3000);
        });
        setIsPlaying(true);
      }
    }
  };

  const handleDispatch = () => {
    setDispatchLoading(true);
    setTimeout(() => {
      setDispatchLoading(false);
      setIsDispatched(true);
      setTimeout(() => setIsDispatched(false), 5000);
    }, 1200);
  };

  return (
    <aside className="w-[400px] bg-white text-black border-l-4 border-blue-900 flex flex-col h-full z-10 shadow-2xl overflow-y-auto shrink-0 p-4 space-y-4">
      {/* High-Contrast Section Header */}
      <div className="bg-blue-900 text-white p-3.5 rounded-xl border-b-4 border-yellow-500 shadow-md">
        <div className="flex items-center justify-between text-xs font-black uppercase text-yellow-400 mb-1">
          <span className="flex items-center gap-1">
            <Sparkles className="w-4 h-4 text-yellow-400" /> GEMINI & ELEVENLABS GATEWAY
          </span>
          <span className="bg-green-600 text-white px-2 py-0.5 rounded text-[10px]">VERIFIED</span>
        </div>
        <h2 className="text-xl font-black uppercase tracking-tight text-white">Dispatch Confirmation</h2>
        <p className="text-xs text-blue-200 font-medium">Multilingual Telephony & IVR Alert Engine</p>
      </div>

      {/* Target Village Summary Card */}
      <div className="bg-blue-50 border-2 border-blue-900 rounded-xl p-3 shadow-sm text-xs font-bold text-black space-y-1">
        <div className="flex justify-between items-center text-blue-900 border-b border-blue-200 pb-1">
          <span className="uppercase font-black">Target Location:</span>
          <span className="bg-red-700 text-white px-2 py-0.5 rounded font-black uppercase text-[10px]">
            {village.threat_level} THREAT
          </span>
        </div>
        <div className="text-base font-black text-blue-950 flex items-center justify-between">
          <span>{village.name} ({village.block})</span>
          <span className="text-xs text-gray-600 font-bold">{village.district}</span>
        </div>
        <div className="flex justify-between items-center pt-1 text-gray-800">
          <span>Pradhan Contact: <strong className="text-black font-black">{village.pradhan_phone}</strong></span>
          <span className="text-red-700 font-black">{village.farmers_affected} Farmers</span>
        </div>
      </div>

      {/* Feature Phone Mockup for Gemini Bengali Text */}
      <div className="space-y-1">
        <div className="flex justify-between items-center px-1 text-xs font-black text-gray-800 uppercase">
          <span className="flex items-center gap-1">
            <MessageSquare className="w-3.5 h-3.5 text-blue-900" /> Gemini Bengali SMS Mockup
          </span>
          <span className="text-[10px] bg-yellow-400 text-black px-1.5 py-0.5 rounded font-extrabold">FEATURE PHONE DISPLAY</span>
        </div>

        <div className="bg-zinc-900 rounded-3xl p-4 border-4 border-zinc-700 shadow-2xl text-emerald-400 font-mono flex flex-col items-center">
          {/* Phone Speaker Notch */}
          <div className="w-12 h-1.5 bg-zinc-700 rounded-full mb-3"></div>

          {/* Screen */}
          <div className="w-full bg-emerald-950/90 border-2 border-emerald-500 rounded-lg p-3 text-emerald-300 text-xs font-mono space-y-2 shadow-inner">
            <div className="flex justify-between items-center text-[10px] text-emerald-400 border-b border-emerald-800/80 pb-1">
              <span>📶 4G BSNL</span>
              <span>🔋 98%</span>
              <span className="font-bold">10:42 AM</span>
            </div>
            <div className="text-[10px] text-emerald-400 font-bold">
              TO: {village.pradhan_phone} ({village.name})
            </div>
            <div className="bg-black/40 p-2 rounded border border-emerald-700/60 leading-relaxed text-[11px] text-emerald-200 font-semibold max-h-36 overflow-y-auto">
              {geminiBengaliMessage}
            </div>
            <div className="flex justify-between text-[10px] text-emerald-400 font-bold pt-1 border-t border-emerald-800/80">
              <span>[ Options ]</span>
              <span>[ Send ]</span>
            </div>
          </div>

          {/* Keypad simulation */}
          <div className="w-full mt-3 space-y-1.5 text-[10px] font-sans">
            <div className="flex justify-between px-4 text-zinc-400 font-bold">
              <span className="bg-zinc-800 px-2 py-0.5 rounded border border-zinc-600">--</span>
              <span className="bg-zinc-800 px-2 py-0.5 rounded border border-zinc-600">OK</span>
              <span className="bg-zinc-800 px-2 py-0.5 rounded border border-zinc-600">--</span>
            </div>
            <div className="grid grid-cols-2 gap-2 px-2">
              <button className="bg-emerald-800 text-white font-black py-1 rounded border border-emerald-600 flex items-center justify-center gap-1">
                <PhoneCall className="w-3 h-3" /> CALL
              </button>
              <button className="bg-red-800 text-white font-black py-1 rounded border border-red-600">
                END
              </button>
            </div>
            <div className="grid grid-cols-3 gap-1 px-4 text-center text-zinc-300 font-bold text-[9px] pt-1">
              {['1', '2 ABC', '3 DEF', '4 GHI', '5 JKL', '6 MNO', '7 PQRS', '8 TUV', '9 WXYZ', '*', '0 +', '#'].map((k) => (
                <div key={k} className="bg-zinc-800/80 py-1 rounded border border-zinc-700 hover:bg-zinc-700">
                  {k}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ElevenLabs Voice Audio Player */}
      <div className="bg-gray-100 border-2 border-gray-300 rounded-xl p-3 space-y-2">
        <div className="flex justify-between items-center text-xs font-black text-black uppercase">
          <span className="flex items-center gap-1">
            <Volume2 className="w-4 h-4 text-blue-900" /> ElevenLabs Voice Audio Prompt
          </span>
          <span className="text-[10px] bg-blue-900 text-white px-2 py-0.5 rounded font-bold">BENGALINI_V2</span>
        </div>

        <audio ref={audioRef} src="/alert.mp3" onEnded={() => setIsPlaying(false)} />

        <div className="bg-white border-2 border-blue-900 rounded-lg p-3 flex items-center space-x-3 shadow-inner">
          <button
            onClick={toggleAudioPlay}
            className="w-10 h-10 rounded-full bg-blue-900 hover:bg-blue-800 text-white font-black flex items-center justify-center shrink-0 shadow-md transition"
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
          </button>

          <div className="flex-1 space-y-1">
            <div className="flex justify-between text-[11px] font-bold text-gray-800">
              <span>{isPlaying ? "Playing IVR Broadcast..." : "ElevenLabs Voice Stream"}</span>
              <span className="text-blue-900 font-mono">00:14 / 00:28</span>
            </div>

            {/* Audio Waveform visualizer simulation */}
            <div className="flex items-center space-x-1 h-6">
              {[40, 70, 30, 90, 60, 100, 50, 80, 40, 90, 70, 30, 85, 60, 95, 40, 75, 50].map((h, i) => (
                <div
                  key={i}
                  style={{ height: isPlaying ? `${Math.max(15, (h * Math.random()).toFixed(0))}%` : '25%' }}
                  className={`flex-1 rounded-full transition-all duration-150 ${
                    isPlaying ? 'bg-blue-800' : 'bg-gray-400'
                  }`}
                ></div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Notification Toast */}
      {isDispatched && (
        <div className="bg-emerald-700 text-white p-3 rounded-xl border-2 border-emerald-900 shadow-xl flex items-center space-x-3 animate-bounce">
          <CheckCircle className="w-6 h-6 shrink-0" />
          <div className="text-xs font-bold">
            <div className="font-black text-sm uppercase">DISPATCH TRANSMITTED!</div>
            <div>SMS sent via Twilio to {village.pradhan_phone} & IVR call queued via ElevenLabs.</div>
          </div>
        </div>
      )}

      {/* Dispatch Trigger Button */}
      <button
        onClick={handleDispatch}
        disabled={dispatchLoading}
        className="w-full bg-red-700 hover:bg-red-800 active:bg-red-900 text-white font-black text-sm py-4 px-4 rounded-xl shadow-2xl border-4 border-red-900 uppercase tracking-wide flex items-center justify-center space-x-2 transition transform hover:-translate-y-0.5"
      >
        {dispatchLoading ? (
          <div className="flex items-center space-x-2">
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
            <span>TRANSMITTING BROADCAST...</span>
          </div>
        ) : (
          <>
            <Send className="w-5 h-5 stroke-[2.5]" />
            <span>TRANSMIT SMS + VOICE BROADCAST</span>
          </>
        )}
      </button>
    </aside>
  );
}
