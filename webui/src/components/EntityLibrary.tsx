import { AlertCircle, ChevronRight, Clock3, Database, Link2, Network, Search, Target, TrendingUp } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { cardSearchText, presentCard } from '../cardPresentation';
import { formatValue } from '../format';
import type { CardType, StatusCard } from '../types';

const typeLabels: Record<CardType, string> = {
  plot: '情节', character: '人物', scene: '场景', faction: '势力', item: '物品', rule: '规则',
};

interface EntityLibraryProps {
  type: CardType;
  cards: StatusCard[];
}

export default function EntityLibrary({ type, cards }: EntityLibraryProps) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('全部');
  const [selectedId, setSelectedId] = useState('');
  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    cards.forEach((card) => {
      const subtype = presentCard(card).subtype;
      counts.set(subtype, (counts.get(subtype) || 0) + 1);
    });
    return [['全部', cards.length] as [string, number], ...counts.entries()];
  }, [cards]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return cards.filter((card) => {
      const matchesCategory = category === '全部' || presentCard(card).subtype === category;
      return matchesCategory && (!needle || cardSearchText(card).includes(needle));
    });
  }, [cards, category, query]);
  const selected = filtered.find((card) => card.card_id === selectedId) || filtered[0];

  useEffect(() => {
    setCategory('全部');
    setSelectedId('');
  }, [type]);

  return (
    <section className="workspace-view entity-library">
      <header className="workspace-heading">
        <div><span className="eyebrow">状态卡索引</span><h1>{typeLabels[type]}</h1></div>
        <div className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`搜索${typeLabels[type]}`} /></div>
      </header>

      <div className="entity-filters" role="tablist" aria-label={`${typeLabels[type]}卡片分类`}>
        {categories.map(([label, count]) => <button key={label} className={category === label ? 'active' : ''} onClick={() => setCategory(label)}><span>{label}</span><b>{count}</b></button>)}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state"><Database size={24} /><b>暂无匹配的{typeLabels[type]}状态卡</b><span>初始化会建立规划卡，事件提交后会继续写入动态状态与生命周期。</span></div>
      ) : (
        <div className="entity-split">
          <div className="entity-list">
            {filtered.map((card) => {
              const view = presentCard(card);
              return (
                <button key={card.card_id} className={selected?.card_id === card.card_id ? 'entity-row active' : 'entity-row'} onClick={() => setSelectedId(card.card_id)}>
                  <span className={`type-dot ${type}`} />
                  <span><b>{card.card_name}</b><small>{card.summary || formatValue(view.goal || card.current_state)}</small><i>{view.subtype}</i></span>
                  <LifecycleBadge value={view.lifecycle} compact />
                  <ChevronRight size={15} />
                </button>
              );
            })}
          </div>

          {selected && <EntityDetail card={selected} />}
        </div>
      )}
    </section>
  );
}

function EntityDetail({ card }: { card: StatusCard }) {
  const view = presentCard(card);
  return (
    <article className="entity-detail">
      <div className="detail-title">
        <div><span className="eyebrow">{view.subtype} · {card.card_id}</span><h2>{card.card_name}</h2></div>
        <div className="detail-badges"><LifecycleBadge value={view.lifecycle} /><span className="version-badge">来源版本 {card.source_version || 1}</span></div>
      </div>

      <div className="entity-facts">
        <Fact icon={Target} label="目标" value={view.goal} />
        <Fact icon={TrendingUp} label="推进阶段" value={view.progression} />
        <Fact icon={Network} label="关联对象" value={view.connections} />
        <Fact icon={Clock3} label="生命周期" value={view.lifecycleDetail} />
      </div>

      <DetailBlock label="当前状态" value={card.current_state || card.summary} />
      <DetailBlock label="约束" value={card.constraints} />
      <DetailBlock label="本次阅读所需" value={card.reader_needs} />
      <DetailBlock label="读者已知" value={card.reader_knowledge} />
      {card.card_type === 'character' && <DetailBlock label="人物知识边界" value={card.character_knowledge} />}
      <DetailBlock label="开放问题" value={card.open_questions} />
      {card.revelation_gate && <div className="detail-block warning-block"><b><AlertCircle size={15} />揭密前置</b><pre>{formatValue(card.revelation_gate)}</pre></div>}
      <div className="detail-block"><b><Link2 size={15} />来源</b>{card.source_refs?.length ? card.source_refs.map((ref, index) => <pre key={index}>{formatValue(ref)}</pre>) : <p>暂无来源记录</p>}</div>
    </article>
  );
}

function Fact({ icon: Icon, label, value }: { icon: typeof Target; label: string; value: unknown }) {
  return <section><header><Icon size={14} /><span>{label}</span></header><pre>{formatValue(value)}</pre></section>;
}

function DetailBlock({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null || (Array.isArray(value) && !value.length)) return null;
  return <div className="detail-block"><b>{label}</b><pre>{formatValue(value)}</pre></div>;
}

function LifecycleBadge({ value, compact = false }: { value: string; compact?: boolean }) {
  const normalized = value.toLowerCase();
  const state = normalized.includes('active') || normalized.includes('活动') ? 'active'
    : normalized.includes('retir') || normalized.includes('退场') ? 'retired'
      : normalized.includes('pay') || normalized.includes('回收') || normalized.includes('完成') ? 'settled' : 'neutral';
  return <em className={`lifecycle-badge ${state} ${compact ? 'compact' : ''}`}>{value}</em>;
}
