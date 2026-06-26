import { useState, useEffect } from 'react';
import { Key, DollarSign, Shield, Brain, Database, Sun, Moon } from 'lucide-react';
import { costsApi, learningApi, tradingApi } from '@/lib/api';
import { useCostsStore } from '@/stores/costsStore';
import { useModelGraphStore } from '@/stores/modelGraphStore';
import { useTradingStore } from '@/stores/tradingStore';
import toast from 'react-hot-toast';

export default function SettingsTab() {
  const [openrouterKey, setOpenrouterKey] = useState('');
  const [binanceKey, setBinanceKey] = useState('');
  const [binanceSecret, setBinanceSecret] = useState('');
  const [dailyBudget, setDailyBudget] = useState('');
  const [budgetModel, setBudgetModel] = useState('gpt-4o');
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('theme') as 'dark' | 'light') || 'dark';
  });
  const { budgets, setBudgets } = useCostsStore();
  const { selectedStrategyId } = useModelGraphStore();
  const { selectedPortfolioId } = useTradingStore();
  const [maxPositionSizePct, setMaxPositionSizePct] = useState('10');
  const [stopLossPct, setStopLossPct] = useState('5');
  const [takeProfitPct, setTakeProfitPct] = useState('10');
  const [maxDrawdownPct, setMaxDrawdownPct] = useState('20');
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [improverAggressiveness, setImproverAggressiveness] = useState('moderate');
  const [autoApply, setAutoApply] = useState(false);
  const [improverRunning, setImproverRunning] = useState(false);

  const setThemeAndSync = (t: 'dark' | 'light') => {
    setTheme(t);
    localStorage.setItem('theme', t);
    document.documentElement.classList.toggle('light', t === 'light');
  };

  useEffect(() => {
    const id = selectedPortfolioId;
    if (!id) return;
    tradingApi.getRiskConfig(id).then((r: any) => {
      if (r.max_position_size_pct !== undefined) setMaxPositionSizePct(String(r.max_position_size_pct));
      if (r.stop_loss_pct !== undefined) setStopLossPct(String(r.stop_loss_pct));
      if (r.take_profit_pct !== undefined) setTakeProfitPct(String(r.take_profit_pct));
      if (r.max_drawdown_pct !== undefined) setMaxDrawdownPct(String(r.max_drawdown_pct));
    }).catch(() => {});
  }, [selectedPortfolioId]);

  useEffect(() => {
    costsApi.getBudgets().then((r: any) => setBudgets(r)).catch(() => {});
  }, [setBudgets]);

  const sections = [
    {
      id: 'api',
      icon: Key,
      label: 'API Keys',
      content: (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">OpenRouter API Key</label>
            <input
              type="password"
              value={openrouterKey}
              onChange={(e) => setOpenrouterKey(e.target.value)}
              placeholder="sk-or-v1-..."
              className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Binance.US API Key</label>
            <input
              type="password"
              value={binanceKey}
              onChange={(e) => setBinanceKey(e.target.value)}
              placeholder="Your Binance.US API key"
              className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Binance.US Secret</label>
            <input
              type="password"
              value={binanceSecret}
              onChange={(e) => setBinanceSecret(e.target.value)}
              placeholder="Your Binance.US secret"
              className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="text-[10px] text-muted-foreground">
            API keys are configured via <code className="text-primary/70">.env</code> on the server.
          </div>
        </div>
      ),
    },
    {
      id: 'budget',
      icon: DollarSign,
      label: 'Budget',
      content: (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Model</label>
            <input
              value={budgetModel}
              onChange={(e) => setBudgetModel(e.target.value)}
              placeholder="gpt-4o, claude-3-opus, etc."
              className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Max USD / Day</label>
            <input
              type="number"
              value={dailyBudget}
              onChange={(e) => setDailyBudget(e.target.value)}
              placeholder="5.00"
              step="0.01"
              className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            onClick={() => {
              const val = parseFloat(dailyBudget);
              if (val > 0 && budgetModel) {
                costsApi.setBudget(budgetModel, val).then(() => {
                  costsApi.getBudgets().then((r: any) => setBudgets(r)).catch(() => {});
                  toast.success(`Budget set for ${budgetModel}`);
                }).catch(() => toast.error('Failed to set budget'));
              }
            }}
            className="w-full py-2 bg-primary text-primary-foreground rounded text-sm font-medium"
          >
            Set Daily Budget
          </button>
          {/* Current budgets */}
          <div className="mt-2 space-y-1">
            {budgets.map((b) => (
              <div key={b.id} className="flex justify-between items-center text-xs bg-card border border-border rounded px-2 py-1.5">
                <span>{b.model_name}</span>
                <div className="flex items-center gap-2">
                  <span className={b.usage_pct > 80 ? 'text-red-400' : 'text-muted-foreground'}>
                    ${b.current_usd_spent.toFixed(4)} / ${b.max_usd_per_day.toFixed(2)}
                  </span>
                  <span className="text-muted-foreground">({b.usage_pct.toFixed(0)}%)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: 'risk',
      icon: Shield,
      label: 'Risk',
      content: (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Max Position Size (% of portfolio)</label>
            <input type="number" value={maxPositionSizePct} onChange={(e) => setMaxPositionSizePct(e.target.value)} className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Stop Loss (%)</label>
            <input type="number" value={stopLossPct} onChange={(e) => setStopLossPct(e.target.value)} className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Take Profit (%)</label>
            <input type="number" value={takeProfitPct} onChange={(e) => setTakeProfitPct(e.target.value)} className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Max Drawdown Circuit Breaker (%)</label>
            <input type="number" value={maxDrawdownPct} onChange={(e) => setMaxDrawdownPct(e.target.value)} className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
          </div>
          <button
            onClick={async () => {
              if (!selectedPortfolioId) { toast.error('Select a portfolio first'); return; }
              try {
                await tradingApi.updateRiskConfig(selectedPortfolioId, {
                  max_position_size_pct: parseFloat(maxPositionSizePct),
                  stop_loss_pct: parseFloat(stopLossPct),
                  take_profit_pct: parseFloat(takeProfitPct),
                  max_drawdown_pct: parseFloat(maxDrawdownPct),
                });
                toast.success('Risk settings saved');
              } catch { toast.error('Failed to save risk settings'); }
            }}
            className="w-full py-2 bg-primary text-primary-foreground rounded text-sm font-medium"
          >
            Save Risk Settings
          </button>
        </div>
      ),
    },
    {
      id: 'autoimprover',
      icon: Brain,
      label: 'Auto-Improver',
      content: (
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground mb-2">
            Runs on strategies to analyze performance and mutate parameters for better results.
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Aggressiveness</label>
            <select
              value={improverAggressiveness}
              onChange={(e) => setImproverAggressiveness(e.target.value)}
              className="w-full bg-black/30 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="conservative">Conservative (suggest only)</option>
              <option value="moderate">Moderate (auto-apply small changes)</option>
              <option value="aggressive">Aggressive (auto-apply all)</option>
            </select>
          </div>
          <div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox" checked={autoApply}
                onChange={(e) => setAutoApply(e.target.checked)}
                className="rounded border-border"
              />
              Auto-apply mutations
            </label>
          </div>
          <button
            onClick={async () => {
              if (!selectedStrategyId) { toast.error('Select a strategy in Orchestrator first'); return; }
              setImproverRunning(true);
              try {
                const res: any = await learningApi.runImprover(selectedStrategyId, {
                  auto_apply: autoApply,
                  aggressiveness: improverAggressiveness,
                });
                if (res.circuit_broken) {
                  toast.error(`Circuit breaker: ${res.reason}`);
                } else if (res.mutations?.length) {
                  toast.success(`${res.mutations.length} mutation(s) ${autoApply ? 'applied' : 'suggested'}`);
                } else {
                  toast('No improvements needed');
                }
              } catch (e: any) { toast.error(e.message || 'Failed'); }
              setImproverRunning(false);
            }}
            disabled={improverRunning}
            className="w-full py-2 bg-purple-500/10 border border-purple-500/30 text-purple-400 rounded text-sm font-medium hover:bg-purple-500/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Brain className="h-4 w-4" />
            {improverRunning ? 'Analyzing...' : 'Run Auto-Improver'}
          </button>
        </div>
      ),
    },
    {
      id: 'memory',
      icon: Database,
      label: 'RAG Memory',
      content: (
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground mb-2">
            ChromaDB stores trade embeddings for RAG. Models use this to learn from past trades.
          </div>
          <button
            onClick={async () => {
              if (!confirm('Clear all trade memories? This cannot be undone.')) return;
              try {
                await learningApi.clearMemory();
                toast.success('Trade memories cleared');
              } catch (e: any) { toast.error(e.message || 'Failed'); }
            }}
            className="w-full py-2 bg-destructive/90 text-destructive-foreground rounded text-sm font-medium"
          >
            Clear All Memories
          </button>
        </div>
      ),
    },
    {
      id: 'theme',
      icon: theme === 'dark' ? Moon : Sun,
      label: 'Theme',
      content: (
        <div className="space-y-3">
          <div className="flex gap-2">
            <button
              onClick={() => setThemeAndSync('dark')}
              className={`flex-1 py-3 rounded-lg border text-sm font-medium transition-colors ${
                theme === 'dark' ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:bg-accent'
              }`}
            >
              <Moon className="h-5 w-5 mx-auto mb-1" />
              Dark
            </button>
            <button
              onClick={() => setThemeAndSync('light')}
              className={`flex-1 py-3 rounded-lg border text-sm font-medium transition-colors ${
                theme === 'light' ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:bg-accent'
              }`}
            >
              <Sun className="h-5 w-5 mx-auto mb-1" />
              Light
            </button>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="p-3">
        <h2 className="text-lg font-bold mb-3">Settings</h2>
        <div className="space-y-1">
          {sections.map((s) => (
            <div key={s.id}>
              <button
                onClick={() => setActiveSection(activeSection === s.id ? null : s.id)}
                className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-accent transition-colors"
              >
                <s.icon className="h-5 w-5 text-muted-foreground" />
                <span className="text-sm flex-1 text-left">{s.label}</span>
                <span className="text-muted-foreground">{activeSection === s.id ? '▼' : '▶'}</span>
              </button>
              {activeSection === s.id && (
                <div className="px-3 pb-3 pt-1">
                  {s.content}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}