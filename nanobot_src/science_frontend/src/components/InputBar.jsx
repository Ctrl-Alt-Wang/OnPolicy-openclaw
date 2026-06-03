import { useState } from 'react'

export default function InputBar({ onSend, disabled }) {
  const [text, setText] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  return (
    <div className="px-4 py-3">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="输入医学科研问题..."
          disabled={disabled}
          className="flex-1 px-3 py-2 rounded-xl bg-gray-100 text-gray-900 text-sm
                     placeholder-gray-400 border border-gray-200
                     focus:outline-none focus:border-emerald-500 focus:bg-white disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium
                     hover:bg-emerald-500 active:scale-95
                     disabled:opacity-40 disabled:scale-100 transition-all"
        >
          {disabled ? (
            <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : '发送'}
        </button>
      </form>
    </div>
  )
}
