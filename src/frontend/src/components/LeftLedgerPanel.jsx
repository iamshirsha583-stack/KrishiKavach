import React, { useState } from 'react';
import { AlertTriangle, MapPin, Users, Droplets, ArrowUpRight, Search, Filter } from 'lucide-react';

export const mockVillages = [
  {
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
    coordinates: [87.82, 22.75],
    sar_vv_change_db: -5.4,
  },
  {
    id: "V-102",
    name: "Arambagh Rural",
    block: "Arambagh",
    district: "Hooghly",
    threat_level: "HIGH",
    flood_depth_cm: 98,
    crop_loss_pct: 65,
    farmers_affected: 980,
    primary_crop: "Jute & Rice",
    pradhan_phone: "+91 98312 99403",
    coordinates: [87.78, 22.88],
    sar_vv_change_db: -3.8,
  },
  {
    id: "V-103",
    name: "Pursurah North",
    block: "Pursurah",
    district: "Hooghly",
    threat_level: "CRITICAL",
    flood_depth_cm: 160,
    crop_loss_pct: 91,
    farmers_affected: 1550,
    primary_crop: "Vegetables & Rice",
    pradhan_phone: "+91 98305 11094",
    coordinates: [87.95, 22.84],
    sar_vv_change_db: -6.1,
  },
  {
    id: "V-104",
    name: "Ghatal Border",
    block: "Ghatal",
    district: "Paschim Medinipur",
    threat_level: "MEDIUM",
    flood_depth_cm: 52,
    crop_loss_pct: 40,
    farmers_affected: 610,
    primary_crop: "Sesame & Paddy",
    pradhan_phone: "+91 94331 40592",
    coordinates: [87.62, 22.67],
    sar_vv_change_db: -2.1,
  },
  {
    id: "V-105",
    name: "Singur Lowlands",
    block: "Singur",
    district: "Hooghly",
    threat_level: "LOW",
    flood_depth_cm: 15,
    crop_loss_pct: 12,
    farmers_affected: 320,
    primary_crop: "Potato & Mustard",
    pradhan_phone: "+91 98309 88310",
    coordinates: [88.23, 22.81],
    sar_vv_change_db: -0.6,
  },
];

