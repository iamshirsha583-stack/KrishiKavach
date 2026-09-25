import React, { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import { MapPin, ShieldAlert, Layers } from 'lucide-react';
import { mockVillages } from './LeftLedgerPanel';

const maplibreglModule = maplibregl;

export default function MapView({ selectedVillage, onSelectVillage }) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const markers = useRef({});

  useEffect(() => {
    if (map.current) return;

    // Initialize MapLibre GL map
    map.current = new maplibreglModule.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          'osm-tiles': {
            type: 'raster',
            tiles: [
              'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
            ],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors | CropSentinel AI GEE SAR',
          },
        },
        layers: [
          {
            id: 'osm-tiles-layer',
            type: 'raster',
            source: 'osm-tiles',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [87.85, 22.80], // Hooghly Basin, West Bengal
      zoom: 9.8,
    });

    map.current.addControl(new maplibreglModule.NavigationControl(), 'top-right');
    map.current.addControl(new maplibreglModule.ScaleControl({ unit: 'metric' }), 'bottom-left');

    // Add markers for each village in emergency ledger
    mockVillages.forEach((village) => {
      const el = document.createElement('div');
      el.className = 'custom-marker cursor-pointer transform hover:scale-125 transition duration-200';
      
      const getMarkerColor = (level) => {
        if (level === 'CRITICAL') return '#b91c1c'; // Red
        if (level === 'HIGH') return '#ea580c'; // Orange
        if (level === 'MEDIUM') return '#eab308'; // Yellow
        return '#047857'; // Emerald
      };

      const color = getMarkerColor(village.threat_level);
      el.innerHTML = `
        <div style="background-color: ${color}; border: 3px solid white; box-shadow: 0 4px 10px rgba(0,0,0,0.5);" 
             class="px-2 py-1 rounded-full text-white font-black text-xs flex items-center gap-1 shadow-lg">
          <span>${village.name}</span>
          <span style="background: rgba(0,0,0,0.3);" class="px-1 rounded text-[10px]">${village.threat_level[0]}</span>
        </div>
      `;

      el.addEventListener('click', () => {
        onSelectVillage(village);
      });

      const marker = new maplibreglModule.Marker({ element: el })
        .setLngLat(village.coordinates)
        .setPopup(
          new maplibreglModule.Popup({ offset: 25 }).setHTML(`
            <div style="font-family: sans-serif; color: #000; padding: 4px;">
              <strong style="font-size: 14px; text-transform: uppercase; color: #1e3a8a;">${village.name}</strong>
              <div style="font-size: 11px; margin-top: 4px; color: #374151;">
                <strong>Threat Level:</strong> <span style="color:${color}; font-weight: bold;">${village.threat_level}</span><br/>
                <strong>Flood Depth:</strong> ${village.flood_depth_cm} cm<br/>
                <strong>Crop Loss:</strong> ${village.crop_loss_pct}%<br/>
                <strong>Farmers:</strong> ${village.farmers_affected}
              </div>
            </div>
          `)
        )
        .addTo(map.current);

      markers.current[village.id] = marker;
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  // Fly to selected village when selection changes
  useEffect(() => {
    if (map.current && selectedVillage) {
      map.current.flyTo({
        center: selectedVillage.coordinates,
        zoom: 11.5,
        essential: true,
        duration: 1500,
      });

      if (markers.current[selectedVillage.id]) {
        markers.current[selectedVillage.id].togglePopup();
      }
    }
  }, [selectedVillage]);

  return (
    <main className="flex-1 h-full relative bg-slate-200 overflow-hidden">
      {/* Map Canvas Container */}
      <div ref={mapContainer} className="w-full h-full" />

      {/* Floating Map Legend Overlay */}
      <div className="absolute top-4 left-4 bg-blue-950/90 backdrop-blur text-white p-3 rounded-lg border-2 border-yellow-500 shadow-2xl z-10 max-w-xs text-xs">
        <div className="flex items-center space-x-2 border-b border-blue-800 pb-2 mb-2">
          <ShieldAlert className="w-5 h-5 text-yellow-400" />
          <span className="font-black tracking-wide uppercase text-yellow-400">SAR Flood Overlay</span>
        </div>
        <div className="space-y-1.5 font-bold">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-red-700 border border-white"></span>
              <span>CRITICAL (&gt; 100cm flood)</span>
            </span>
            <span className="text-red-400">2 Villages</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-amber-600 border border-white"></span>
              <span>HIGH (75-100cm flood)</span>
            </span>
            <span className="text-amber-400">1 Village</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-yellow-400 border border-black"></span>
              <span>MEDIUM (30-75cm flood)</span>
            </span>
            <span className="text-yellow-300">1 Village</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-emerald-700 border border-white"></span>
              <span>LOW (&lt; 30cm flood)</span>
            </span>
            <span className="text-emerald-400">1 Village</span>
          </div>
        </div>
      </div>

      {/* Active Selection Badge */}
      {selectedVillage && (
        <div className="absolute bottom-6 left-4 bg-white text-black p-3 rounded-xl border-4 border-blue-900 shadow-2xl z-10 flex items-center space-x-3">
          <MapPin className="w-6 h-6 text-blue-900 shrink-0" />
          <div>
            <div className="text-[10px] font-black uppercase tracking-wider text-blue-900">CENTERED ON VILLAGE</div>
            <div className="text-base font-black text-black">{selectedVillage.name} ({selectedVillage.block})</div>
            <div className="text-xs font-bold text-gray-700">Coords: {selectedVillage.coordinates.join(', ')}</div>
          </div>
        </div>
      )}
    </main>
  );
}
