import { useEffect, useState } from 'react';
import { Users, Trash2, Shield, ShieldOff, BarChart3, DollarSign, Settings2, AlertTriangle } from 'lucide-react';
import { adminApi } from '@/lib/api';
import toast from 'react-hot-toast';

export default function AdminTab() {
  const [users, setUsers] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [_settings, setSettings] = useState<Record<string, string>>({});
  const [view, setView] = useState<'users' | 'settings' | 'stats'>('users');
  const [regEnabled, setRegEnabled] = useState(true);
  const [orBaseUrl, setOrBaseUrl] = useState('');
  const [bnBaseUrl, setBnBaseUrl] = useState('');
  const [bnWsBaseUrl, setBnWsBaseUrl] = useState('');

  const fetchUsers = () => {
    adminApi.getUsers().then((r: any) => setUsers(r)).catch(() => {});
  };

  const fetchStats = () => {
    adminApi.getStats().then((r: any) => setStats(r)).catch(() => {});
  };

  const fetchSettings = () => {
    adminApi.getSettings().then((r: any) => {
      setSettings(r);
      setRegEnabled(r.registration_enabled === 'true' || r.registration_enabled === undefined);
      setOrBaseUrl(r.openrouter_base_url || '');
      setBnBaseUrl(r.binance_api_base || '');
      setBnWsBaseUrl(r.binance_ws_base || '');
    }).catch(() => {});
  };

  useEffect(() => {
    fetchUsers();
    fetchStats();
    fetchSettings();
  }, []);

  const handleToggleUser = (userId: number, field: string, value: boolean) => {
    adminApi.updateUser(userId, { [field]: value }).then(() => {
      setUsers((prev) => prev.map((u) => u.id === userId ? { ...u, [field]: value } : u));
      toast.success(`User updated`);
    }).catch((e: any) => toast.error(e.message || 'Failed'));
  };

  const handleDeleteUser = (userId: number, email: string) => {
    if (!confirm(`Delete user "${email}"? This cascade-deletes all their portfolios, strategies, and trades.`)) return;
    adminApi.deleteUser(userId).then(() => {
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      toast.success(`Deleted ${email}`);
      fetchStats();
    }).catch((e: any) => toast.error(e.message || 'Failed'));
  };

  const handleSaveSetting = (key: string, value: string, label: string) => {
    adminApi.updateSettings(key, value).then(() => {
      setSettings((prev) => ({ ...prev, [key]: value }));
      toast.success(`${label} saved`);
    }).catch((e: any) => toast.error(e.message || 'Failed'));
  };

  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="p-3">
        <h2 className="text-lg font-bold mb-3">Admin Panel</h2>

        {/* View tabs */}
        <div className="flex gap-1 mb-3">
          {([
            { id: 'users', label: 'Users', icon: Users },
            { id: 'settings', label: 'Settings', icon: Settings2 },
            { id: 'stats', label: 'Stats', icon: BarChart3 },
          ] as const).map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              className={`flex-1 flex items-center justify-center gap-1 py-2 rounded text-xs font-medium transition-colors ${
                view === v.id ? 'bg-primary text-primary-foreground' : 'bg-card border border-border hover:bg-accent'
              }`}
            >
              <v.icon className="h-3.5 w-3.5" />
              {v.label}
            </button>
          ))}
        </div>

        {/* Users view */}
        {view === 'users' && (
          <div className="space-y-1">
            {users.map((u) => (
              <div key={u.id} className="flex items-center gap-2 p-2.5 bg-card border border-border rounded-lg">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{u.email}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {u.is_admin ? 'Admin' : 'User'} · Active: {u.is_active ? 'Yes' : 'No'}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleToggleUser(u.id, 'is_active', !u.is_active)}
                    className={`p-1.5 rounded text-xs ${u.is_active ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}
                    title={u.is_active ? 'Disable' : 'Enable'}
                  >
                    {u.is_active ? <ShieldOff className="h-3.5 w-3.5" /> : <Shield className="h-3.5 w-3.5" />}
                  </button>
                  <button
                    onClick={() => handleToggleUser(u.id, 'is_admin', !u.is_admin)}
                    className="p-1.5 rounded text-xs bg-purple-500/10 text-purple-400"
                    title={u.is_admin ? 'Demote' : 'Promote to admin'}
                  >
                    <Shield className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleDeleteUser(u.id, u.email)}
                    className="p-1.5 rounded text-xs bg-red-500/10 text-red-400"
                    title="Delete user"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
            {users.length === 0 && (
              <div className="text-sm text-muted-foreground text-center py-4">No users found</div>
            )}
          </div>
        )}

        {/* Settings view */}
        {view === 'settings' && (
          <div className="space-y-3">
            <div className="bg-card border border-border rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium">Registration</label>
                <button
                  onClick={() => {
                    const newVal = !regEnabled;
                    setRegEnabled(newVal);
                    handleSaveSetting('registration_enabled', newVal ? 'true' : 'false', 'Registration');
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    regEnabled ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'
                  }`}
                >
                  {regEnabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
              {!regEnabled && (
                <div className="flex items-center gap-1 text-[10px] text-yellow-400 bg-yellow-400/10 rounded px-2 py-1">
                  <AlertTriangle className="h-3 w-3" />
                  New registrations are blocked
                </div>
              )}
            </div>

            <div className="bg-card border border-border rounded-lg p-3">
              <label className="text-xs text-muted-foreground block mb-1">OpenRouter Base URL</label>
              <input
                value={orBaseUrl}
                onChange={(e) => setOrBaseUrl(e.target.value)}
                placeholder="https://openrouter.ai/api/v1"
                className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary mb-2"
              />
              <button
                onClick={() => handleSaveSetting('openrouter_base_url', orBaseUrl, 'OpenRouter URL')}
                className="py-1.5 px-4 bg-primary text-primary-foreground rounded text-xs font-medium"
              >
                Save
              </button>
            </div>

            <div className="bg-card border border-border rounded-lg p-3">
              <label className="text-xs text-muted-foreground block mb-1">Binance API Base URL</label>
              <input
                value={bnBaseUrl}
                onChange={(e) => setBnBaseUrl(e.target.value)}
                placeholder="https://api.binance.us"
                className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary mb-2"
              />
              <button
                onClick={() => handleSaveSetting('binance_api_base', bnBaseUrl, 'Binance API URL')}
                className="py-1.5 px-4 bg-primary text-primary-foreground rounded text-xs font-medium"
              >
                Save
              </button>
            </div>

            <div className="bg-card border border-border rounded-lg p-3">
              <label className="text-xs text-muted-foreground block mb-1">Binance WebSocket Base URL</label>
              <input
                value={bnWsBaseUrl}
                onChange={(e) => setBnWsBaseUrl(e.target.value)}
                placeholder="wss://stream.binance.us:9443/ws"
                className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary mb-2"
              />
              <button
                onClick={() => handleSaveSetting('binance_ws_base', bnWsBaseUrl, 'Binance WS URL')}
                className="py-1.5 px-4 bg-primary text-primary-foreground rounded text-xs font-medium"
              >
                Save
              </button>
            </div>
          </div>
        )}

        {/* Stats view */}
        {view === 'stats' && stats && (
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'Total Users', value: stats.total_users, icon: Users, color: 'text-blue-400' },
              { label: 'Strategies', value: stats.total_strategies, icon: BarChart3, color: 'text-purple-400' },
              { label: 'Total Trades', value: stats.total_trades, icon: BarChart3, color: 'text-green-400' },
              { label: 'Total P&L', value: `$${stats.total_pnl.toLocaleString(undefined, { signDisplay: 'always', maximumFractionDigits: 2 })}`, icon: DollarSign, color: stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400' },
              { label: 'Total Costs', value: `$${stats.total_costs.toFixed(4)}`, icon: DollarSign, color: 'text-yellow-400' },
            ].map((s) => (
              <div key={s.label} className="bg-card border border-border rounded-lg p-3">
                <s.icon className={`h-4 w-4 ${s.color} mb-1`} />
                <div className="text-lg font-bold">{String(s.value)}</div>
                <div className="text-[10px] text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}