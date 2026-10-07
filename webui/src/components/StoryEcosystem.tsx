import { Activity, Boxes, Drama, Gem, Network, Route, TrendingUp } from 'lucide-react';
import { isEcosystemCard, presentCard } from '../cardPresentation';
import { formatValue } from '../format';
import type { CardType, StateData, StatusCard } from '../types';

const cardTypes: CardType[] = ['plot', 'character', 'scene', 'faction', 'item', 'rule'];

function allCards(state: StateData | null): StatusCard[] {
  return cardTypes.flatMap((type) => state?.status_cards[`${type}_cards`] || []);
}

function inGroup(card: StatusCard, group: string): boolean {
  const subtype = presentCard(card).subtype;
  if (group === 'lines') return subtype === '故事线';
  if (group === 'growth') return subtype === '成长线';
  if (group === 'relationships') return subtype === '关系弧';
  if (group === 'agendas') return subtype.includes('议程');
  if (group === 'items') return subtype.includes('物品');
  if (group === 'setpieces') return subtype === '大场面';
  return subtype.includes('临时');
}

export default function StoryEcosystem({ state }: { state: StateData | null }) {
  const ecosystem = allCards(state).filter(isEcosystemCard);
  const groups = [
    { id: 'lines', label: '故事线', icon: Route, cards: ecosystem.filter((card) => inGroup(card, 'lines')) },
    { id: 'growth', label: '主要角色成长线', icon: TrendingUp, cards: ecosystem.filter((card) => inGroup(card, 'growth')) },
    { id: 'relationships', label: '核心关系弧', icon: Network, cards: ecosystem.filter((card) => inGroup(card, 'relationships')) },
    { id: 'agendas', label: '实体议程', icon: Activity, cards: ecosystem.filter((card) => inGroup(card, 'agendas')) },
    { id: 'items', label: '关键物品', icon: Gem, cards: ecosystem.filter((card) => inGroup(card, 'items')) },
    { id: 'setpieces', label: '大场面', icon: Drama, cards: ecosystem.filter((card) => inGroup(card, 'setpieces')) },
    { id: 'transient', label: '临时资产', icon: Boxes, cards: ecosystem.filter((card) => inGroup(card, 'transient')) },
  ];
  const latest = state?.latest_state;

  return (
    <section className="workspace-view ecosystem-view">
      <header className="workspace-heading">
        <div>
          <span className="eyebrow">Narrative ecology</span>
          <h1>故事生态</h1>
        </div>
        <span className="ecosystem-total"><Network size={16} />{ecosystem.length} 项规划资产</span>
      </header>

      <div className="ecosystem-summary" aria-label="故事生态状态摘要">
        <SummaryMetric label="活动故事线" value={Object.keys(latest?.narrative_line_states || {}).length || groups[0].cards.length} />
        <SummaryMetric label="核心关系" value={groups[2].cards.length} />
        <SummaryMetric label="实体议程" value={Object.keys(latest?.entity_agendas || {}).length || groups[3].cards.length} />
        <SummaryMetric label="时间线记录" value={latest?.timeline_events?.length || 0} />
      </div>

      <RuntimeState state={state} />

      <div className="ecosystem-groups">
        {groups.map((group) => {
          const Icon = group.icon;
          return (
            <section className="ecosystem-group" key={group.id}>
              <header><Icon size={16} /><h2>{group.label}</h2><span>{group.cards.length}</span></header>
              {group.cards.length ? group.cards.map((card) => {
                const presentation = presentCard(card);
                return (
                  <article className="ecosystem-row" key={card.card_id}>
                    <span className={`type-dot ${card.card_type}`} />
                    <div>
                      <b>{card.card_name}</b>
                      <small>{formatValue(presentation.goal || card.summary || card.current_state)}</small>
                    </div>
                    <span className="subtype-label">{presentation.subtype}</span>
                    <LifecycleBadge value={presentation.lifecycle} />
                  </article>
                );
              }) : <p className="ecosystem-empty">当前项目尚未生成此类资产</p>}
            </section>
          );
        })}
      </div>
    </section>
  );
}

function RuntimeState({ state }: { state: StateData | null }) {
  const latest = state?.latest_state;
  const collections = [
    { label: '故事线运行态', values: Object.entries(latest?.narrative_line_states || {}) },
    { label: '实体议程运行态', values: Object.entries(latest?.entity_agendas || {}) },
    { label: '资产生命周期', values: Object.entries(latest?.asset_states || {}) },
  ];
  if (!collections.some((item) => item.values.length) && !latest?.timeline_events?.length) return null;
  return (
    <section className="ecosystem-runtime">
      <header><Activity size={16} /><h2>当前运行态</h2></header>
      <div>
        {collections.map((collection) => (
          <section key={collection.label}>
            <header><b>{collection.label}</b><span>{collection.values.length}</span></header>
            {collection.values.slice(0, 8).map(([id, value]) => <RuntimeRow key={id} id={id} value={value} />)}
            {!collection.values.length && <p>暂无记录</p>}
          </section>
        ))}
      </div>
    </section>
  );
}

function RuntimeRow({ id, value }: { id: string; value: Record<string, unknown> }) {
  const status = String(value.lifecycle || value.status || value.state || '活动');
  const summary = value.current_goal || value.goal || value.next_action || value.summary || value.last_change || value;
  return <article className="runtime-row"><div><b>{String(value.name || value.subject_name || id)}</b><small>{formatValue(summary)}</small></div><LifecycleBadge value={status} /></article>;
}

function SummaryMetric({ label, value }: { label: string; value: number }) {
  return <div><span>{label}</span><b>{value}</b></div>;
}

function LifecycleBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const state = normalized.includes('active') || normalized.includes('活动') ? 'active'
    : normalized.includes('retir') || normalized.includes('退休') ? 'retired'
      : normalized.includes('pay') || normalized.includes('回收') ? 'settled' : 'neutral';
  return <em className={`lifecycle-badge ${state}`}>{value}</em>;
}
