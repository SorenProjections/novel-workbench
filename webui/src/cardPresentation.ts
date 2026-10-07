import type { CardType, StatusCard } from './types';

export interface CardPresentation {
  subtype: string;
  lifecycle: string;
  goal: unknown;
  progression: unknown;
  connections: unknown;
  lifecycleDetail: unknown;
}

const subtypeByPrefix: Array<[string, string]> = [
  ['plot_master_story_design', '全书总纲'],
  ['plot_volume_story_engine', '卷故事引擎'],
  ['plot_hook_', '伏笔'],
  ['plot_relationship_', '关系弧'],
  ['plot_line_', '故事线'],
  ['plot_set_piece_', '大场面'],
  ['plot_transient_', '临时线索'],
  ['plot_agenda_', '实体议程'],
  ['character_growth_', '成长线'],
  ['character_agenda_', '角色议程'],
  ['faction_agenda_', '势力议程'],
  ['scene_agenda_', '生态议程'],
  ['item_arc_', '关键物品弧'],
  ['item_track_', '卷物品轨迹'],
  ['scene_major_map_', '主要地图'],
  ['scene_location_', '卷地点'],
  ['scene_asset_', '场景资产'],
];

const fallbackLabels: Record<CardType, string> = {
  plot: '事件与情节',
  character: '人物状态',
  scene: '场景状态',
  faction: '势力状态',
  item: '物品状态',
  rule: '规则约束',
};

function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function firstValue(source: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== '' && (!Array.isArray(value) || value.length)) {
      return value;
    }
  }
  return undefined;
}

export function presentCard(card: StatusCard): CardPresentation {
  const state = recordOf(card.current_state);
  const attributes = recordOf(card.attributes);
  const subtype = subtypeByPrefix.find(([prefix]) => card.card_id.startsWith(prefix))?.[1]
    || (card.card_id.includes('_transient_') ? '临时资产' : fallbackLabels[card.card_type]);
  const lifecycle = String(firstValue(state, ['lifecycle', 'status', 'story_status', 'state'])
    ?? firstValue(attributes, ['lifecycle', 'status'])
    ?? '未标注');

  return {
    subtype,
    lifecycle,
    goal: firstValue(state, [
      'independent_goal', 'volume_goal', 'external_goal', 'goal', 'story_function',
      'purpose', 'event_goal', 'volume_center', 'story_engine',
    ]),
    progression: firstValue(state, [
      'scheduled_movements', 'planned_actions', 'event_movements', 'progression_stages',
      'growth_stages', 'build_up', 'custody_chain', 'turning_stages',
    ]),
    connections: firstValue(state, [
      'owner_ids', 'collision_line_ids', 'collision_ids', 'participating_line_ids',
      'character_ids', 'event_slot_ids', 'active_slot_ids', 'relationship_tracks',
    ]),
    lifecycleDetail: {
      lifecycle: state.lifecycle,
      carryover: state.carryover,
      promotion_condition: state.promotion_condition,
      retirement_condition: state.retirement_condition,
      residual_effect: state.residual_effect,
      payoff: state.payoff,
      convergence_or_payoff: state.convergence_or_payoff,
    },
  };
}

export function isEcosystemCard(card: StatusCard): boolean {
  const subtype = presentCard(card).subtype;
  return [
    '故事线', '成长线', '关系弧', '实体议程', '角色议程', '势力议程', '生态议程', '关键物品弧',
    '卷物品轨迹', '大场面', '临时线索', '临时资产',
  ].includes(subtype);
}

export function cardSearchText(card: StatusCard): string {
  return `${card.card_name} ${card.summary || ''} ${card.card_id} ${JSON.stringify(card.current_state || {})}`.toLowerCase();
}
