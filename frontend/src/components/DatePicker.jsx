export default function DatePicker({ date, onPrev, onNext, onRefresh, loading }) {
  const formatted = new Date(date + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  })

  return (
    <div className="date-picker">
      <button className="nav-btn" onClick={onPrev} disabled={loading}>◀</button>
      <span className="date-label">{formatted}</span>
      <button className="nav-btn" onClick={onNext} disabled={loading}>▶</button>
      <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
        {loading ? '…' : '↻ Refresh'}
      </button>
    </div>
  )
}
