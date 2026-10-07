import {
  BookOpenText,
  Boxes,
  Building2,
  Clapperboard,
  Gem,
  GitBranch,
  LayoutDashboard,
  Layers3,
  MapPinned,
  Network,
  Plus,
  RefreshCw,
  Scale,
  Settings2,
  Users,
} from 'lucide-react';
import type { CardType, ProjectMeta, ProjectSummary, StateData, WorkspaceView } from '../types';
import { isEcosystemCard } from '../cardPresentation';

const navItems: Array<{ id: WorkspaceView; label: string; icon: typeof LayoutDashboard; cardType?: CardType }> = [
  { id: 'pipeline', label: '生产流水线', icon: LayoutDashboard },
  { id: 'assets', label: '分层资产', icon: Layers3 },
  { id: 'ecosystem', label: '故事生态', icon: Network },
  { id: 'plot', label: '情节', icon: GitBranch, cardType: 'plot' },
  { id: 'character', label: '人物', icon: Users, cardType: 'character' },
  { id: 'scene', label: '场景', icon: MapPinned, cardType: 'scene' },
  { id: 'faction', label: '势力', icon: Building2, cardType: 'faction' },
  { id: 'item', label: '物品', icon: Gem, cardType: 'item' },
  { id: 'rule', label: '规则', icon: Scale, cardType: 'rule' },
  { id: 'chapters', label: '章节', icon: BookOpenText },
  { id: 'context', label: '上下文追踪', icon: Boxes },
  { id: 'models', label: '模型与 API', icon: Settings2 },
];

interface SidebarProps {
  projects: ProjectSummary[];
  projectId: string;
  meta: ProjectMeta | null;
  state: StateData | null;
  view: WorkspaceView;
  onProjectChange: (projectId: string) => void;
  onViewChange: (view: WorkspaceView) => void;
  onRefresh: () => void;
  onCreate: () => void;
}

export default function Sidebar({
  projects,
  projectId,
  meta,
  state,
  view,
  onProjectChange,
  onViewChange,
  onRefresh,
  onCreate,
}: SidebarProps) {
  const countFor = (item: (typeof navItems)[number]) => {
    if (item.cardType) return state?.status_cards[`${item.cardType}_cards`]?.length || 0;
    if (item.id === 'ecosystem') {
      const planned = Object.values(state?.status_cards || {}).flat().filter(isEcosystemCard).length;
      const runtime = Object.keys(state?.latest_state?.narrative_line_states || {}).length
        + Object.keys(state?.latest_state?.entity_agendas || {}).length
        + Object.keys(state?.latest_state?.asset_states || {}).length;
      return planned + runtime;
    }
    if (item.id === 'chapters') return meta?.chapter_count || 0;
    return null;
  };

  return (
    <aside className="sidebar">
      <div className="project-picker">
        <label htmlFor="project-select">当前项目</label>
        <div className="select-row">
          <select id="project-select" value={projectId} onChange={(event) => onProjectChange(event.target.value)}>
            <option value="">选择项目</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>{project.project_id}</option>
            ))}
          </select>
          <button className="icon-button" onClick={onRefresh} title="刷新项目">
            <RefreshCw size={16} />
          </button>
          <button className="icon-button" onClick={onCreate} title="新建项目">
            <Plus size={17} />
          </button>
        </div>
      </div>

      <nav className="primary-nav" aria-label="工作台导航">
        {navItems.map((item) => {
          const Icon = item.icon;
          const count = countFor(item);
          return (
            <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => onViewChange(item.id)}>
              <Icon size={17} />
              <span>{item.label}</span>
              {count !== null && <b>{count}</b>}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-summary">
        <Clapperboard size={16} />
        <div>
          <b>{meta?.run_count || 0} 次运行</b>
          <span>卡索引 v{state?.card_index_version || 0}</span>
        </div>
      </div>
    </aside>
  );
}
