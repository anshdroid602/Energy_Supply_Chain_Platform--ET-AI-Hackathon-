import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import { Crosshair, Navigation } from "lucide-react";
import { nodeColor, riskColor, riskLevel } from "../utils";

const DEFAULT_CENTER = [21, 55];
const DEFAULT_ZOOM = 4;

const pulseIcon = L.divIcon({
  className: "pulse-icon",
  html: '<span class="wave"></span><span class="core"></span>',
  iconSize: [0, 0],
});

// Smoothly frames the theatre — and pans to the active reroute when one lands.
function Framing({ points }) {
  const map = useMap();
  useEffect(() => {
    const t = setTimeout(() => map.invalidateSize(), 120);
    return () => clearTimeout(t);
  }, [map]);
  useEffect(() => {
    if (points && points.length >= 2) {
      map.flyToBounds(points, { padding: [70, 70], maxZoom: 5.2, duration: 1.2 });
    } else {
      map.flyTo(DEFAULT_CENTER, DEFAULT_ZOOM, { duration: 0.8 });
    }
  }, [map, points]);
  return null;
}

export default function OpsMap({ graph, vessels, result }) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  const maxRisk = result?.max_acceptable_risk ?? 0.5;
  const top = (result?.procurement_options || []).find((o) => o.viable) || null;
  const route = top?.safest_viable_route || top?.fastest_route || null;
  const reroutePts = (route?.path || [])
    .map((id) => byId[id])
    .filter((n) => n && n.lat != null)
    .map((n) => [n.lat, n.lon]);

  const framePts = reroutePts.length >= 2
    ? [...reroutePts, [26.6, 56.5]]        // include Hormuz for context
    : null;

  const chokepoints = nodes.filter((n) => n.type === "chokepoint");
  const sanctionedCount = (vessels || []).filter((v) => v.sanctioned).length;

  return (
    <>
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        zoomControl={false}
        attributionControl
        worldCopyJump
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; OpenStreetMap · CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
        />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png"
          opacity={0.5}
        />

        {/* supply lattice */}
        {edges.map((e, i) => {
          const a = byId[e.from], b = byId[e.to];
          if (!a?.lat || !b?.lat) return null;
          return (
            <Polyline key={`e-${i}`} positions={[[a.lat, a.lon], [b.lat, b.lon]]}
              pathOptions={{ color: "#3a4756", weight: 1, opacity: 0.4 }} />
          );
        })}

        {/* active reroute */}
        {reroutePts.length >= 2 && (
          <Polyline positions={reroutePts}
            pathOptions={{ color: "#45c4b0", weight: 3, opacity: 0.95, className: "reroute-flow" }} />
        )}

        {/* nodes */}
        {nodes.filter((n) => n.lat != null).map((n) => {
          const choke = n.type === "chokepoint";
          const color = choke ? riskColor(n.risk || 0) : nodeColor(n.type);
          const radius = choke ? 6 : n.type === "refinery" ? 6.5 : n.type === "supplier" ? 5.5 : 3.5;
          return (
            <CircleMarker key={n.id} center={[n.lat, n.lon]} radius={radius}
              pathOptions={{ color, fillColor: color, fillOpacity: 0.9, weight: choke ? 2 : 1.2 }}>
              <Popup>
                <strong>{n.id}</strong> · {n.type.replace("_", " ")}
                {choke && <div>risk {(n.risk ?? 0).toFixed(2)} ({riskLevel(n.risk || 0)}) · {n.risk_events ?? 0} events</div>}
                {n.grade_name && <div>{n.grade_name}{n.share_pct ? ` · ${n.share_pct}% of imports` : ""}</div>}
                {n.capacity_kbpd && <div>{n.capacity_kbpd.toLocaleString()} kb/d capacity</div>}
              </Popup>
            </CircleMarker>
          );
        })}

        {/* pulsing high-risk chokepoints */}
        {chokepoints.filter((c) => (c.risk || 0) >= 0.6 && c.lat != null).map((c) => (
          <Marker key={`p-${c.id}`} position={[c.lat, c.lon]} icon={pulseIcon} interactive={false} />
        ))}

        {/* live vessels */}
        {(vessels || []).filter((v) => v.lat != null).map((v) => (
          <CircleMarker key={`${v.mmsi}-${v.ts}`} center={[v.lat, v.lon]}
            radius={v.sanctioned ? 5 : 2.5}
            pathOptions={{
              color: v.sanctioned ? "#f04452" : "#7c8b9a",
              fillColor: v.sanctioned ? "#f04452" : "#7c8b9a",
              fillOpacity: v.sanctioned ? 0.95 : 0.6, weight: v.sanctioned ? 2 : 0.5,
            }}>
            <Popup>
              <strong>{v.name || `MMSI ${v.mmsi}`}</strong>
              {v.sanctioned && <div style={{ color: "#f04452" }}>SANCTIONED · {v.sanction_match} match</div>}
            </Popup>
          </CircleMarker>
        ))}

        <Framing points={framePts} />
      </MapContainer>

      <div className="map-title">
        <Crosshair size={14} />
        <span className="eyebrow">Live theatre · Arabian Sea</span>
      </div>

      <div className="map-legend">
        <div className="legend-row"><span className="legend-dot" style={{ background: "#f04452" }} /> Chokepoint risk</div>
        <div className="legend-row"><span className="legend-dot" style={{ background: "#6a9bd8" }} /> Supplier</div>
        <div className="legend-row"><span className="legend-dot" style={{ background: "#3fb27f" }} /> Refinery</div>
        <div className="legend-row"><span className="legend-line" style={{ borderColor: "#45c4b0" }} /> Recommended reroute</div>
        <div className="legend-row"><span className="legend-dot" style={{ background: "#f04452", width: 6, height: 6 }} /> {sanctionedCount} sanctioned vessels tracked</div>
      </div>

      {top && route && (
        <div className="reroute-flag">
          <div className="eyebrow" style={{ color: "var(--teal)", marginBottom: 4 }}><Navigation size={11} style={{ verticalAlign: -1 }} /> Active reroute</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{top.supplier} → {result.refinery}</div>
          <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 3 }}>
            {route.eta_days.toFixed(0)}d ETA · {(route.path_risk * 100).toFixed(0)}% route risk
          </div>
        </div>
      )}
    </>
  );
}