export default function LeftLedgerPanel({ selectedVillage, onSelectVillage }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterLevel, setFilterLevel] = useState('ALL');

  const filteredVillages = mockVillages.filter(v => {
    const matchesSearch = v.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          v.block.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterLevel === 'ALL' || v.threat_level === filterLevel;
    return matchesSearch && matchesFilter;
  });

  const getThreatBadge = (level) => {
    switch (level) {
      case 'CRITICAL':
        return 'bg-red-700 text-white font-black border-2 border-red-900 animate-pulse';
      case 'HIGH':
        return 'bg-amber-600 text-white font-extrabold border border-amber-800';
      case 'MEDIUM':
        return 'bg-yellow-400 text-black font-extrabold border border-yellow-600';
      case 'LOW':
        return 'bg-emerald-700 text-white font-bold border border-emerald-900';
      default:
        return 'bg-gray-700 text-white';
    }
  };

  return (
    <aside className="w-96 bg-white text-black border-r-4 border-blue-900 flex flex-col h-full z-10 shadow-2xl overflow-hidden shrink-0">
      {/* High Contrast Panel Header */}
      <div className="bg-blue-900 text-white p-4 border-b-4 border-yellow-500 shadow-md">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-black tracking-widest text-yellow-400 uppercase">OFFICIAL DISASTER REGISTER</span>
          <span className="text-xs bg-red-600 text-white font-bold px-2 py-0.5 rounded uppercase">LIVE SAR DATA</span>
        </div>
        <h2 className="text-2xl font-black tracking-tight uppercase text-white">Emergency Ledger</h2>
        <p className="text-xs text-blue-200 font-medium">Hooghly Basin Flood Inundation & Crop Risk Assessment</p>
      </div>

      {/* Search & Filter Bar */}
      <div className="p-3 bg-gray-100 border-b-2 border-gray-300 space-y-2">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-600" />
          <input
            type="text"
            placeholder="Search village or block..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 bg-white border-2 border-gray-400 rounded text-sm text-black font-bold placeholder-gray-500 focus:outline-none focus:border-blue-800"
          />
        </div>
        <div className="flex items-center justify-between text-xs font-bold text-gray-700">
          <span className="flex items-center gap-1">
            <Filter className="w-3.5 h-3.5" /> Threat Filter:
          </span>
          <div className="flex space-x-1">
            {['ALL', 'CRITICAL', 'HIGH'].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setFilterLevel(lvl)}
                className={`px-2 py-0.5 rounded font-black text-[11px] ${
                  filterLevel === lvl
                    ? 'bg-blue-900 text-white'
                    : 'bg-white text-gray-800 border border-gray-300 hover:bg-gray-200'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Village Cards List */}
      <div className="flex-1 overflow-y-auto divide-y-2 divide-gray-200 bg-gray-50 p-2 space-y-2">
        {filteredVillages.map((village) => {
          const isSelected = selectedVillage?.id === village.id;
          return (
            <div
              key={village.id}
              onClick={() => onSelectVillage(village)}
              className={`p-3 rounded-lg border-2 cursor-pointer transition-all shadow-sm ${
                isSelected
                  ? 'bg-blue-50 border-blue-900 shadow-md ring-2 ring-blue-800'
                  : 'bg-white border-gray-300 hover:border-blue-600 hover:shadow-md'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-bold text-gray-500 uppercase">{village.id}</span>
                    <span className="text-xs font-semibold text-blue-900 bg-blue-100 px-1.5 py-0.5 rounded">
                      {village.district}
                    </span>
                  </div>
                  <h3 className="text-lg font-black text-black leading-snug flex items-center gap-1">
                    {village.name}
                    <ArrowUpRight className="w-4 h-4 text-blue-900" />
                  </h3>
                  <p className="text-xs font-bold text-gray-700">Block: {village.block}</p>
                </div>
                <span className={`px-2.5 py-1 rounded text-xs tracking-wider uppercase font-black ${getThreatBadge(village.threat_level)}`}>
                  {village.threat_level}
                </span>
              </div>

              {/* Metric Indicators */}
              <div className="grid grid-cols-3 gap-1 pt-2 border-t border-gray-200 text-xs">
                <div className="bg-red-50 p-1.5 rounded border border-red-200">
                  <div className="text-[10px] uppercase font-bold text-red-800 flex items-center gap-0.5">
                    <Droplets className="w-3 h-3 text-red-600" /> Flood Depth
                  </div>
                  <div className="text-sm font-black text-red-950">{village.flood_depth_cm} cm</div>
                </div>

                <div className="bg-amber-50 p-1.5 rounded border border-amber-200">
                  <div className="text-[10px] uppercase font-bold text-amber-900 flex items-center gap-0.5">
                    <AlertTriangle className="w-3 h-3 text-amber-600" /> Crop Loss
                  </div>
                  <div className="text-sm font-black text-amber-950">{village.crop_loss_pct}%</div>
                </div>

                <div className="bg-blue-50 p-1.5 rounded border border-blue-200">
                  <div className="text-[10px] uppercase font-bold text-blue-900 flex items-center gap-0.5">
                    <Users className="w-3 h-3 text-blue-700" /> Farmers
                  </div>
                  <div className="text-sm font-black text-blue-950">{village.farmers_affected}</div>
                </div>
              </div>

              <div className="mt-2 text-[11px] font-semibold text-gray-600 flex justify-between items-center">
                <span>Crop: <strong className="text-black">{village.primary_crop}</strong></span>
                <span className="text-blue-900 font-bold">SAR Δ: {village.sar_vv_change_db} dB</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Summary */}
      <div className="bg-blue-950 text-white p-3 border-t-4 border-yellow-500 text-xs font-bold flex justify-between items-center">
        <span>TOTAL MONITORED: <strong className="text-yellow-400 font-black">{mockVillages.length} VILLAGES</strong></span>
        <span className="bg-red-600 px-2 py-0.5 rounded text-white font-black text-[11px]">2 CRITICAL ALERTS</span>
      </div>
    </aside>
  );
}
