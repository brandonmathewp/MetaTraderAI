import { useState, useEffect, lazy, Suspense, useCallback } from 'react';
import {
  TrendingUp, BarChart3, Code2, PieChart, DollarSign, Settings, Sun, Moon,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { authApi } from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import Login from '@/components/Login';

// Lazy-loaded tabs for code splitting
const MarketTab = lazy(() => import('@/components/market/MarketTab'));
const OrchestratorTab = lazy(() => import('@/components/orchestrator/OrchestratorTab'));
const EditorTab = lazy(() => import('@/components/editor/EditorTab'));
const StatsTab = lazy(() => import('@/components/stats/StatsTab'));
const CostsTab = lazy(() => import('@/components/costs/CostsTab'));
const SettingsTab = lazy(() => import('@/components/settings/SettingsTab'));

const TABS = [
  { id: 'market', label: 'Market', icon: TrendingUp, shortcut: '1' },
  { id: 'orchestrator', label: 'Orch', icon: PieChart, shortcut: '2' },
  { id: 'editor', label: 'Editor', icon: Code2, shortcut: '3' },
  { id: 'stats', label: 'Stats', icon: BarChart3, shortcut: '4' },
  { id: 'costs', label: 'Costs', icon: DollarSign, shortcut: '5' },
  { id: 'settings', label: 'Settings', icon: Settings, shortcut: '6' },
];

function TabFallback() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
    </div>
  );
}

export default function App() {
  const { isAuthenticated, user, setUser } = useAuthStore();
  const [tab, setTab] = useState('market');
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('theme') as 'dark' | 'light') || 'dark';
  });

  useWebSocket(user?.id ?? null);

  // Apply theme to document
  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light');
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Auth check
  useEffect(() => {
    if (isAuthenticated && !user) {
      authApi.me()
        .then((u) => setUser({ id: u.id, email: u.email, is_active: u.is_active }))
        .catch(() => { setUser(null); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, user, setUser]);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    const t = TABS.find((t) => t.shortcut === e.key);
    if (t) {
      setTab(t.id);
      return;
    }
    if (e.key === 'd' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setTheme((t) => t === 'dark' ? 'light' : 'dark'); }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return <Login />;
  }

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-card/50">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">MetaTrader</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Live indicator */}
          <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="p-1 hover:bg-accent rounded transition-colors"
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? (
              <Moon className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Sun className="h-4 w-4 text-muted-foreground" />
            )}
          </button>
          <button
            onClick={() => {
              localStorage.removeItem('access_token');
              localStorage.removeItem('refresh_token');
              useAuthStore.getState().logout();
            }}
            className="text-[10px] text-muted-foreground hover:text-red-400 transition-colors"
          >
            Logout
          </button>
        </div>
      </div>

      {/* Main content - lazy loaded */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <Suspense fallback={<TabFallback />}>
          {tab === 'market' && <MarketTab />}
          {tab === 'orchestrator' && <OrchestratorTab />}
          {tab === 'editor' && <EditorTab />}
          {tab === 'stats' && <StatsTab />}
          {tab === 'costs' && <CostsTab />}
          {tab === 'settings' && <SettingsTab />}
        </Suspense>
      </div>

      {/* Bottom nav */}
      <nav className="flex items-center justify-around bg-card border-t border-border px-1 py-1">
        {TABS.map(({ id, label, icon: Icon, shortcut }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg min-w-0 transition-colors ${
              tab === id ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
            }`}
            title={`${label} (${shortcut})`}
          >
            <Icon className="h-5 w-5" />
            <span className="text-[10px] font-medium">{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}