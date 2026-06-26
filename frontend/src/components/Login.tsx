import { useState, useEffect } from 'react';
import { TrendingUp, Mail, Lock, LogIn } from 'lucide-react';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const { setUser } = useAuthStore();

  useEffect(() => {
    authApi.registrationStatus().then((r) => {
      setRegistrationEnabled(r.registration_enabled);
    }).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const api = mode === 'login' ? authApi.login : authApi.register;
      const res = await api(email, password);
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('refresh_token', res.refresh_token);
      const user = await authApi.me();
      setUser({ id: user.id, email: user.email, is_active: user.is_active, is_admin: user.is_admin });
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 mb-4">
            <TrendingUp className="h-8 w-8 text-primary" />
          </div>
          <h1 className="text-2xl font-bold">MetaTrader</h1>
          <p className="text-sm text-muted-foreground mt-1">AI-Powered Paper Trading</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full bg-card border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                placeholder="Min 8 characters"
                className="w-full bg-card border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            <LogIn className="h-4 w-4" />
            {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>

          <button
            type="button"
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
            className="w-full text-sm text-muted-foreground hover:text-foreground transition-colors"
            disabled={!registrationEnabled && mode === 'login'}
          >
            {!registrationEnabled
              ? 'Registration is currently disabled'
              : mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}