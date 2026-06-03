export default function Brand() {
  return (
    <div className="flex items-center gap-3 px-5 py-5">
      <img
        src="/medclaw-logo.png"
        alt="MedClaw"
        className="h-9 w-9 rounded-lg"
      />
      <div>
        <div className="text-sm font-semibold text-dark-text">MedClaw</div>
        <div className="text-xs text-dark-text-secondary">Medical OpenClaw 2026.04.11</div>
      </div>
    </div>
  )
}
