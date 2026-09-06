export default function EdgeBadge({ edge, edgePct }) {
  if (!edge) return null
  return <span className="edge-badge">EDGE {edgePct}</span>
}
