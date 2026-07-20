import { MapContainer, TileLayer, CircleMarker, Polyline, Popup } from "react-leaflet";
import { nodeColor, riskColor } from "../utils";

// Deliberately CircleMarker (not L.marker/default icons) for every point on
// the map — sidesteps react-leaflet's well-known default-icon-path bug
// entirely, and color-codes risk for free.

function nodeById(nodes, id) {
  return nodes.find((n) => n.id === id);
}

export default function MapView({ graph, vessels }) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];

  return (
    <MapContainer
      center={[20, 55]}
      zoom={3}
      style={{ height: "100%", width: "100%", background: "#0b1220" }}
      worldCopyJump
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      {edges.map((e, i) => {
        const from = nodeById(nodes, e.from);
        const to = nodeById(nodes, e.to);
        if (!from?.lat || !to?.lat) return null;
        return (
          <Polyline
            key={`edge-${i}`}
            positions={[[from.lat, from.lon], [to.lat, to.lon]]}
            pathOptions={{ color: "#546e7a", weight: 1.5, opacity: 0.6 }}
          />
        );
      })}

      {nodes.filter((n) => n.lat != null && n.lon != null).map((n) => {
        const isChokepoint = n.type === "chokepoint";
        const color = isChokepoint ? riskColor(n.risk || 0) : nodeColor(n.type);
        const radius = isChokepoint ? 9 + (n.risk || 0) * 6 : n.type === "refinery" ? 8 : 5;
        return (
          <CircleMarker
            key={n.id}
            center={[n.lat, n.lon]}
            radius={radius}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: isChokepoint ? 2 : 1 }}
          >
            <Popup>
              <strong>{n.id}</strong> ({n.type})
              {isChokepoint && (
                <div>
                  risk: {(n.risk ?? 0).toFixed(2)} ({n.risk_events ?? 0} events)
                </div>
              )}
              {n.grade_name && <div>{n.grade_name}{n.share_pct ? ` — ${n.share_pct}% of imports` : ""}</div>}
              {n.note && <div style={{ fontStyle: "italic", fontSize: 12 }}>{n.note}</div>}
            </Popup>
          </CircleMarker>
        );
      })}

      {(vessels || []).filter((v) => v.lat != null && v.lon != null).map((v) => (
        <CircleMarker
          key={`${v.mmsi}-${v.ts}`}
          center={[v.lat, v.lon]}
          radius={v.sanctioned ? 6 : 3.5}
          pathOptions={{
            color: v.sanctioned ? "#ff1744" : "#90a4ae",
            fillColor: v.sanctioned ? "#ff1744" : "#90a4ae",
            fillOpacity: 0.9,
            weight: v.sanctioned ? 2 : 1,
          }}
        >
          <Popup>
            <strong>{v.name || `MMSI ${v.mmsi}`}</strong>
            {v.sanctioned && <div style={{ color: "#ff1744" }}>SANCTIONED ({v.sanction_match})</div>}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
