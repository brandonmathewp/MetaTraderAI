import { useCallback, useEffect, useState, useRef } from 'react';
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  Background,
  Controls,
  MiniMap,
  type Connection,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Play, Square, Plus, Trash2, Copy, RefreshCw, Settings2,
  Zap, X,
} from 'lucide-react';
import { strategiesApi, tradingApi } from '@/lib/api';
import { useModelGraphStore } from '@/stores/modelGraphStore';
import toast from 'react-hot-toast';

const NODE_TYPES = [
  { type: 'trigger', label: 'Trigger', color: '#3b82f6' },
  { type: 'marketData', label: 'Market Data', color: '#22c55e' },
  { type: 'llmModel', label: 'LLM Model', color: '#a855f7' },
  { type: 'council', label: 'Council', color: '#f59e0b' },
  { type: 'filter', label: 'Filter', color: '#06b6d4' },
  { type: 'merge', label: 'Merge', color: '#ec4899' },
  { type: 'action', label: 'Action', color: '#ef4444' },
  { type: 'script', label: 'Script', color: '#64748b' },
];

function nodeTypeColor(type: string) {
  return NODE_TYPES.find((t) => t.type === type)?.color || '#666';
}

export default function OrchestratorTab() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const {
    strategies, selectedStrategyId, isExecuting,
    executingNodes, setStrategies, setSelectedStrategy,
    setIsExecuting, addExecutingNode, removeExecutingNode,
  } = useModelGraphStore();
  const [strategyName, setStrategyName] = useState('New Strategy');
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [nodeConfig, setNodeConfig] = useState<Record<string, any>>({});
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [portfolios, setPortfolios] = useState<{ id: number; name: string }[]>([]);
  const [intervalSec, setIntervalSec] = useState(300);
  const [runningStatus, setRunningStatus] = useState<any>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);

  // Load strategies & portfolios
  useEffect(() => {
    strategiesApi.list().then((r: any) => setStrategies(r)).catch(() => {});
    tradingApi.getPortfolios().then((r: any) => setPortfolios(r)).catch(() => {});
  }, [setStrategies]);

  // Load graph when strategy changes
  useEffect(() => {
    if (!selectedStrategyId) return;
    strategiesApi.get(selectedStrategyId).then((s: any) => {
      setStrategyName(s.name);
    }).catch(() => {});
    strategiesApi.getNodes(selectedStrategyId).then((ns: any) => {
      setNodes(ns.map((n: any) => ({
        id: n.id.toString(),
        type: 'default',
        position: { x: n.position_x, y: n.position_y },
        data: { label: n.label, nodeType: n.node_type, configJson: n.node_config_json },
      })));
    }).catch(() => {});
    strategiesApi.getEdges(selectedStrategyId).then((es: any) => {
      setEdges(es.map((e: any) => ({
        id: e.id.toString(),
        source: e.source_node_id.toString(),
        target: e.target_node_id.toString(),
        sourceHandle: e.source_handle,
        targetHandle: e.target_handle,
      })));
    }).catch(() => {});
    // Poll status
    const iv = setInterval(() => {
      strategiesApi.get(selectedStrategyId).then((r: any) => setRunningStatus(r)).catch(() => {});
    }, 5000);
    return () => clearInterval(iv);
  }, [selectedStrategyId, setNodes, setEdges]);

  const onNodeClick = useCallback((_event: any, node: Node) => {
    setSelectedNode(node);
    const configJson = node.data?.configJson;
    const rawConfig: any = node.data?.configJson;
    try { setNodeConfig(rawConfig ? JSON.parse(rawConfig) : {} as Record<string, any>); } catch { setNodeConfig({}); }
  }, []);

  const saveNodeConfig = async () => {
    if (!selectedNode || !selectedStrategyId) return;
    const cfgJson = JSON.stringify(nodeConfig);
    const d = selectedNode.data as any;
    await strategiesApi.updateNode(selectedStrategyId, parseInt(selectedNode.id), {
      node_type: d.nodeType,
      label: d.label,
      node_config_json: cfgJson,
      position_x: selectedNode.position.x,
      position_y: selectedNode.position.y,
    });
    setNodes((nds) => nds.map((n) =>
      n.id === selectedNode.id ? { ...n, data: { ...n.data, configJson: cfgJson } } : n
    ));
    setSelectedNode(null);
    toast.success('Node config saved');
  };

  const onConnect = useCallback((connection: Connection) => {
    setEdges((eds) => addEdge(connection, eds));
    if (selectedStrategyId && connection.source && connection.target) {
      strategiesApi.createEdge(selectedStrategyId, {
        source_node_id: parseInt(connection.source),
        target_node_id: parseInt(connection.target),
      }).catch(() => {});
    }
  }, [selectedStrategyId, setEdges]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const type = e.dataTransfer.getData('application/reactflow-type');
    if (!type || !reactFlowInstance || !selectedStrategyId) return;
    const pos = reactFlowInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const def = NODE_TYPES.find((t) => t.type === type);
    strategiesApi.createNode(selectedStrategyId, {
      node_type: type, label: def?.label || type,
      position_x: pos.x, position_y: pos.y,
    }).then((res: any) => {
      setNodes((nds) => [...nds, {
        id: res.id.toString(), type: 'default',
        position: { x: pos.x, y: pos.y },
        data: { label: res.label, nodeType: type, configJson: null },
      }]);
    }).catch(() => {});
  }, [reactFlowInstance, selectedStrategyId, setNodes]);

  const createStrategy = async () => {
    const name = prompt('Strategy name:', 'New Strategy');
    if (!name) return;
    const res: any = await strategiesApi.create({ name });
    setSelectedStrategy(res.id);
    setNodes([]); setEdges([]);
    strategiesApi.list().then((r: any) => setStrategies(r)).catch(() => {});
  };

  const deleteStrategy = async () => {
    if (!selectedStrategyId || !confirm('Delete this strategy?')) return;
    await strategiesApi.delete(selectedStrategyId);
    setSelectedStrategy(null); setNodes([]); setEdges([]);
    strategiesApi.list().then((r: any) => setStrategies(r)).catch(() => {});
  };

  const cloneStrategy = async () => {
    if (!selectedStrategyId) return;
    const res: any = await strategiesApi.clone(selectedStrategyId);
    toast.success(`Cloned as "${res.name}"`);
    strategiesApi.list().then((r: any) => setStrategies(r)).catch(() => {});
  };

  const executeOnce = async () => {
    if (!selectedStrategyId) return;
    setIsExecuting(true);
    try {
      const res: any = await strategiesApi.execute(selectedStrategyId, { portfolio_id: portfolioId || undefined });
      setLastResult(res);
      if (res.total_cost > 0) {
        toast.success(`Executed: ${res.nodes_executed} nodes, $${res.total_cost.toFixed(4)}`);
      } else {
        toast.success(`Executed: ${res.nodes_executed} nodes`);
      }
    } catch (e: any) { toast.error(e.message || 'Execution failed'); }
    finally { setIsExecuting(false); }
  };

  const startContinuous = async () => {
    if (!selectedStrategyId) return;
    try {
      const res: any = await strategiesApi.start(selectedStrategyId, {
        portfolio_id: portfolioId || undefined,
        interval_seconds: intervalSec,
      });
      if (res.is_running) {
        setRunningStatus(res);
        const updated = strategies.map((s) =>
          s.id === selectedStrategyId ? { ...s, is_active: true } : s
        );
        setStrategies(updated);
        toast.success(`Running every ${intervalSec}s`);
      }
    } catch (e: any) { toast.error(e.message || 'Start failed'); }
  };

  const stopContinuous = async () => {
    if (!selectedStrategyId) return;
    try {
      await strategiesApi.stop(selectedStrategyId);
      setRunningStatus(null);
      const updated = strategies.map((s) =>
        s.id === selectedStrategyId ? { ...s, is_active: false } : s
      );
      setStrategies(updated);
      toast.success('Stopped');
    } catch (e: any) { toast.error(e.message || 'Stop failed'); }
  };

  const isRunning = runningStatus?.is_running || strategies.find(s => s.id === selectedStrategyId)?.is_active;

  // Inject glow/animation into running nodes via class
  const nodesWithAnimation = nodes.map((n) => ({
    ...n,
    className: executingNodes.has(n.id) ? 'executing-pulse' : '',
  }));

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border overflow-x-auto">
        <select
          value={selectedStrategyId || ''}
          onChange={(e) => setSelectedStrategy(e.target.value ? parseInt(e.target.value) : null)}
          className="bg-card border border-border rounded px-2 py-1 text-xs flex-1 min-w-0"
        >
          <option value="">-- Select --</option>
          {strategies.map((s) => (
            <option key={s.id} value={s.id}>{s.name} {s.is_active ? '●' : ''}</option>
          ))}
        </select>
        <button onClick={createStrategy} className="p-1 hover:bg-accent rounded flex-shrink-0" title="New">
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button onClick={cloneStrategy} className="p-1 hover:bg-accent rounded flex-shrink-0" title="Clone">
          <Copy className="h-3.5 w-3.5" />
        </button>
        <button onClick={executeOnce} disabled={isExecuting} className="p-1 hover:bg-green-500/20 text-green-400 rounded flex-shrink-0" title="Run once">
          <Play className="h-3.5 w-3.5" fill={isExecuting ? 'currentColor' : 'none'} />
        </button>
        {isRunning ? (
          <button onClick={stopContinuous} className="p-1 bg-red-500/20 text-red-400 rounded flex-shrink-0" title="Stop">
            <Square className="h-3.5 w-3.5" fill="currentColor" />
          </button>
        ) : (
          <button onClick={startContinuous} className="p-1 hover:bg-green-500/20 text-green-400 rounded flex-shrink-0" title="Run continuously">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        )}
        <select
          value={portfolioId || ''}
          onChange={(e) => setPortfolioId(e.target.value ? parseInt(e.target.value) : null)}
          className="bg-card border border-border rounded px-1.5 py-1 text-[10px] w-20 flex-shrink-0"
          title="Portfolio"
        >
          <option value="">P: None</option>
          {portfolios.map((p) => (
            <option key={p.id} value={p.id}>P: {p.name}</option>
          ))}
        </select>
        <button onClick={deleteStrategy} className="p-1 hover:bg-red-500/20 text-red-400 rounded flex-shrink-0" title="Delete">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Canvas */}
      <div className="flex-1 min-h-0 relative" ref={reactFlowWrapper}>
        <ReactFlow
          nodes={nodesWithAnimation}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onInit={setReactFlowInstance}
          onDragOver={onDragOver}
          onDrop={onDrop}
          fitView
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ animated: true }}
        >
          <Background color="#1a1a1a" gap={20} />
          <Controls className="!bg-card !border-border !rounded-lg" />
          <MiniMap
            nodeColor={(n) => nodeTypeColor((n.data as any)?.nodeType || '')}
            className="!bg-card !border-border"
          />
        </ReactFlow>
      </div>

      {/* Node palette */}
      <div className="flex gap-1 px-2 py-1.5 border-t border-border overflow-x-auto">
        {NODE_TYPES.map((nt) => (
          <div
            key={nt.type}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('application/reactflow-type', nt.type);
              e.dataTransfer.effectAllowed = 'move';
            }}
            className="flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium cursor-grab whitespace-nowrap shrink-0"
            style={{ backgroundColor: nt.color + '20', color: nt.color, border: `1px solid ${nt.color}40` }}
          >
            {nt.label}
          </div>
        ))}
      </div>

      {/* Node config panel (slide-up sheet) */}
      {selectedNode && (
        <div className="absolute inset-0 z-50 flex items-end" onClick={() => setSelectedNode(null)}>
          <div
            className="w-full bg-card border-t border-border rounded-t-xl max-h-[60%] overflow-auto p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">
                {(() => { const nd = selectedNode.data as any; return (
                  <><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: nodeTypeColor(nd?.nodeType || '') }} />
                {nd?.label || 'Node'}</>
                ); })()}
              </h3>
              <button onClick={() => setSelectedNode(null)} className="p-1 hover:bg-accent rounded">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3">
              {/* Label */}
              <div>
                <label className="text-xs text-muted-foreground">Label</label>
                <input
                  value={nodeConfig.label || selectedNode.data?.label || ''}
                  onChange={(e) => setNodeConfig({ ...nodeConfig, label: e.target.value })}
                  className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                  onBlur={() => {
                    if (nodeConfig.label) {
                      selectedNode.data.label = nodeConfig.label;
                      setNodes((nds) => nds.map((n) => n.id === selectedNode.id ? { ...n, data: { ...n.data, label: nodeConfig.label } } : n));
                    }
                  }}
                />
              </div>

              {/* Model selector for LLM/Council */}
              {(selectedNode.data?.nodeType === 'llmModel' || selectedNode.data?.nodeType === 'council') && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">OpenRouter Model</label>
                    <input
                      value={nodeConfig.model_name || ''}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, model_name: e.target.value })}
                      placeholder="gpt-4o, claude-3-opus, gemini-flash..."
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">System Prompt</label>
                    <textarea
                      value={nodeConfig.system_prompt || ''}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, system_prompt: e.target.value })}
                      rows={3}
                      placeholder="You are a trading analyst..."
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-xs mt-0.5 resize-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-muted-foreground">Temperature</label>
                      <input
                        type="number" step="0.1" min="0" max="2"
                        value={nodeConfig.temperature ?? 0.7}
                        onChange={(e) => setNodeConfig({ ...nodeConfig, temperature: parseFloat(e.target.value) })}
                        className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Max Tokens</label>
                      <input
                        type="number" step="1" min="1" max="16384"
                        value={nodeConfig.max_tokens ?? 1024}
                        onChange={(e) => setNodeConfig({ ...nodeConfig, max_tokens: parseInt(e.target.value) })}
                        className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                      />
                    </div>
                  </div>
                </>
              )}

              {/* Council specific */}
              {selectedNode.data?.nodeType === 'council' && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Voter Models (comma-separated)</label>
                    <input
                      value={Array.isArray(nodeConfig.voter_models) ? nodeConfig.voter_models.join(', ') : (nodeConfig.voter_models || '')}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, voter_models: e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean) })}
                      placeholder="gpt-4o, claude-3-opus, gemini-flash"
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Presiding Model</label>
                    <input
                      value={nodeConfig.presiding_model || ''}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, presiding_model: e.target.value })}
                      placeholder="gpt-4o"
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Question</label>
                    <input
                      value={nodeConfig.question || ''}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, question: e.target.value })}
                      placeholder="Analyze the market data and decide: BUY, SELL, or HOLD?"
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    />
                  </div>
                </>
              )}

              {/* Market Data */}
              {selectedNode.data?.nodeType === 'marketData' && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Symbol</label>
                    <input
                      value={nodeConfig.symbol || ''}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, symbol: e.target.value.toUpperCase() })}
                      placeholder="BTCUSDT"
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Interval</label>
                    <select
                      value={nodeConfig.interval || '1m'}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, interval: e.target.value })}
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    >
                      {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((i) => (
                        <option key={i} value={i}>{i}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              {/* Action */}
              {selectedNode.data?.nodeType === 'action' && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Confidence Threshold</label>
                    <input
                      type="number" step="0.05" min="0" max="1"
                      value={nodeConfig.confidence_threshold ?? 0.7}
                      onChange={(e) => setNodeConfig({ ...nodeConfig, confidence_threshold: parseFloat(e.target.value) })}
                      className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                    />
                  </div>
                </>
              )}

              {/* Filter */}
              {selectedNode.data?.nodeType === 'filter' && (
                <div>
                  <label className="text-xs text-muted-foreground">Condition (Python expression)</label>
                  <input
                    value={nodeConfig.condition || ''}
                    onChange={(e) => setNodeConfig({ ...nodeConfig, condition: e.target.value })}
                    placeholder="len(items) > 5"
                    className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5 font-mono"
                  />
                </div>
              )}

              {/* Merge */}
              {selectedNode.data?.nodeType === 'merge' && (
                <div>
                  <label className="text-xs text-muted-foreground">Strategy</label>
                  <select
                    value={nodeConfig.merge_strategy || 'concatenate'}
                    onChange={(e) => setNodeConfig({ ...nodeConfig, merge_strategy: e.target.value })}
                    className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-sm mt-0.5"
                  >
                    <option value="concatenate">Concatenate</option>
                    <option value="best_confidence">Best Confidence</option>
                    <option value="weighted">Weighted</option>
                  </select>
                </div>
              )}

              {/* Script */}
              {selectedNode.data?.nodeType === 'script' && (
                <div>
                  <label className="text-xs text-muted-foreground">Python Code</label>
                  <textarea
                    value={nodeConfig.script_code || ''}
                    onChange={(e) => setNodeConfig({ ...nodeConfig, script_code: e.target.value })}
                    rows={6}
                    placeholder={`def main(input_data):\n    # your logic here\n    return {"action": "HOLD"}\n\nresult = main(input_data)`}
                    className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-xs mt-0.5 font-mono resize-none"
                  />
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button onClick={saveNodeConfig} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
                  Save Config
                </button>
                {selectedNode.data?.nodeType === 'llmModel' && (
                  <button onClick={() => toast('Model nodes need OpenRouter API key in Settings')}
                    className="py-2 px-3 bg-accent rounded-lg text-sm" title="Test model">
                    <Zap className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            {/* Last execution result for this node */}
            {lastResult?.results?.[parseInt(selectedNode.id)] && (
              <div className="mt-3 p-2 bg-black/30 rounded text-xs">
                <div className="text-muted-foreground mb-1">Last Result:</div>
                <pre className="text-green-400/80 overflow-auto max-h-20">
                  {JSON.stringify(lastResult.results[parseInt(selectedNode.id)], null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Execution summary bar */}
      {lastResult && (
        <div className="px-2 py-1 border-t border-border bg-accent/30 text-xs flex items-center gap-3 overflow-x-auto">
          <span className="text-muted-foreground">Last run:</span>
          <span>{lastResult.nodes_executed} nodes</span>
          <span className="text-primary">${lastResult.total_cost?.toFixed(4)}</span>
          <span>{lastResult.total_tokens} tokens</span>
          {isRunning && (
            <>
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
              <span className="text-green-400">Running every {intervalSec}s</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}