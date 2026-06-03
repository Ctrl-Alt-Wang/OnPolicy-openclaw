import { useState } from 'react'

export default function ThinkingBlock({ toolCalls = [], reasonings = [] }) {
  const [open, setOpen] = useState(false)
  const hasReasoning = reasonings.length > 0
  const toolStarts = toolCalls.filter(tc => tc.type === 'tool_start')

  if (!hasReasoning && toolCalls.length === 0) return null

  return (
    <div className="mt-2 pt-2 border-t border-gray-200">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600
                   transition-colors w-full text-left"
      >
        <span className={`transition-transform ${open ? 'rotate-90' : ''}`}>▸</span>
        <span>思考过程</span>
        {toolStarts.length > 0 && (
          <span className="text-emerald-600">· {toolStarts.length} 次工具调用</span>
        )}
        {hasReasoning && <span className="text-violet-600">· 推理</span>}
      </button>

      {open && (
        <div className="mt-2 space-y-2 text-xs">
          {reasonings.map((text, i) => (
            <div key={`r-${i}`} className="pl-3 pr-3 py-2 rounded-lg bg-violet-50 border border-violet-200">
              <div className="flex items-center gap-1 text-violet-600 font-medium mb-1">
                <span>💭</span><span>推理</span>
              </div>
              <p className="text-gray-700 leading-relaxed whitespace-pre-wrap break-words">{text}</p>
            </div>
          ))}

          {toolCalls.map((tc, i) => {
            if (tc.type === 'tool_start') {
              return (
                <div key={`ts-${i}`} className="pl-3 pr-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200">
                  <div className="flex items-center gap-1 text-emerald-700 font-medium mb-1">
                    <span>🔧</span><span>{tc.tool_name}</span>
                    <span className="text-emerald-400 text-[10px]">调用中</span>
                  </div>
                  {tc.preview && <p className="text-gray-500">{tc.preview}</p>}
                  {tc.args && (
                    <p className="text-gray-400 text-[10px] mt-0.5 font-mono truncate">
                      {typeof tc.args === 'string' ? tc.args : JSON.stringify(tc.args)}
                    </p>
                  )}
                </div>
              )
            }
            if (tc.type === 'tool_complete') {
              const isError = tc.error
              return (
                <div key={`tc-${i}`} className={`pl-3 pr-3 py-2 rounded-lg border ${isError ? 'bg-red-50 border-red-200' : 'bg-emerald-50/50 border-emerald-200'}`}>
                  <div className="flex items-center gap-1 font-medium mb-1">
                    <span>{isError ? '❌' : '✅'}</span>
                    <span className={isError ? 'text-red-600' : 'text-emerald-700'}>{tc.tool_name}</span>
                    <span className="text-gray-400 text-[10px]">{isError ? '失败' : '完成'}</span>
                  </div>
                  {tc.preview && !isError && <p className="text-gray-500">{tc.preview}</p>}
                  {tc.result && !isError && (
                    <p className="text-gray-400 text-[10px] mt-0.5 font-mono truncate">
                      {typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result).slice(0, 100)}
                    </p>
                  )}
                  {isError && tc.preview && <p className="text-red-600">{tc.preview}</p>}
                </div>
              )
            }
            return null
          })}
        </div>
      )}
    </div>
  )
}
