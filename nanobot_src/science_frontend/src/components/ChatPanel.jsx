import ThinkingBlock from './ThinkingBlock.jsx'
import { downloadTrajectory } from '../api/hermes.js'

export default function ChatPanel({ messages }) {
  if (messages.length === 0) return null

  return (
    <div className="px-4 py-4 space-y-4">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-emerald-600 text-white rounded-br-md'
                : 'bg-gray-100 text-gray-800 rounded-bl-md'
            }`}
          >
            {msg.content ? (
              <p className="whitespace-pre-wrap break-words">{msg.displayLabel || msg.content}</p>
            ) : msg.running ? (
              <span className="inline-flex gap-1">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            ) : (
              <p className="text-gray-400 italic">（无内容）</p>
            )}

            <ThinkingBlock
              toolCalls={msg.toolCalls || []}
              reasonings={msg.reasonings || []}
            />

            {msg.usage && !msg.running && (
              <div className="mt-2 pt-2 border-t border-gray-200 space-y-1">
                <div className="text-[10px] text-gray-400">
                  消耗 {msg.usage.total_tokens} tokens
                </div>
                {msg._trajectoryCount > 0 && !msg.trajectoryEvents && (
                  <p className="text-[10px] text-gray-300">轨迹已过期（刷新后无法下载）</p>
                )}
                {msg.trajectoryEvents?.length > 0 && (
                  <button
                    onClick={() => downloadTrajectory(msg.trajectoryEvents, msg.content.slice(0, 50))}
                    className="text-[10px] text-emerald-600 hover:text-emerald-500 underline"
                  >
                    ↓ 下载轨迹 ({msg.trajectoryEvents.length} 事件)
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
      <div ref={el => el?.scrollIntoView?.({ behavior: 'smooth' })} />
    </div>
  )
}
