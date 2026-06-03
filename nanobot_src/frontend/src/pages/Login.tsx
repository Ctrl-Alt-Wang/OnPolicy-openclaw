import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { prewarmRuntime, ssoLogin } from '../lib/api'

const INFOX_LOGIN_BASE_URL = 'https://www.infox-med.com/#/loginPage'

export default function Login() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [iframeKey, setIframeKey] = useState(0)
  const handledRef = useRef(false)

  const resetToQrLogin = (message: string) => {
    setError(message)
    handledRef.current = false
    setIframeKey((current) => current + 1)
  }

  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
      // Only accept messages from infox-med
      if (event.origin !== 'https://www.infox-med.com') return

      const msgData = event.data
      if (!msgData || msgData.key !== 'pushToken') return

      // Prevent duplicate handling
      if (handledRef.current) return
      handledRef.current = true

      const infoxToken = msgData.data
      if (!infoxToken) {
        setError('未获取到登录凭证')
        handledRef.current = false
        return
      }

      setLoading(true)
      setError('')
      try {
        await ssoLogin(infoxToken)
        void prewarmRuntime().catch(() => {})
        // 登录成功后清除所有状态，确保TopBar重新初始化
        navigate('/dashboard', { replace: true })
      } catch (err: unknown) {
        const errorMessage = err instanceof Error ? err.message : '登录失败'
        if (errorMessage.includes('InfoX-Med token 无效或已过期')) {
          resetToQrLogin('授权已失效，请重新扫码登录 InfoX-Med 后再试')
          return
        }
        setError(errorMessage)
        handledRef.current = false
      } finally {
        setLoading(false)
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [navigate])

  return (
    <div className="flex min-h-screen items-center justify-center bg-dark-bg">
      <div className="w-full max-w-[780px] rounded-xl border border-dark-border bg-dark-card p-6">
        {/* Logo */}
        <div className="mb-4 flex flex-col items-center gap-2">
          <img
            src="/medclaw-logo.png"
            alt="MedClaw"
            className="h-10 w-10 rounded-lg"
          />
          <h1 className="text-lg font-semibold text-dark-text">MedClaw 医疗智能助手</h1>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-3 rounded-lg bg-accent-red/10 p-3 text-sm text-accent-red">
            {error}
          </div>
        )}

        {/* Loading overlay */}
        {loading && (
          <div className="mb-3 flex items-center justify-center gap-2 text-sm text-dark-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>正在登录...</span>
          </div>
        )}

        {/* InfoX-Med Login iframe */}
        <div className="flex justify-center">
          <iframe
            key={iframeKey}
            src={`${INFOX_LOGIN_BASE_URL}?reload=${iframeKey}`}
            className="rounded-lg border-0"
            width="730"
            height="478"
            scrolling="no"
            title="InfoX-Med 登录"
          />
        </div>

        <p className="mt-4 text-center text-xs text-dark-muted">
          使用 InfoX-Med 账号登录
        </p>
      </div>
    </div>
  )
}
