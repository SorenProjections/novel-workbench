import { Activity, AlertTriangle, CheckCircle2, Database, Eye, Network, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { formatValue, shortFingerprint } from '../format';
import type { ActivityEntry, RunResult, StateData } from '../types';

interface InspectorProps {
  state: StateData | null;
  activity: ActivityEntry[];
  lastResult: RunResult | null;
}

type InspectorTab = 'state' | 'ecosystem' | 'context' | 'activity';

export default function Inspector({ state, activity, lastResult }: InspectorProps) {
  const [tab, setTab] = useState<InspectorTab>('state');
  const snapshot = state?.latest_state;
  const context = state?.latest_context;

  return (
    <aside className="inspector">
      <div className="inspector-tabs" role="tablist">
        <button className={tab === 'state' ? 'active' : ''} onClick={() => setTab('state')}><Eye size={15} />状态</button>
        <button className={tab === 'ecosystem' ? 'active' : ''} onClick={() => setTab('ecosystem')}><Network size={15} />动态</button>
        <button className={tab === 'context' ? 'active' : ''} onClick={() => setTab('context')}><Database size={15} />上下文</button>
        <button className={tab === 'activity' ? 'active' : ''} onClick={() => setTab('activity')}><Activity size={15} />运行</button>
      </div>

      <div className="inspector-body">
        {tab === 'state' && (
          <>
            <InspectorSection title="最新事件">
              <KeyValue label="摘要" value={snapshot?.result_state_summary} />
              <KeyValue label="位置" value={snapshot?.location} />
              <KeyValue label="故事时间" value={snapshot?.time_in_story} />
              <KeyValue label="开放线头" value={snapshot?.open_threads} />
            </InspectorSection>
            <InspectorSection title="事实状态">
              <KeyValue label="资源" value={snapshot?.resources} />
              <KeyValue label="能力边界" value={snapshot?.ability_boundary} />
              <KeyValue label="关系" value={snapshot?.relationship_state} />
              <KeyValue label="实体" value={snapshot?.entity_states} />
            </InspectorSection>
            {lastResult?.quality_report && (
              <InspectorSection title="正文质量">
                <div className={`quality-chip ${lastResult.quality_report.passed ? 'pass' : 'warn'}`}>
                  {lastResult.quality_report.passed ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                  <b>{lastResult.quality_report.score ?? '未评分'}</b><span>阈值 {lastResult.quality_report.threshold ?? 72}</span>
                </div>
                <KeyValue label="生成尝试" value={lastResult.quality_attempts} />
                <KeyValue label="问题" value={lastResult.quality_report.issues} />
              </InspectorSection>
            )}
          </>
        )}

        {tab === 'ecosystem' && (
          snapshot ? (
            <>
              <DynamicSection title="故事线" entries={Object.entries(snapshot.narrative_line_states || {})} />
              <DynamicSection title="实体议程" entries={Object.entries(snapshot.entity_agendas || {})} />
              <DynamicSection title="资产生命周期" entries={Object.entries(snapshot.asset_states || {})} />
              <InspectorSection title={`时间线 ${snapshot.timeline_events?.length || 0}`}>
                {(snapshot.timeline_events || []).slice(-8).reverse().map((item, index) => <DynamicRow key={index} id={String(item.event_id || item.timeline_id || index)} value={item} />)}
              </InspectorSection>
            </>
          ) : <EmptyInspector text="暂无动态状态" />
        )}

        {tab === 'context' && (
          context ? (
            <>
              <InspectorSection title="本次焦点">
                <p className="focus-copy">{context.focus}</p>
                <KeyValue label="预算" value={`${context.estimated_tokens} / ${context.token_budget} tokens`} />
                <KeyValue label="指纹" value={shortFingerprint(context.fingerprint)} />
              </InspectorSection>
              <InspectorSection title={`来源 ${context.sources.length}`}>
                {context.sources.map((source) => <div className="trace-row" key={source.source_id}>{source.protected ? <ShieldCheck size={15} /> : <Database size={15} />}<span><b>{source.authority} · {source.path}</b><small>{source.reason}</small></span><em>{source.estimated_tokens}</em></div>)}
              </InspectorSection>
              <InspectorSection title={`状态卡 ${context.cards.length}`}>
                {context.cards.map((card) => <div className="trace-row" key={card.card_id}><span className={`type-dot ${card.card_type}`} /><span><b>{card.card_name}</b><small>{card.reason}</small></span><em>{card.relevance_score.toFixed(1)}</em></div>)}
              </InspectorSection>
            </>
          ) : <EmptyInspector text="尚无已编译上下文" />
        )}

        {tab === 'activity' && (
          activity.length ? (
            <div className="activity-list">
              {activity.map((entry) => (
                <details className={`activity-row activity-detail ${entry.level}`} key={entry.id}>
                  <summary><time>{entry.at}</time><span><b>{entry.message}</b><small>{entry.event}</small></span></summary>
                  {entry.data && <div className="activity-payload">{entry.event === 'step' && <div className="usage-line"><span>输入 {String(entry.data.input_tokens ?? 0)}</span><span>输出 {String(entry.data.output_tokens ?? 0)}</span><span>{String(entry.data.latency_ms ?? 0)} ms</span><span>{String(entry.data.prompt_hash ?? '')}</span></div>}{entry.data.request_preview ? <pre>{String(entry.data.request_preview)}</pre> : <pre>{JSON.stringify(entry.data, null, 2)}</pre>}</div>}
                </details>
              ))}
            </div>
          ) : <EmptyInspector text="暂无运行记录" />
        )}
      </div>
    </aside>
  );
}

function DynamicSection({ title, entries }: { title: string; entries: Array<[string, Record<string, unknown>]> }) {
  return <InspectorSection title={`${title} ${entries.length}`}>{entries.length ? entries.slice(0, 10).map(([id, value]) => <DynamicRow key={id} id={id} value={value} />) : <span className="inspector-muted">暂无记录</span>}</InspectorSection>;
}

function DynamicRow({ id, value }: { id: string; value: Record<string, unknown> }) {
  const status = String(value.lifecycle || value.status || value.state || '活动');
  const summary = value.current_goal || value.goal || value.next_action || value.summary || value.last_change || value;
  return <div className="dynamic-row"><span><b>{String(value.name || value.subject_name || id)}</b><small>{formatValue(summary)}</small></span><em>{status}</em></div>;
}

function InspectorSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="inspector-section"><h3>{title}</h3>{children}</section>;
}

function KeyValue({ label, value }: { label: string; value: unknown }) {
  return <div className="inspector-kv"><span>{label}</span><pre>{formatValue(value)}</pre></div>;
}

function EmptyInspector({ text }: { text: string }) {
  return <div className="inspector-empty"><Database size={22} /><span>{text}</span></div>;
}
