import { AlertCircle, Database, ShieldCheck } from 'lucide-react';
import { shortFingerprint } from '../format';
import type { ContextTrace, RunResult } from '../types';

export default function ContextWorkspace({ context, lastResult }: { context: ContextTrace | null; lastResult: RunResult | null }) {
  const compiledContext = lastResult?.compiled_context || context?.compiled_context;
  return (
    <section className="workspace-view context-workspace">
      <header className="workspace-heading">
        <div><span className="eyebrow">Context Compiler</span><h1>上下文追踪</h1></div>
        {context && <span className="fingerprint">{shortFingerprint(context.fingerprint)}</span>}
      </header>
      {!context ? (
        compiledContext ? (
          <details className="raw-context" open>
            <summary>查看待审稿实际编译上下文</summary>
            <pre>{JSON.stringify(compiledContext, null, 2)}</pre>
          </details>
        ) : <div className="empty-state"><Database size={24} /><b>尚无上下文包</b></div>
      ) : (
        <>
          <div className="context-summary-band">
            <div><span>事件焦点</span><b>{context.focus}</b></div>
            <div><span>Token 预算</span><b>{context.estimated_tokens} / {context.token_budget}</b></div>
            <div><span>载入来源</span><b>{context.sources.length}</b></div>
            <div><span>载入卡片</span><b>{context.cards.length}</b></div>
          </div>
          <div className="context-columns">
            <section>
              <h2>权威来源</h2>
              {context.sources.map((source) => (
                <article className="source-card" key={source.source_id}>
                  <header>{source.protected ? <ShieldCheck size={16} /> : <Database size={16} />}<b>{source.authority}</b><em>v{source.version || 0}</em></header>
                  <code>{source.path}</code>
                  <p>{source.reason}</p>
                  <small>{source.estimated_tokens} tokens</small>
                </article>
              ))}
            </section>
            <section>
              <h2>阅读状态卡</h2>
              {context.cards.map((card) => (
                <article className="source-card" key={card.card_id}>
                  <header><span className={`type-dot ${card.card_type}`} /><b>{card.card_name}</b><em>{card.priority}</em></header>
                  <code>{card.card_id}</code>
                  <p>{card.reason}</p>
                  <small>相关度 {card.relevance_score.toFixed(2)} · {card.estimated_tokens} tokens</small>
                </article>
              ))}
            </section>
            <section>
              <h2>省略记录</h2>
              {context.omitted.length ? context.omitted.map((item) => (
                <article className="omission-row" key={`${item.source_id}-${item.reason}`}>
                  <AlertCircle size={15} /><span><b>{item.source_id}</b><small>{item.reason}</small></span>
                </article>
              )) : <p className="muted">本次没有记录省略项。</p>}
            </section>
          </div>
          {compiledContext && (
            <details className="raw-context">
              <summary>查看实际编译上下文</summary>
              <pre>{JSON.stringify(compiledContext, null, 2)}</pre>
            </details>
          )}
          {lastResult?.quality_report?.attempts && (
            <section className="quality-attempts">
              <h2>正文候选</h2>
              <div>
                {lastResult.quality_report.attempts.map((attempt, index) => (
                  <article key={index} className={Number(attempt.attempt) === lastResult.quality_report?.selected_attempt ? 'selected' : ''}>
                    <span>候选 {String(attempt.attempt || index + 1)}</span>
                    <b>{attempt.valid === false ? '结构无效' : `${String(attempt.score ?? 0)} 分`}</b>
                    <small>{Array.isArray(attempt.issues) ? attempt.issues.join('、') : String(attempt.reason || '')}</small>
                  </article>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </section>
  );
}
