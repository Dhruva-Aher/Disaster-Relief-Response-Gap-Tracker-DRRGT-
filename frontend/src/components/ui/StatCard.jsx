export function StatCard({ label, value, sublabel, tone = "warn" }) {
  return (
    <div className={`kpi ${tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
      </div>
      <div className="kpi-sublabel">{sublabel}</div>
    </div>
  );
}
