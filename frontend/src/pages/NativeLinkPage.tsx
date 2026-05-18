import { useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/authApi';
import { ApiError } from '../api/client';
import './NativeLinkPage.css';

const formatError = (error: unknown): string => {
  if (error instanceof ApiError) {
    const payload = error.data as { detail?: string } | null;
    if (payload?.detail) {
      return payload.detail;
    }
    return `リクエストに失敗しました (${error.status})`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return '不明なエラーです';
};

const formatTimeLeft = (expiresAt: string | null, nowMs: number): string => {
  if (!expiresAt) return '';
  const expiresAtMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresAtMs)) return '';
  const remainingSec = Math.max(0, Math.floor((expiresAtMs - nowMs) / 1000));
  const minutes = Math.floor(remainingSec / 60);
  const seconds = remainingSec % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

export function NativeLinkPage() {
  const [code, setCode] = useState('');
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNowTick(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const timeLeft = useMemo(() => {
    return formatTimeLeft(expiresAt, nowTick);
  }, [expiresAt, nowTick]);

  const isExpired = useMemo(() => {
    if (!expiresAt) return false;
    const at = new Date(expiresAt).getTime();
    if (Number.isNaN(at)) return false;
    return at <= nowTick;
  }, [expiresAt, nowTick]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);
    setCopied(false);
    try {
      const response = await authApi.startNativeLink();
      setCode(response.code);
      setExpiresAt(response.expires_at);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="native-link-page">
      <div className="native-link-card">
        <h2 className="native-link-title">ネイティブアプリ連携</h2>
        <p className="native-link-subtitle">
          ワンタイムコードを発行して、Windowsネイティブアプリに貼り付けてください。
        </p>

        <ol className="native-link-steps">
          <li>ネイティブアプリを起動します。</li>
          <li>この画面で「コードを発行」を押します。</li>
          <li>コードをネイティブアプリに貼り付けて「Link」を押します。</li>
          <li>ホットキー長押しで録音し、離してから Enter で送信します。</li>
        </ol>

        <div className="native-link-actions">
          <button
            type="button"
            className="native-link-generate-btn"
            onClick={handleGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? '発行中...' : 'コードを発行'}
          </button>
          <button
            type="button"
            className="native-link-copy-btn"
            onClick={handleCopy}
            disabled={!code || isExpired}
          >
            {copied ? 'コピー済み' : 'コピー'}
          </button>
        </div>

        <div className={`native-link-code-box ${isExpired ? 'expired' : ''}`}>
          {code ? code : '未発行'}
        </div>
        <div className="native-link-meta">
          {expiresAt && !isExpired && <span>期限まで {timeLeft}</span>}
          {isExpired && <span>コードの期限が切れました。再発行してください。</span>}
        </div>

        {error && <p className="native-link-error">{error}</p>}
      </div>
    </div>
  );
}
