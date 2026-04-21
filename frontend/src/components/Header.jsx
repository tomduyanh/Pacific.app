export function Header({ tokensUsed, tokenBudget, metacontext, onMetacontextChange, onMetacontextBlur }) {
  const pct = Math.min(100, Math.round((tokensUsed / tokenBudget) * 100));
  const formatted = tokensUsed.toLocaleString();
  const budgetFmt = tokenBudget.toLocaleString();

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-3">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-gray-950 leading-tight">Pacific</h1>
            <span className="text-xs px-2 py-0.5 rounded border border-emerald-200 bg-emerald-50 text-emerald-700">
              MVP monitor
            </span>
          </div>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-xs text-gray-500 shrink-0">Active task:</span>
            <input
              value={metacontext}
              onChange={(e) => onMetacontextChange(e.target.value)}
              onBlur={onMetacontextBlur}
              placeholder="Describe what the user is trying to do..."
              className="text-xs text-gray-700 bg-transparent border-none outline-none min-w-0 flex-1 placeholder-gray-400"
            />
          </div>
        </div>

        <div className="text-left md:text-right flex-shrink-0">
          <div className="text-xs text-gray-500 font-medium mb-1">Payload budget</div>
          <div className="text-sm font-semibold text-gray-800">
            {formatted} / {budgetFmt} tokens
          </div>
          <div className="mt-1 h-1 w-40 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${pct > 80 ? "bg-amber-500" : "bg-emerald-600"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
