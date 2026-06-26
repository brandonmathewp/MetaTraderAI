import { useEffect, useState, useCallback } from 'react';
import {
  DollarSign, TrendingUp, BarChart3, AlertTriangle,
  Zap, Clock, Trash2, Plus, RefreshCw, ChevronDown, ChevronUp,
} from 'lucide-react';
import { costsApi } from '@/lib/api';
import { useCostsStore } from '@/stores/costsStore';
import toast from 'react-hot-toast';

export default function CostsTab() {
  const {
    todayCosts, overallCost, overallCalls,
    strategyCosts, predictiveCost, predictive7d, predictive30d,
    budgets, costHistory, recentUpdates, lastUpdate,
    modelRates,
    setTodayCosts, setStrategyCosts, setPredictiveCost, setPredictives,
    setBudgets, setCostHistory, setModelRates,
  } = useCostsStore();

  const [showAddBudget, setShowAddBudget] = useState(false);
  const [newBudgetModel, setNewBudgetModel] = useState('');
  const [newBudgetAmount, setNewBudgetAmount] = useState('5.00');
  const [expandedStrategy, setExpandedStrategy] = useState<number | null>(null);
  const [strategyDetail, setStrategyDetail] = useState<any>(null);
  const [selectedDays, setSelectedDays] = useState(7);

  const fetchData = useCallback(() => {
    costsApi.getToday().then((r: any) => setTodayCosts(r.models, r.overall_cost, r.overall_calls)).catch(() => {});
    costsApi.getByStrategy(selectedDays).then((r: any) => setStrategyCosts(r.strategies)).catch(() => {});
    costsApi.getPredictive(30).then((r: any) => {
      setPredictives(r.projected_7day_rate, r.projected_30day_rate);
      setPredictiveCost(r.projected_7day_rate);
    }).catch(() => {});
    costsApi.getBudgets().then((r: any) => setBudgets(r)).catch(() => {});
    costsApi.getHistory(30).then((r: any) => setCostHistory(r)).catch(() => {});
    costsApi.getModelRates().then((r: any) => setModelRates(r.rates || {})).catch(() => {});
  }, [selectedDays, setTodayCosts, setStrategyCosts, setPredictives, setPredictiveCost, setBudgets, setCostHistory, setModelRates]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh every 15s
  useEffect(() => {
    const iv = setInterval(() => {
      costsApi.getToday().then((r: any) => setTodayCosts(r.models, r.overall_cost, r.overall_calls)).catch(() => {});
      costsApi.getBudgets().then((r: any) => setBudgets(r)).catch(() => {});
    }, 15000);
    return () => clearInterval(iv);
  }, [setTodayCosts, setBudgets]);

  const totalBudget = budgets.reduce((s, b) => s + b.max_usd_per_day, 0);
  const maxBar = Math.max(totalBudget, overallCost * 2, 5);

  const handleAddBudget = async () => {
    if (!newBudgetModel || !newBudgetAmount) return;
    const amt = parseFloat(newBudgetAmount);
    if (isNaN(amt) || amt <= 0) { toast.error('Invalid amount'); return; }
    await costsApi.setBudget(newBudgetModel, amt).catch(() => toast.error('Failed to set budget'));
    setShowAddBudget(false);
    setNewBudgetModel('');
    setNewBudgetAmount('5.00');
    fetchData();
    toast.success(`Budget set for ${newBudgetModel}: $${amt}/day`);
  };

  const handleDeleteBudget = async (id: number) => {
    await costsApi.deleteBudget(id).catch(() => toast.error('Failed'));
    fetchData();
  };

  const handleStrategyExpand = async (strategyId: number | null) => {
    if (!strategyId) return;
    if (expandedStrategy === strategyId) {
      setExpandedStrategy(null); setStrategyDetail(null);
    } else {
      setExpandedStrategy(strategyId);
      const detail: any = await costsApi.getStrategyDetail(strategyId, selectedDays).catch(() => null);
      setStrategyDetail(detail);
    }
  };

  const timeSinceUpdate = lastUpdate ? Math.floor((Date.now() - lastUpdate) / 1000) : 99;
  const isLive = timeSinceUpdate < 30;

  return (
    <div className="flex flex-col h-full overflow-auto">
      {/* Live counter pulse */}
      {isLive && lastUpdate > 0 && (
        <div className="px-3 pt-2 flex items-center justify-center gap-1">
          <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
          <span className="text-[10px] text-green-400/70">Live</span>
        </div>
      )}

      {/* Today's total */}
      <div className="p-3 pb-1">
        <div className="bg-card border border-border rounded-lg p-4 relative overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">Today's Spending</span>
              {recentUpdates.length > 0 && (
                <span className="px-1.5 py-0.5 bg-primary/20 text-primary text-[10px] rounded-full">
                  {recentUpdates.length} recent
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">{overallCalls} calls</span>
          </div>
          <div className="text-3xl font-bold text-primary transition-all duration-300">
            ${overallCost.toFixed(6)}
          </div>
          <div className="mt-2">
            <div className="h-2 bg-muted rounded-full overflow-hidden flex">
              {todayCosts.map((c, i) => {
                const pct = maxBar > 0 ? (c.cost / maxBar) * 100 : 0;
                const colors = ['#3b82f6', '#a855f7', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#64748b'];
                return (
                  <div
                    key={c.model}
                    className="h-full transition-all duration-500"
                    style={{ width: `${pct}%`, backgroundColor: colors[i % colors.length] }}
                    title={`${c.model}: $${c.cost.toFixed(4)}`}
                  />
                );
              })}
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
              <span>$0</span>
              <span>Budget cap: ${totalBudget.toFixed(2)}</span>
              <span>+${maxBar.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Quick budget add */}
      <div className="px-3 pb-1">
        <button
          onClick={() => setShowAddBudget(!showAddBudget)}
          className="w-full py-1.5 text-xs text-muted-foreground border border-dashed border-border rounded-lg hover:border-primary/50 transition-colors"
        >
          {showAddBudget ? 'Cancel' : '+ Add Budget Limit'}
        </button>
        {showAddBudget && (
          <div className="bg-card border border-border rounded-lg p-3 mt-1 space-y-2">
            <input
              type="text" value={newBudgetModel}
              onChange={(e) => setNewBudgetModel(e.target.value)}
              placeholder="Model name (e.g. gpt-4o)"
              className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-xs"
            />
            <div className="flex gap-2">
              <div className="relative flex-1">
                <DollarSign className="absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
                <input
                  type="number" step="0.01" value={newBudgetAmount}
                  onChange={(e) => setNewBudgetAmount(e.target.value)}
                  placeholder="5.00"
                  className="w-full bg-black/30 border border-border rounded pl-7 pr-2 py-1.5 text-xs"
                />
              </div>
              <button onClick={handleAddBudget}
                className="px-3 py-1.5 bg-primary text-primary-foreground rounded text-xs font-medium">
                Set Budget
              </button>
            </div>
            {Object.keys(modelRates).length > 0 && (
              <div className="text-[10px] text-muted-foreground">
                Common: {Object.keys(modelRates).slice(0, 5).join(', ')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Per-model breakdown with live counters */}
      <div className="px-3 pb-2">
        <div className="flex items-center gap-1.5 mb-2">
          <DollarSign className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Per Model</h3>
          <Zap className="h-3 w-3 text-yellow-400" />
        </div>
        <div className="space-y-1.5">
          {todayCosts.map((c) => {
            const budget = budgets.find((b) => b.model_name === c.model);
            const pct = budget ? budget.usage_pct : (maxBar > 0 ? (c.cost / maxBar) * 100 : 0);
            const isOverBudget = budget && budget.current_usd_spent >= budget.max_usd_per_day;
            const isNearBudget = budget && budget.usage_pct > 80;
            return (
              <div key={c.model} className={`bg-card border rounded-lg p-2.5 transition-colors ${
                isOverBudget ? 'border-red-500/50 bg-red-500/5' : isNearBudget ? 'border-yellow-500/50 bg-yellow-500/5' : 'border-border'
              }`}>
                <div className="flex justify-between items-center mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium truncate max-w-[140px]">{c.model}</span>
                    {modelRates[c.model] && (
                      <span className="text-[9px] text-muted-foreground">
                        ${modelRates[c.model].input}/1M in
                      </span>
                    )}
                  </div>
                  <span className="text-xs font-mono">${c.cost.toFixed(6)}</span>
                </div>
                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(pct, 100)}%`,
                      backgroundColor: isOverBudget ? '#ef4444' : isNearBudget ? '#f59e0b' : '#22c55e',
                    }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
                  <span>{c.calls} calls · {c.request_tokens + c.response_tokens} tok</span>
                  <span>
                    {budget ? (
                      <>{isOverBudget && <AlertTriangle className="h-2.5 w-2.5 inline text-red-400 mr-0.5" />}
                      ${budget.current_usd_spent.toFixed(4)} / ${budget.max_usd_per_day.toFixed(2)}
                      </>
                    ) : 'Unlimited'}
                  </span>
                </div>
              </div>
            );
          })}
          {todayCosts.length === 0 && (
            <div className="text-xs text-muted-foreground text-center py-4 border border-dashed border-border rounded-lg">
              No model calls recorded today
            </div>
          )}
        </div>
      </div>

      {/* Active budgets */}
      <div className="px-3 pb-2">
        <div className="flex items-center gap-1.5 mb-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Daily Budgets ({budgets.length})</h3>
        </div>
        <div className="space-y-1">
          {budgets.map((b) => (
            <div key={b.id} className="flex items-center gap-2 bg-card border border-border rounded px-3 py-2">
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{b.model_name}</div>
                <div className="h-1 bg-muted rounded-full mt-1 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${b.usage_pct > 80 ? 'bg-red-500' : b.usage_pct > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
                    style={{ width: `${Math.min(b.usage_pct, 100)}%` }}
                  />
                </div>
              </div>
              <span className="text-xs font-mono whitespace-nowrap">
                ${b.current_usd_spent.toFixed(4)} / ${b.max_usd_per_day}
              </span>
              <button onClick={() => handleDeleteBudget(b.id)}
                className="p-1 hover:bg-red-500/20 rounded text-red-400/60 hover:text-red-400">
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {budgets.length === 0 && (
            <div className="text-xs text-muted-foreground text-center py-2 border border-dashed border-border rounded-lg">
              No budgets configured — all models Unlimited
            </div>
          )}
        </div>
      </div>

      {/* Strategy cost breakdown */}
      <div className="px-3 pb-2">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Per Strategy</h3>
          </div>
          <select value={selectedDays} onChange={(e) => setSelectedDays(parseInt(e.target.value))}
            className="bg-card border border-border rounded px-1.5 py-0.5 text-[10px]">
            <option value={1}>1d</option>
            <option value={7}>7d</option>
            <option value={30}>30d</option>
            <option value={90}>90d</option>
          </select>
        </div>
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          {strategyCosts.length === 0 ? (
            <div className="p-3 text-xs text-muted-foreground text-center">No strategy costs</div>
          ) : (
            strategyCosts.map((s) => (
              <div key={s.strategy_id || 'none'}>
                <button
                  onClick={() => handleStrategyExpand(s.strategy_id)}
                  className="w-full flex justify-between items-center p-2.5 border-b border-border/50 hover:bg-accent/30 transition-colors"
                >
                  <div className="text-left min-w-0">
                    <div className="text-xs font-medium truncate">{s.strategy_name}</div>
                    <div className="text-[10px] text-muted-foreground">{s.calls} model calls</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono">${s.total_cost.toFixed(4)}</span>
                    {expandedStrategy === s.strategy_id ? <ChevronUp className="h-3 w-3 text-muted-foreground" /> : <ChevronDown className="h-3 w-3 text-muted-foreground" />}
                  </div>
                </button>
                {expandedStrategy === s.strategy_id && strategyDetail && (
                  <div className="p-2.5 bg-accent/10 border-b border-border/50 text-xs space-y-2">
                    {strategyDetail.models?.length > 0 && (
                      <div>
                        <div className="text-[10px] text-muted-foreground mb-1">Model breakdown:</div>
                        {strategyDetail.models.map((m: any) => (
                          <div key={m.model} className="flex justify-between items-center py-0.5">
                            <span className="truncate mr-2">{m.model}</span>
                            <span className="font-mono">${m.cost.toFixed(6)} ({m.calls})</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {strategyDetail.daily?.length > 0 && (
                      <div>
                        <div className="text-[10px] text-muted-foreground mb-1">Daily spend:</div>
                        <div className="flex items-end gap-0.5 h-10">
                          {strategyDetail.daily.map((d: any, i: number) => {
                            const maxVal = Math.max(...strategyDetail.daily.map((x: any) => x.cost), 0.01);
                            const h = (d.cost / maxVal) * 100;
                            return (
                              <div key={i} className="flex-1 flex flex-col" title={`${d.date}: $${d.cost.toFixed(6)}`}>
                                <div className="w-full bg-primary/60 rounded-t-sm" style={{ height: `${Math.max(h, 1)}%`, minHeight: 1 }} />
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Predictive costs */}
      <div className="px-3 pb-2">
        <div className="flex items-center gap-1.5 mb-2">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">30-Day Projection</h3>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-card border border-border rounded-lg p-3 text-center">
            <div className="text-lg font-bold">${predictive7d.toFixed(2)}</div>
            <div className="text-[10px] text-muted-foreground">7-day avg</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-3 text-center">
            <div className="text-lg font-bold">${predictive30d.toFixed(2)}</div>
            <div className="text-[10px] text-muted-foreground">30-day avg</div>
          </div>
        </div>
        {totalBudget > 0 && predictive7d > totalBudget * 30 && (
          <div className="flex items-center gap-1 mt-2 text-xs text-red-400 bg-red-400/10 rounded-lg px-3 py-2">
            <AlertTriangle className="h-3 w-3" />
            Projected cost exceeds monthly budget
          </div>
        )}
      </div>

      {/* Cost history bar chart */}
      <div className="px-3 pb-4">
        <div className="flex items-center gap-1.5 mb-2">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">History (30d)</h3>
        </div>
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="flex items-end gap-0.5 h-20">
            {costHistory.map((h, i) => {
              const maxVal = Math.max(...costHistory.map((ch) => ch.total_cost), 0.01);
              const height = (h.total_cost / maxVal) * 100;
              return (
                <div key={i} className="flex-1 flex flex-col items-center" title={`${h.date}: $${h.total_cost.toFixed(4)}`}>
                  <div className="w-full bg-primary/60 rounded-t-sm min-h-[1px]" style={{ height: `${Math.max(height, 1)}%` }} />
                </div>
              );
            })}
          </div>
          {costHistory.length === 0 && (
            <div className="text-xs text-muted-foreground text-center py-4">No history data</div>
          )}
        </div>
      </div>

      {/* Model rate reference */}
      {Object.keys(modelRates).length > 0 && (
        <div className="px-3 pb-4">
          <div className="flex items-center gap-1.5 mb-2">
            <DollarSign className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Model Rates ($/1M tokens)</h3>
          </div>
          <div className="bg-card border border-border rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-2">Model</th>
                  <th className="text-right p-2">Input</th>
                  <th className="text-right p-2">Output</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(modelRates).slice(0, 10).map(([name, rates]) => (
                  <tr key={name} className="border-b border-border/50">
                    <td className="p-2 truncate max-w-[120px]">{name}</td>
                    <td className="p-2 text-right">${rates.input.toFixed(4)}</td>
                    <td className="p-2 text-right">${rates.output.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}