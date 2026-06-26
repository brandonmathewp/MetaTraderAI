import { useEffect, useState, useRef } from 'react';
import {
  BarChart3, TrendingUp, TrendingDown, DollarSign, Activity, Target,
  PieChart, Percent, AlertTriangle, ChevronDown, ChevronUp,
  Brain, Database, Lightbulb, RotateCw,
} from 'lucide-react';
import { tradingApi, learningApi } from '@/lib/api';
import { useTradingStore } from '@/stores/tradingStore';
import { useModelGraphStore } from '@/stores/modelGraphStore';
import toast from 'react-hot-toast';

interface TradeDetail {
  id: number; symbol: string; side: string; quantity: number; price: number;
  confidence: number | null; outcome_pnl: number | null; status: string;
  model_prediction: string | null; created_at: string; closed_at: string | null;
}

interface Position {
  symbol: string; quantity: number; avg_entry: number; current_price: number;
  unrealized_pnl: number; realized_pnl: number; market_value: number;
  stop_loss: number | null; take_profit: number | null;
}

export default function StatsTab() {
  const { portfolios, positions, trades, selectedPortfolioId, setPortfolios, setPositions, setTrades, setSelectedPortfolio } = useTradingStore();
  const { strategies, selectedStrategyId } = useModelGraphStore();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<any>(null);
  const [expandedTrade, setExpandedTrade] = useState<number | null>(null);
  const [positionsList, setPositionsList] = useState<Position[]>([]);
  const [tradesList, setTradesList] = useState<TradeDetail[]>([]);
  const [memoryStats, setMemoryStats] = useState<any>(null);
  const [perfData, setPerfData] = useState<any>(null);
  const [mutationHistory, setMutationHistory] = useState<any>([]);
  const [showLearning, setShowLearning] = useState(false);

  const fetchData = () => {
    tradingApi.getPortfolios().then((res: any) => {
      setPortfolios(res);
      if (res.length > 0 && !selectedPortfolioId) {
        setSelectedPortfolio(res[0].id);
      }
    }).catch(() => {});
  };

  useEffect(() => { fetchData(); }, []);

  useEffect(() => {
    if (!selectedPortfolioId) return;
    setLoading(true);
    Promise.all([
      tradingApi.getSummary(selectedPortfolioId),
      tradingApi.getPositions(selectedPortfolioId),
      tradingApi.getTrades(selectedPortfolioId, 100),
      learningApi.getMemoryStats(),
    ]).then(([s, p, t, mem]: any) => {
      setSummary(s);
      setPositionsList(Array.isArray(p) ? p : []);
      setTradesList(Array.isArray(t) ? t : []);
      setMemoryStats(mem);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [selectedPortfolioId]);

  // Periodic refresh
  useEffect(() => {
    if (!selectedPortfolioId) return;
    const iv = setInterval(() => {
      tradingApi.getSummary(selectedPortfolioId).then(s => setSummary(s)).catch(() => {});
      tradingApi.getPositions(selectedPortfolioId).then((p: any) => setPositionsList(Array.isArray(p) ? p : [])).catch(() => {});
    }, 5000);
    return () => clearInterval(iv);
  }, [selectedPortfolioId]);

  const totalPnl = summary?.total_pnl || 0;
  const wins = tradesList.filter((t) => (t.outcome_pnl || 0) > 0).length;
  const losses = tradesList.filter((t) => (t.outcome_pnl || 0) < 0).length;
  const winRate = wins + losses > 0 ? ((wins / (wins + losses)) * 100) : 0;
  const totalWinningPnl = tradesList.reduce((s, t) => t.outcome_pnl && t.outcome_pnl > 0 ? s + t.outcome_pnl : s, 0);
  const totalLosingPnl = tradesList.reduce((s, t) => t.outcome_pnl && t.outcome_pnl < 0 ? s + Math.abs(t.outcome_pnl) : s, 0);
  const profitFactor = totalLosingPnl > 0 ? (totalWinningPnl / totalLosingPnl) : (totalWinningPnl > 0 ? Infinity : 0);
  const drawdown = summary?.drawdown_pct || 0;

  const stats = [
    { label: 'Equity', value: `$${(summary?.equity || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`, icon: DollarSign, color: 'text-blue-400' },
    { label: 'Cash', value: `$${(summary?.cash_balance || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`, icon: Activity, color: 'text-green-400' },
    { label: 'Total P&L', value: `$${totalPnl.toLocaleString(undefined, { signDisplay: 'always', maximumFractionDigits: 2 })}`, icon: totalPnl >= 0 ? TrendingUp : TrendingDown, color: totalPnl >= 0 ? 'text-green-400' : 'text-red-400' },
    { label: 'Return', value: `${(summary?.total_pnl_pct || 0).toFixed(2)}%`, icon: Percent, color: (summary?.total_pnl_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400' },
    { label: 'Win Rate', value: `${winRate.toFixed(1)}%`, icon: Target, color: 'text-purple-400' },
    { label: 'Profit Factor', value: profitFactor === Infinity ? '∞' : profitFactor.toFixed(2), icon: BarChart3, color: profitFactor >= 1 ? 'text-green-400' : 'text-red-400' },
    { label: 'Drawdown', value: `${drawdown.toFixed(1)}%`, icon: AlertTriangle, color: drawdown > 10 ? 'text-red-400' : 'text-yellow-400' },
    { label: 'Trades', value: `${tradesList.length} (${wins}W/${losses}L)`, icon: PieChart, color: 'text-yellow-400' },
  ];

  return (
    <div className="flex flex-col h-full overflow-auto">
      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-2 p-3">
        {stats.map((s) => (
          <div key={s.label} className="bg-card border border-border rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <s.icon className={`h-3.5 w-3.5 ${s.color}`} />
              <span className="text-xs text-muted-foreground">{s.label}</span>
            </div>
            <div className="text-lg font-bold">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Portfolio selector */}
      <div className="px-3 pb-2">
        <select
          value={selectedPortfolioId || ''}
          onChange={(e) => setSelectedPortfolio(e.target.value ? parseInt(e.target.value) : null)}
          className="bg-card border border-border rounded px-2 py-1.5 text-sm w-full"
        >
          <option value="">-- Select Portfolio --</option>
          {portfolios.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        {portfolios.length === 0 && (
          <button
            onClick={() => {
              const name = prompt('Portfolio name:', 'My Portfolio');
              const balance = parseFloat(prompt('Initial balance:', '100000') || '100000');
              if (name && balance) {
                tradingApi.createPortfolio(name, balance).then(() => fetchData()).catch(() => {});
              }
            }}
            className="mt-2 w-full py-2 text-sm text-primary border border-primary/30 rounded-lg hover:bg-primary/10"
          >
            + Create Portfolio
          </button>
        )}
      </div>

      {/* Equity curve mini */}
      {summary && (
        <div className="px-3 pb-2">
          <h3 className="text-sm font-semibold mb-1">Equity Overview</h3>
          <div className="bg-card border border-border rounded-lg p-3">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Start: ${summary.initial_balance?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              <span>Peak: ${summary.peak_equity?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden flex">
              <div
                className="h-full bg-green-500 rounded-l-full transition-all"
                style={{ width: `${Math.min(((summary.equity || 1) / (summary.peak_equity || 1)) * 100, 100)}%` }}
              />
              {drawdown > 0 && (
                <div
                  className="h-full bg-red-500/50 transition-all"
                  style={{ width: `${Math.min(drawdown, 100 - ((summary.equity || 1) / (summary.peak_equity || 1)) * 100)}%` }}
                />
              )}
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
              <span>Equity: ${(summary.equity || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              <span>Drawdown: {drawdown.toFixed(1)}%</span>
            </div>
          </div>
        </div>
      )}

      {/* Positions */}
      <div className="px-3 pb-2">
        <h3 className="text-sm font-semibold mb-1">Open Positions ({positionsList.length})</h3>
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          {positionsList.length === 0 ? (
            <div className="p-3 text-sm text-muted-foreground text-center">No open positions</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-right p-2">Qty</th>
                  <th className="text-right p-2">Entry</th>
                  <th className="text-right p-2">Market</th>
                  <th className="text-right p-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positionsList.map((p, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="p-2 font-medium">{p.symbol}</td>
                    <td className="p-2 text-right">{p.quantity}</td>
                    <td className="p-2 text-right">${p.avg_entry?.toFixed(2)}</td>
                    <td className="p-2 text-right">${p.current_price?.toFixed(2)}</td>
                    <td className={`p-2 text-right font-medium ${(p.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${(p.unrealized_pnl || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Learning & Memory Panel */}
      <div className="px-3 pb-4">
        <button
          onClick={() => setShowLearning(!showLearning)}
          className="w-full flex items-center justify-between p-3 bg-card border border-border rounded-lg hover:bg-accent/30 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-purple-400" />
            <span className="text-sm font-semibold">Learning & Memory</span>
          </div>
          {showLearning ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>

        {showLearning && (
          <div className="mt-2 space-y-2">
            {/* Memory stats */}
            {memoryStats && (
              <div className="bg-card border border-border rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-2">
                  <Database className="h-3.5 w-3.5 text-blue-400" />
                  <span className="text-xs font-semibold">Trade Memory (RAG)</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Stored:</span>
                    <span className="ml-1 font-medium">{memoryStats.total_memories}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Total PnL:</span>
                    <span className={`ml-1 font-medium ${memoryStats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${(memoryStats.total_pnl || 0).toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Wins:</span>
                    <span className="ml-1 font-medium text-green-400">{memoryStats.winning_trades}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Losses:</span>
                    <span className="ml-1 font-medium text-red-400">{memoryStats.losing_trades}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Auto-improver */}
            <div className="bg-card border border-border rounded-lg p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Lightbulb className="h-3.5 w-3.5 text-yellow-400" />
                <span className="text-xs font-semibold">Auto-Improver</span>
              </div>
              <p className="text-[10px] text-muted-foreground mb-2">
                Analyzes trade performance and mutates strategy parameters to improve results.
              </p>
              {selectedStrategyId ? (
                <div className="space-y-2">
                  <button
                    onClick={async () => {
                      try {
                        const res: any = await learningApi.runImprover(selectedStrategyId);
                        if (res.circuit_broken) {
                          toast.error(`Circuit breaker: ${res.reason}`);
                        } else if (res.mutations?.length > 0) {
                          toast.success(`${res.mutations.length} mutation(s) applied`);
                          learningApi.getImproverHistory(selectedStrategyId).then(setMutationHistory).catch(() => {});
                        } else {
                          toast('No improvements needed');
                        }
                      } catch (e: any) { toast.error(e.message || 'Failed'); }
                    }}
                    className="w-full py-2 text-xs bg-purple-500/10 border border-purple-500/30 text-purple-400 rounded-lg hover:bg-purple-500/20 transition-colors flex items-center justify-center gap-1.5"
                  >
                    <RotateCw className="h-3 w-3" />
                    Analyze & Improve (Strategy #{selectedStrategyId})
                  </button>

                  {/* Mutation history */}
                  {mutationHistory.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-[10px] text-muted-foreground">Recent mutations:</div>
                      {mutationHistory.slice(0, 5).map((m: any) => (
                        <div key={m.id} className="flex justify-between items-center text-xs bg-accent/20 rounded px-2 py-1">
                          <span>{m.reason}</span>
                          <div className="flex items-center gap-1">
                            <span className={m.applied ? 'text-green-400' : 'text-yellow-400'}>
                              {m.applied ? 'Applied' : 'Suggested'}
                            </span>
                            <span className="text-[10px] text-muted-foreground">
                              {m.created_at ? new Date(m.created_at).toLocaleDateString() : ''}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <select
                  onChange={async (e) => {
                    const id = parseInt(e.target.value);
                    if (!id) return;
                    learningApi.getStrategyPerformance(id, 7).then(setPerfData).catch(() => {});
                    learningApi.getImproverHistory(id).then(setMutationHistory).catch(() => {});
                  }}
                  className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-xs"
                >
                  <option value="">-- Select a strategy --</option>
                  {useTradingStore.getState().portfolios.length === 0 && (
                    strategies.map((s: any) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))
                  )}
                </select>
              )}
            </div>

            {/* Performance data */}
            {perfData && perfData.closed_trades > 0 && (
              <div className="bg-card border border-border rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-2">
                  <BarChart3 className="h-3.5 w-3.5 text-green-400" />
                  <span className="text-xs font-semibold">Performance: {perfData.strategy_name}</span>
                </div>
                <div className="grid grid-cols-2 gap-1.5 text-xs">
                  <div><span className="text-muted-foreground">Trades:</span> <span className="font-medium">{perfData.closed_trades}</span></div>
                  <div><span className="text-muted-foreground">Win Rate:</span> <span className="font-medium">{perfData.win_rate}%</span></div>
                  <div><span className="text-muted-foreground">Profit Factor:</span> <span className="font-medium">{perfData.profit_factor}</span></div>
                  <div><span className="text-muted-foreground">Sharpe:</span> <span className="font-medium">{perfData.sharpe_ratio}</span></div>
                  <div><span className="text-muted-foreground">Total PnL:</span> <span className={`font-medium ${perfData.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>${perfData.total_pnl?.toFixed(2)}</span></div>
                  <div><span className="text-muted-foreground">Avg Win:</span> <span className="font-medium text-green-400">${perfData.avg_win?.toFixed(2)}</span></div>
                </div>
                {perfData.model_breakdown && Object.keys(perfData.model_breakdown).length > 0 && (
                  <div className="mt-2">
                    <div className="text-[10px] text-muted-foreground mb-1">Model performance:</div>
                    {Object.entries(perfData.model_breakdown).map(([model, d]: any) => (
                      <div key={model} className="flex justify-between text-xs py-0.5">
                        <span className="truncate max-w-[120px]">{model}</span>
                        <span className="font-mono">{d.win_rate}% WR · ${d.total_pnl?.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="px-3 pb-4 flex-1">
        <h3 className="text-sm font-semibold mb-1">Trade History ({tradesList.length})</h3>
        <div className="bg-card border border-border rounded-lg overflow-auto max-h-[350px]">
          {tradesList.length === 0 ? (
            <div className="p-3 text-sm text-muted-foreground text-center">No trades yet</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border sticky top-0 bg-card z-10">
                  <th className="text-left p-2">Time</th>
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-center p-2">Side</th>
                  <th className="text-right p-2">Qty</th>
                  <th className="text-right p-2">Price</th>
                  <th className="text-right p-2">P&L</th>
                  <th className="w-5"></th>
                </tr>
              </thead>
              <tbody>
                {tradesList.map((t) => (
                  <>
                    <tr
                      key={t.id}
                      onClick={() => setExpandedTrade(expandedTrade === t.id ? null : t.id)}
                      className="border-b border-border/50 hover:bg-accent/50 cursor-pointer transition-colors"
                    >
                      <td className="p-2 text-muted-foreground">
                        {t.created_at ? new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'}
                      </td>
                      <td className="p-2 font-medium">{t.symbol}</td>
                      <td className={`p-2 text-center font-semibold ${t.side === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                        {t.side}
                      </td>
                      <td className="p-2 text-right">{t.quantity}</td>
                      <td className="p-2 text-right">${t.price?.toFixed(2)}</td>
                      <td className={`p-2 text-right font-medium ${(t.outcome_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {t.outcome_pnl != null ? `$${t.outcome_pnl.toFixed(2)}` : '-'}
                      </td>
                      <td className="p-1 text-muted-foreground">
                        {expandedTrade === t.id ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      </td>
                    </tr>
                    {expandedTrade === t.id && (
                      <tr key={`exp-${t.id}`} className="bg-accent/20">
                        <td colSpan={7} className="p-2 text-xs">
                          <div className="grid grid-cols-2 gap-1">
                            <span className="text-muted-foreground">Status:</span>
                            <span>{t.status}</span>
                            {t.confidence != null && (
                              <>
                                <span className="text-muted-foreground">Confidence:</span>
                                <span>{(t.confidence * 100).toFixed(1)}%</span>
                              </>
                            )}
                            {t.model_prediction && (
                              <>
                                <span className="text-muted-foreground">Prediction:</span>
                                <span className="truncate max-w-[150px]">{t.model_prediction}</span>
                              </>
                            )}
                            {t.closed_at && (
                              <>
                                <span className="text-muted-foreground">Closed:</span>
                                <span>{new Date(t.closed_at).toLocaleString()}</span>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}