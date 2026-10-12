export function StatTile({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div className="tile">
      <span className="value">{value}</span>
      <span className="label">{label}</span>
    </div>
  );
}
