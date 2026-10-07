import {
  Activity, BookMarked, Check, CheckCircle2, ChevronRight, Circle, ClipboardCheck,
  Database, Gauge, GitBranch, Layers3, ListChecks, Lock, Play, RadioTower, RotateCcw, Route,
  Settings2, ShieldCheck, Square, WandSparkles, X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { formatValue } from '../format';
import { useDraft } from '../useDraft';
import DraftStatus from './DraftStatus';
import type { ActivityEntry, RunResult, StateData, WorkflowData, WorkflowReview, WorkflowStage } from '../types';

type WorkspaceMode = 'flow' | 'review' | 'auto' | 'advanced';
type AdvancedMode = 'write' | 'sprout';

interface PipelineWorkspaceProps {
  projectId: string;
  disabled: boolean;
  running: boolean;
  runMessage: string;
  progress: number;
  lastResult: RunResult | null;
  activity: ActivityEntry[];
  state: StateData | null;
  workflow: WorkflowData | null;
  onGenerateWorkflow: (stage: string, payload: Record<string, unknown>) => void;
  onApproveWorkflow: (stagingId: string, editable: Record<string, unknown>) => void;
  onAuditWorkflow: (stagingId: string, editable: Record<string, unknown>) => void;
  onReviseWorkflow: (stagingId: string, editable: Record<string, unknown>, feedback: string) => void;
  onRejectWorkflow: (stagingId: string) => void;
  onRewindFoundation: (stepKey: string) => void;
  onAuto: (startIndex: number, maxEvents: number, onlyKey: boolean) => void;
  onWrite: (goal: string, resultTarget: string, isKey: boolean) => void;
  onApprove: (stagingId: string, draftText: string) => void;
  onReject: (stagingId: string) => void;
  onSprout: (goal: string, count: number, startIndex: number, resultTarget: string, isKey: boolean) => void;
  onStop: () => void;
}

const workspaceModes: Array<{ id: WorkspaceMode; label: string; icon: typeof ListChecks }> = [
  { id: 'flow', label: '创作流程', icon: ListChecks },
  { id: 'review', label: '审核中心', icon: ClipboardCheck },
  { id: 'auto', label: '自动执行', icon: Gauge },
  { id: 'advanced', label: '高级工具', icon: Settings2 },
];

const reviewKindLabels: Record<WorkflowReview['review_kind'], string> = {
  foundation: '作品基座', master_plan: '全书总纲', volume_plan: '卷纲与事件队列',
  event_plan: '事件展开方案', prose: '正文草稿', state_delta: '状态差异', chapter_plan: '自然切章',
  asset_edit: '分层资产微调',
};

function stageById(workflow: WorkflowData | null, id: WorkflowStage['id']) {
  return workflow?.stages.find((stage) => stage.id === id);
}

export default function PipelineWorkspace(props: PipelineWorkspaceProps) {
  const [mode, setMode] = useState<WorkspaceMode>('flow');
  const [brief, setBrief] = useState('');
  const [volumeIndex, setVolumeIndex] = useState(1);
  const [eventIndex, setEventIndex] = useState(1);
  const [autoStart, setAutoStart] = useState(1);
  const [autoMax, setAutoMax] = useState(0);
  const [autoKey, setAutoKey] = useState(false);
  const [advancedMode, setAdvancedMode] = useState<AdvancedMode>('write');
  const [goal, setGoal] = useState('');
  const [resultTarget, setResultTarget] = useState('');
  const [eventKey, setEventKey] = useState(false);
  const [sproutGoal, setSproutGoal] = useState('');
  const [sproutCount, setSproutCount] = useState(6);
  const [sproutStart, setSproutStart] = useState(1);
  const [sproutResult, setSproutResult] = useState('');
  const [sproutKey, setSproutKey] = useState(false);
  const [reviewId, setReviewId] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [legacyDraft, setLegacyDraft] = useState('');
  const previousPendingCount = useRef(0);
  const blocked = props.disabled || props.running;

  const reviews = props.workflow?.reviews || [];
  const pending = props.workflow?.pending_reviews || [];
  const selectedReview = reviews.find((review) => review.staging_id === reviewId)
    || pending[0]
    || reviews[reviews.length - 1];
  const selectedSlot = props.workflow?.event_slots[eventIndex - 1];
  const reviewBase = !selectedReview ? '' : selectedReview.review_kind === 'prose'
    ? String(selectedReview.editable.draft_text || '')
    : (selectedReview.review_kind === 'master_plan' && selectedReview.master_step)
      || (selectedReview.review_kind === 'volume_plan' && selectedReview.volume_step)
      || (selectedReview.review_kind === 'event_plan' && selectedReview.event_plan_step)
      ? JSON.stringify(selectedReview.editable.content, null, 2)
      : JSON.stringify(selectedReview.editable, null, 2);
  const draftKey = selectedReview?.status === 'pending'
    ? `${props.projectId}:review:${selectedReview.staging_id}:${selectedReview.revision_count || 0}` : '';
  const reviewDraft = useDraft(draftKey, reviewBase);
  const feedbackDraft = useDraft(draftKey ? `${draftKey}:feedback` : '', String(selectedReview?.suggested_feedback || ''));
  const reviewText = reviewDraft.text;
  const setReviewText = reviewDraft.change;
  const revisionFeedback = feedbackDraft.text;
  const setRevisionFeedback = feedbackDraft.change;


  useEffect(() => {
    const next = props.workflow?.next_event_index;
    if (next && next > 0) setEventIndex(next);
  }, [props.workflow?.next_event_index]);

  useEffect(() => {
    const activeVolume = props.workflow?.volume_plan_progress;
    if (activeVolume && activeVolume.approved_count > 0) {
      setVolumeIndex(activeVolume.volume_index);
    }
  }, [
    props.workflow?.volume_plan_progress.volume_index,
    props.workflow?.volume_plan_progress.approved_count,
  ]);

  useEffect(() => {
    const savedBrief = props.workflow?.foundation_progress.brief || '';
    if (savedBrief) setBrief(savedBrief);
    else if (props.workflow?.foundation_progress.approved_count === 0) setBrief('');
  }, [
    props.workflow?.foundation_progress.brief,
    props.workflow?.foundation_progress.approved_count,
  ]);

  useEffect(() => { setReviewError(''); }, [selectedReview?.staging_id]);

  useEffect(() => {
    if (pending.length && mode === 'flow') setMode('review');
  }, [pending.length]);

  useEffect(() => {
    const previous = previousPendingCount.current;
    previousPendingCount.current = pending.length;
    if (previous > 0 && pending.length === 0 && mode === 'review') setMode('flow');
  }, [pending.length, mode]);

  useEffect(() => {
    if (props.lastResult?.review_required) setLegacyDraft(String(props.lastResult.draft_text || ''));
  }, [props.lastResult]);

  const currentReviewEditable = () => {
    if (!selectedReview) throw new Error('没有选中的审核稿');
    return selectedReview.review_kind === 'prose'
      ? { ...selectedReview.editable, draft_text: reviewText }
      : (selectedReview.review_kind === 'master_plan' && selectedReview.master_step)
        || (selectedReview.review_kind === 'volume_plan' && selectedReview.volume_step)
        || (selectedReview.review_kind === 'event_plan' && selectedReview.event_plan_step)
        ? { ...selectedReview.editable, content: JSON.parse(reviewText) as unknown }
        : JSON.parse(reviewText) as Record<string, unknown>;
  };

  const approveReview = () => {
    if (!selectedReview) return;
    try {
      const editable = currentReviewEditable();
      setReviewError('');
      props.onApproveWorkflow(selectedReview.staging_id, editable);
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : String(error));
    }
  };

  const reviseReview = () => {
    if (!selectedReview) return;
    try {
      const editable = currentReviewEditable();
      setReviewError('');
      props.onReviseWorkflow(selectedReview.staging_id, editable, revisionFeedback.trim());
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : String(error));
    }
  };

  const auditReview = () => {
    if (!selectedReview) return;
    try {
      const editable = currentReviewEditable();
      setReviewError('');
      props.onAuditWorkflow(selectedReview.staging_id, editable);
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <section className="workspace-view pipeline-workspace">
      <header className="workspace-heading">
        <div><span className="eyebrow">Production</span><h1>生产流水线</h1></div>
        {props.running && <button className="danger-button" onClick={props.onStop}><Square size={15} />停止</button>}
      </header>

      <div className="mode-tabs workflow-mode-tabs">
        {workspaceModes.map((item) => {
          const Icon = item.icon;
          const badge = item.id === 'review' ? pending.length : 0;
          return <button key={item.id} className={mode === item.id ? 'active' : ''} onClick={() => setMode(item.id)}><Icon size={16} />{item.label}{badge > 0 && <b>{badge}</b>}</button>;
        })}
      </div>

      <WorkflowRail stages={props.workflow?.stages || []} />

      {mode === 'flow' && (
        <FlowWorkspace
          workflow={props.workflow}
          brief={brief}
          setBrief={setBrief}
          volumeIndex={volumeIndex}
          setVolumeIndex={setVolumeIndex}
          eventIndex={eventIndex}
          setEventIndex={setEventIndex}
          selectedSlot={selectedSlot}
          blocked={blocked}
          onGenerate={props.onGenerateWorkflow}
          onOpenReview={() => setMode('review')}
        />
      )}

      {mode === 'review' && (
        <>
        <DraftStatus before={reviewBase} after={reviewText} savedAt={reviewDraft.savedAt} warning={reviewDraft.warning || feedbackDraft.warning} conflict={reviewDraft.conflict} />
        <ReviewWorkspace
          reviews={reviews}
          selected={selectedReview}
          reviewText={reviewText}
          revisionFeedback={revisionFeedback}
          reviewError={reviewError}
          runMessage={props.runMessage}
          blocked={blocked}
          onSelect={setReviewId}
          onChange={setReviewText}
          onFeedbackChange={setRevisionFeedback}
          onAudit={auditReview}
          onRevise={reviseReview}
          onApprove={approveReview}
          onReject={() => selectedReview && props.onRejectWorkflow(selectedReview.staging_id)}
          onRewind={props.onRewindFoundation}
        />
        </>
      )}

      {mode === 'auto' && (
        <div className="pipeline-form compact-flow-form">
          <div className="field-grid"><label className="field"><span>起始事件</span><input type="number" min={1} value={autoStart} onChange={(event) => setAutoStart(Number(event.target.value))} /></label><label className="field"><span>最多执行事件</span><input type="number" min={0} value={autoMax} onChange={(event) => setAutoMax(Number(event.target.value))} /></label></div>
          <label className="toggle-row"><input type="checkbox" checked={autoKey} onChange={(event) => setAutoKey(event.target.checked)} /><span>仅执行关键事件</span></label>
          <div className="form-actions"><button className="primary-button" disabled={blocked || !props.workflow?.event_slots.length} onClick={() => props.onAuto(autoStart, autoMax, autoKey)}><Play size={16} />按已批准卷纲执行</button></div>
        </div>
      )}

      {mode === 'advanced' && (
        <AdvancedTools
          mode={advancedMode} setMode={setAdvancedMode} blocked={blocked}
          goal={goal} setGoal={setGoal} resultTarget={resultTarget} setResultTarget={setResultTarget} eventKey={eventKey} setEventKey={setEventKey}
          sproutGoal={sproutGoal} setSproutGoal={setSproutGoal} sproutCount={sproutCount} setSproutCount={setSproutCount} sproutStart={sproutStart} setSproutStart={setSproutStart} sproutResult={sproutResult} setSproutResult={setSproutResult} sproutKey={sproutKey} setSproutKey={setSproutKey}
          onWrite={props.onWrite} onSprout={props.onSprout}
        />
      )}

      {(props.running || props.runMessage) && (
        <div className="run-strip"><div><b>{props.running ? '运行中' : '最近运行'}</b><span>{props.runMessage || '正在准备任务'}</span></div><div className="progress-track"><span style={{ width: `${Math.max(2, props.progress)}%` }} /></div><em>{Math.round(props.progress)}%</em></div>
      )}

      {Boolean(props.lastResult?.review_required && props.lastResult?.staging_id) && mode === 'advanced' && (
        <section className="review-panel">
          <header><div><span className="eyebrow">Advanced review</span><h2>补写草稿待审核</h2></div><div className="review-actions"><button className="secondary-button" disabled={blocked} onClick={() => props.onReject(String(props.lastResult?.staging_id))}><X size={16} />拒绝</button><button className="primary-button" disabled={blocked || !legacyDraft.trim()} onClick={() => props.onApprove(String(props.lastResult?.staging_id), legacyDraft)}><Check size={16} />提交补写</button></div></header>
          <textarea className="review-draft" value={legacyDraft} onChange={(event) => setLegacyDraft(event.target.value)} aria-label="补写事件正文" />
        </section>
      )}

      {props.lastResult && <RunOverview result={props.lastResult} state={props.state} />}
      {props.lastResult?.execution_report && <ExecutionDetails result={props.lastResult} />}
    </section>
  );
}

function WorkflowRail({ stages }: { stages: WorkflowStage[] }) {
  return <section className="workflow-rail"><header><Layers3 size={15} /><h2>审核链</h2></header><div>{stages.map((stage) => { const Icon = stage.status === 'approved' ? CheckCircle2 : stage.status === 'locked' ? Lock : Circle; return <article className={stage.status} key={stage.id}><Icon size={14} /><span>{stage.label}</span><em>{stage.status === 'approved' ? '已批准' : stage.status === 'pending' ? '待审核' : stage.status === 'available' ? '可生成' : '未解锁'}</em></article>; })}</div></section>;
}

interface FlowWorkspaceProps {
  workflow: WorkflowData | null;
  brief: string; setBrief: (value: string) => void;
  volumeIndex: number; setVolumeIndex: (value: number) => void;
  eventIndex: number; setEventIndex: (value: number) => void;
  selectedSlot?: Record<string, unknown>;
  blocked: boolean;
  onGenerate: (stage: string, payload: Record<string, unknown>) => void;
  onOpenReview: () => void;
}

function FlowWorkspace(props: FlowWorkspaceProps) {
  const foundation = stageById(props.workflow, 'foundation');
  const master = stageById(props.workflow, 'master_plan');
  const volume = stageById(props.workflow, 'volume_plan');
  const foundationProgress = props.workflow?.foundation_progress;
  const masterProgress = props.workflow?.master_plan_progress;
  const volumeProgress = props.workflow?.volume_plan_progress;
  const nextFoundationStep = foundationProgress?.steps.find((step) => step.status === 'available');
  const nextMasterStep = masterProgress?.steps.find((step) => step.status === 'available');
  const nextVolumeStep = volumeProgress?.steps.find((step) => step.status === 'available');
  const selectedEventId = String(props.selectedSlot?.slot_id || '');
  const eventPlanProgress = selectedEventId
    ? props.workflow?.event_plan_progress?.[selectedEventId]
    : undefined;
  const nextEventPlanStep = eventPlanProgress?.steps.find((step) => step.status === 'available');
  const isCurrentEvent = props.eventIndex === props.workflow?.next_event_index;
  const isCompletedEvent = props.eventIndex <= (props.workflow?.completed_events || 0);
  const pending = props.workflow?.pending_reviews || [];
  if (pending.length) return <div className="workflow-next"><ClipboardCheck size={22} /><div><b>{pending[0].title}</b><span>当前文件尚未批准；批准或驳回前不会生成后续文件</span></div><button className="primary-button" onClick={props.onOpenReview}>进入审核<ChevronRight size={15} /></button></div>;

  if (foundation?.status !== 'approved') return (
    <section className="foundation-flow">
      <header>
        <div><span className="eyebrow">Foundation files</span><h2>作品基座逐文件审核</h2></div>
        <strong>{foundationProgress?.approved_count || 0} / {foundationProgress?.total || 8} 已批准</strong>
      </header>
      <div className="foundation-stepper">
        {(foundationProgress?.steps || []).map((step) => {
          const Icon = step.status === 'approved' ? CheckCircle2 : step.status === 'locked' ? Lock : Circle;
          return <article className={step.status} key={step.id}><Icon size={15} /><b>{step.index}</b><span>{step.label}</span><em>{step.status === 'approved' ? '已批准' : step.status === 'pending' ? '待审核' : step.status === 'available' ? '当前文件' : '等待前序'}</em></article>;
        })}
      </div>
      <div className="pipeline-form foundation-form">
        <label className="field wide"><span>创作意图</span><textarea value={props.brief} onChange={(event) => props.setBrief(event.target.value)} placeholder="题材、核心体验、主角、主要矛盾、世界边界与篇幅预期" /></label>
        <p className="foundation-rule">每次只生成一个文件。你修改并批准当前文件后，下一个文件才会读取该批准版本并解锁。</p>
        <div className="form-actions"><button className="primary-button" disabled={props.blocked || !props.brief.trim() || !nextFoundationStep} onClick={() => props.onGenerate('foundation', { brief: props.brief.trim() })}><WandSparkles size={16} />{nextFoundationStep ? `生成第 ${nextFoundationStep.index}/${foundationProgress?.total || 8} 步：${nextFoundationStep.label}` : '等待当前文件审核'}</button></div>
      </div>
    </section>
  );
  if (master?.status !== 'approved') return (
    <section className="foundation-flow master-plan-flow">
      <header>
        <div><span className="eyebrow">Master plan files</span><h2>全书总纲与资产逐文件审核</h2></div>
        <strong>{masterProgress?.approved_count || 0} / {masterProgress?.total || 0} 已批准</strong>
      </header>
      <div className="foundation-stepper master-stepper">
        {(masterProgress?.steps || []).map((step) => {
          const Icon = step.status === 'approved' ? CheckCircle2 : step.status === 'locked' ? Lock : Circle;
          return <article className={step.status} key={step.id}><Icon size={15} /><b>{step.index}</b><span>{step.label}</span><em>{step.status === 'approved' ? '已批准' : step.status === 'pending' ? '待审核' : step.status === 'available' ? `当前文件 · ${step.max_tokens.toLocaleString('zh-CN')} tokens` : '等待前序'}</em></article>;
        })}
      </div>
      <div className="pipeline-form foundation-form master-plan-form">
        <p className="foundation-rule">每次只生成并审核一个逻辑文件；人物成长弧按角色拆开，群像关系弧按核心角色对拆开，故事线、关键物品和大场面先生成索引，再逐条生成审核。已批准文件立即保存为断点，后续失败不会让它重新生成。</p>
        <div className="master-budget-summary"><span>丰富度档位 <b>{masterProgress?.complexity_level || 'medium'}</b></span><span>本阶段总输出预算 <b>{(masterProgress?.total_output_budget || 0).toLocaleString('zh-CN')} tokens</b></span></div>
        <div className="form-actions"><button className="primary-button" disabled={props.blocked || !nextMasterStep} onClick={() => props.onGenerate('master_plan', {})}><WandSparkles size={16} />{nextMasterStep ? `生成第 ${nextMasterStep.index}/${masterProgress?.total || 0} 步：${nextMasterStep.label}` : '等待当前文件审核'}</button></div>
      </div>
    </section>
  );
  if (volume?.status !== 'approved') return (
    <section className="foundation-flow master-plan-flow volume-plan-flow">
      <header>
        <div><span className="eyebrow">Volume plan files</span><h2>卷纲与资产逐文件审核</h2></div>
        <strong>{volumeProgress?.approved_count || 0} / {volumeProgress?.total || 12} 已批准</strong>
      </header>
      <div className="foundation-stepper master-stepper">
        {(volumeProgress?.steps || []).map((step) => {
          const Icon = step.status === 'approved' ? CheckCircle2 : step.status === 'locked' ? Lock : Circle;
          return <article className={step.status} key={step.id}><Icon size={15} /><b>{step.index}</b><span>{step.label}</span><em>{step.status === 'approved' ? '已批准' : step.status === 'pending' ? '待审核' : step.status === 'available' ? `当前文件 · ${step.max_tokens.toLocaleString('zh-CN')} tokens` : '等待前序'}</em></article>;
        })}
      </div>
      <div className="pipeline-form foundation-form master-plan-form">
        <label className="field compact"><span>卷序</span><input type="number" min={1} value={props.volumeIndex} disabled={(volumeProgress?.approved_count || 0) > 0} onChange={(event) => props.setVolumeIndex(Number(event.target.value))} /></label>
        <p className="foundation-rule">每次只生成并审核一个卷级逻辑文件。地图排期和逐事件设计分别按8个槽位分批；批准后立即保存为断点，后续失败只重试当前文件。</p>
        <div className="master-budget-summary"><span>目标事件 <b>{volumeProgress?.events_per_volume || 30}</b></span><span>本阶段总输出预算 <b>{(volumeProgress?.total_output_budget || 0).toLocaleString('zh-CN')} tokens</b></span></div>
        <div className="form-actions"><button className="primary-button" disabled={props.blocked || !nextVolumeStep} onClick={() => props.onGenerate('volume_plan', { volume_index: props.volumeIndex })}><BookMarked size={16} />{nextVolumeStep ? `生成第 ${nextVolumeStep.index}/${volumeProgress?.total || 12} 步：${nextVolumeStep.label}` : '等待当前文件审核'}</button></div>
      </div>
    </section>
  );

  return (
    <section className="event-queue-workspace">
      <header><div><span className="eyebrow">Model queue</span><h2>卷事件队列</h2></div><div className="authority-review-actions"><button className="secondary-button" disabled={props.blocked} onClick={() => props.onGenerate('master_plan', { from_current: true })}>微调总纲</button><button className="secondary-button" disabled={props.blocked} onClick={() => props.onGenerate('volume_plan', { from_current: true })}>微调卷纲</button><span>{props.workflow?.completed_events || 0} / {props.workflow?.event_slots.length || 0}</span></div></header>
      <div className="event-queue-layout">
        <div className="event-slot-list">{(props.workflow?.event_slots || []).map((slot, index) => <button key={String(slot.slot_id || index)} className={props.eventIndex === index + 1 ? 'active' : ''} onClick={() => props.setEventIndex(index + 1)}><b>{index + 1}</b><span>{String(slot.event_goal || slot.title || slot.slot_id || `事件 ${index + 1}`)}</span><em>{index < (props.workflow?.completed_events || 0) ? '已完成' : index + 1 === props.workflow?.next_event_index ? '下一事件' : '待执行'}</em></button>)}</div>
        <article className="event-slot-detail">
          <span className="eyebrow">事件 {props.eventIndex}</span>
          <h3>{String(props.selectedSlot?.event_goal || '选择事件')}</h3>
          <DataRow label="结果目标" value={props.selectedSlot?.result_target} />
          <DataRow label="冲突形式" value={props.selectedSlot?.conflict_form} />
          <DataRow label="关键交付" value={props.selectedSlot?.key_deliverables} />
          <DataRow label="允许变化" value={props.selectedSlot?.allowed_delta} />
          <DataRow label="禁止变化" value={props.selectedSlot?.forbidden_delta} />
          <section className="event-plan-files">
            <header>
              <div><span className="eyebrow">Event plan files</span><h4>事件展开逐文件审核</h4></div>
              <strong>{eventPlanProgress?.approved_count || 0} / {eventPlanProgress?.total || 5} 已批准</strong>
            </header>
            <div className="foundation-stepper event-plan-stepper">
              {(eventPlanProgress?.steps || []).map((step) => {
                const Icon = step.status === 'approved' ? CheckCircle2 : step.status === 'locked' ? Lock : Circle;
                return <article className={step.status} key={step.id}><Icon size={14} /><b>{step.index}</b><span>{step.label}</span><em>{step.status === 'approved' ? '已批准' : step.status === 'pending' ? '待审核' : step.status === 'available' ? `${step.max_tokens.toLocaleString('zh-CN')} tokens` : '等待前序'}</em></article>;
              })}
            </div>
            <p className="foundation-rule">一次只生成、修改并批准一个文件。五个文件全部保存后，正文按钮才会解锁；正文失败只重试正文，不会重做这些规划。</p>
            <div className="master-budget-summary"><span>规划输出预算 <b>{(eventPlanProgress?.total_output_budget || 0).toLocaleString('zh-CN')} tokens</b></span><span>上下文 <b>确定性编译，不做模型摘要</b></span></div>
          </section>
          <button
            className="primary-button"
            disabled={props.blocked || !props.selectedSlot || !isCurrentEvent || isCompletedEvent || (!nextEventPlanStep && !eventPlanProgress?.complete)}
            onClick={() => props.onGenerate(
              eventPlanProgress?.complete ? 'prose' : 'event_plan',
              { event_index: props.eventIndex, volume_index: props.volumeIndex },
            )}
          >
            <WandSparkles size={16} />
            {isCompletedEvent
              ? '事件已完成'
              : !isCurrentEvent
                ? '请先完成当前事件'
                : eventPlanProgress?.complete
                  ? '按已批准规划生成正文草稿'
                  : nextEventPlanStep
                    ? `生成第 ${nextEventPlanStep.index}/${eventPlanProgress?.total || 5} 步：${nextEventPlanStep.label}`
                    : '准备事件规划'}
          </button>
        </article>
      </div>
    </section>
  );
}

function NextStage({ title, action, blocked, onClick }: { title: string; action: string; blocked: boolean; onClick: () => void }) {
  return <div className="workflow-next"><Circle size={22} /><div><b>{title}</b><span>当前阶段可生成</span></div><button className="primary-button" disabled={blocked} onClick={onClick}><WandSparkles size={15} />{action}</button></div>;
}

function ReviewWorkspace({
  reviews, selected, reviewText, revisionFeedback, reviewError, runMessage, blocked,
  onSelect, onChange, onFeedbackChange, onAudit, onRevise, onApprove, onReject, onRewind,
}: {
  reviews: WorkflowReview[];
  selected?: WorkflowReview;
  reviewText: string;
  revisionFeedback: string;
  reviewError: string;
  runMessage: string;
  blocked: boolean;
  onSelect: (id: string) => void;
  onChange: (value: string) => void;
  onFeedbackChange: (value: string) => void;
  onAudit: () => void;
  onRevise: () => void;
  onApprove: () => void;
  onReject: () => void;
  onRewind: (stepKey: string) => void;
}) {
  if (!reviews.length) return <div className="empty-state"><ClipboardCheck size={24} /><b>暂无审核任务</b></div>;
  const selectedFile = record(selected?.editable.content);
  const selectedPrewrite = record(selectedFile.prewrite_check);
  const failedPrewrite = selected?.review_kind === 'event_plan'
    && selected.event_plan_step === 'prewrite_assets'
    && selectedPrewrite.passed === false;
  const prosePrewrite = record(selected?.prewrite_check);
  const nestedProseChecks = record(prosePrewrite.checks);
  const proseChecks = Object.keys(nestedProseChecks).length ? nestedProseChecks : prosePrewrite;
  const failedProsePlan = selected?.review_kind === 'prose'
    && (prosePrewrite.passed === false
      || ['causality', 'timeline', 'map', 'knowledge_boundary', 'entity_agency', 'line_lifecycle', 'asset_coverage', 'non_checklist_rhythm']
        .some((key) => proseChecks[key] === false));
  const failedProseQuality = selected?.review_kind === 'prose'
    && selected.quality_report?.passed === false;
  const failedPlanningGate = failedPrewrite || failedProsePlan;
  const supportsRevision = selected?.status === 'pending'
    && !failedPlanningGate
    && (selected.review_kind === 'event_plan' || selected.review_kind === 'prose');
  const revisionHistory = selected?.revision_history || [];
  const auditHistory = selected?.audit_history || [];
  const latestAudit = auditHistory.length ? auditHistory[auditHistory.length - 1] : undefined;
  const auditedEditable = record(latestAudit?.audited_editable);
  const auditedText = selected?.review_kind === 'prose'
    ? String(auditedEditable.draft_text || '')
    : selected?.review_kind === 'event_plan'
      ? JSON.stringify(auditedEditable.content, null, 2)
      : JSON.stringify(auditedEditable, null, 2);
  const auditMatchesEditor = Boolean(selected?.current_audit && latestAudit && auditedText === reviewText);
  const currentAudit = auditMatchesEditor ? selected?.current_audit : null;
  const auditIsStale = Boolean(latestAudit && !currentAudit);
  const savedReviewText = selected?.review_kind === 'prose'
    ? String(selected.editable.draft_text || '')
    : selected?.review_kind === 'event_plan'
      ? JSON.stringify(selected.editable.content, null, 2)
      : JSON.stringify(selected?.editable || {}, null, 2);
  const editorChanged = savedReviewText !== reviewText;
  const stateDeltaFailed = selected?.review_kind === 'prose'
    && (runMessage.includes('状态差异提取') || runMessage.includes('observed_delta'));
  const qualityMetrics = record(selected?.quality_report?.metrics);
  const qualityActual = Number(qualityMetrics.char_count || 0);
  const qualityTarget = Number(qualityMetrics.target_chars || record(selected?.budget_report).total_chars || 0);
  const qualityScore = Number(selected?.quality_report?.score || 0);
  const qualityThreshold = Number(selected?.quality_report?.threshold || 72);
  const qualityIssues = selected?.quality_report?.issues || [];
  const machineStatus = editorChanged
    ? { className: 'stale', label: '正文已修改，批准时重新检查' }
    : selected?.quality_report?.passed === true
      ? { className: 'pass', label: `通过 ${qualityScore}/${qualityThreshold}` }
      : selected?.quality_report?.passed === false
        ? { className: 'fail', label: `未通过 ${qualityScore}/${qualityThreshold}` }
        : { className: 'pending', label: '未检查' };
  const aiStatus = currentAudit?.verdict === 'pass'
    ? { className: 'pass', label: '通过' }
    : currentAudit
      ? { className: 'fail', label: '待修改' }
      : auditIsStale
        ? { className: 'stale', label: '正文已变化，旧结论失效' }
        : { className: 'pending', label: '未执行' };
  const approvalLabel = stateDeltaFailed
    ? '重试生成状态差异'
    : selected?.review_kind === 'asset_edit'
      ? '批准并写回权威文件'
      : selected?.review_kind === 'foundation' && selected.foundation_step
        ? '批准并解锁下一文件'
        : selected?.review_kind === 'master_plan' && selected.master_step
          ? '批准并解锁下一文件'
        : selected?.review_kind === 'volume_plan' && selected.volume_step
          ? '批准并解锁下一文件'
        : selected?.review_kind === 'event_plan' && selected.event_plan_step
          ? '批准并保存当前规划文件'
        : failedProseQuality
          ? '检查修改后正文'
        : '批准正文并生成状态差异';
  const safetyNote = stateDeltaFailed
    ? '正文机械质量已经通过；上次失败发生在批准后的状态差异提取。正文和 AI 审核结果都已保留，可直接重试，不需要重新生成正文。'
    : failedProsePlan
    ? '这份正文不能批准：它依据的正文前检查实际仍有失败项。点击“按检查意见退回重做场景方案”会保留前 1–3 步，撤销错误的第 4–5 步和当前正文。'
    : failedPrewrite
    ? '这不是可批准结果：正文前检查发现连续场景方案仍有结构问题。点击“按检查意见退回重做场景方案”会保留前 1–3 步，把 repair_instructions 带回第 4 步；不会生成正文。'
    : failedProseQuality
    ? `当前正文质量检查未通过：有效字符 ${qualityActual.toLocaleString('zh-CN')} / 目标 ${qualityTarget.toLocaleString('zh-CN')}${qualityIssues.length ? `；${qualityIssues.join('；')}` : ''}。可以继续编辑后点击“检查修改后正文”，或驳回并重新生成。`
    : selected?.review_kind === 'asset_edit'
    ? '这是单个逻辑文件的暂存修改。批准时会检查权威版本并合并回所属文件；批准前不会改变当前设定。'
    : selected?.review_kind === 'foundation' && selected.foundation_step
      ? '这张审核单只包含当前一个基座文件。你可以直接修改；只有批准后的版本会成为权威文件，并作为下一个文件的生成输入。'
      : selected?.review_kind === 'master_plan' && selected.master_step
        ? `这张审核单只拥有当前全书规划文件。批准后立即保存为断点并解锁下一文件；本次输出上限为 ${(selected.max_tokens || 0).toLocaleString('zh-CN')} tokens。`
      : selected?.review_kind === 'volume_plan' && selected.volume_step
        ? `这张审核单只拥有当前卷级文件。批准后立即写入第 ${selected.volume_index || 1} 卷断点并解锁下一文件；本次输出上限为 ${(selected.max_tokens || 0).toLocaleString('zh-CN')} tokens。`
      : selected?.review_kind === 'event_plan' && selected.event_plan_step
        ? `这张审核单只包含事件 ${selected.event_index || 1} 的当前规划文件。批准后会原子保存到卷级权威文件并解锁下一步，不会生成正文；本次输出上限为 ${(selected.max_tokens || 0).toLocaleString('zh-CN')} tokens。`
      : '这是模型生成的暂存稿。可以直接修改；批准前不会影响当前设定与已发布章节。';
  return (
    <div className="review-workspace">
      <aside>
        {[...reviews].reverse().map((review) => (
          <button
            key={review.staging_id}
            className={selected?.staging_id === review.staging_id ? 'active' : ''}
            onClick={() => onSelect(review.staging_id)}
          >
            <StatusIcon status={review.status} />
            <span><b>{review.title}</b><small>{reviewKindLabels[review.review_kind]}</small></span>
            <em>{review.status === 'pending' ? '待审核' : review.status === 'approved' ? '已批准' : '已驳回'}</em>
          </button>
        ))}
      </aside>
      {selected && (
        <section>
          <header>
            <div>
              <span className="eyebrow">
                {reviewKindLabels[selected.review_kind]}
                {selected.step_index && selected.step_total ? ` · ${selected.step_index}/${selected.step_total}` : ''}
              </span>
              <h2>{selected.title}</h2>
            </div>
            {selected.status === 'pending' ? (
              <div className="review-actions">
                <button className={failedPlanningGate ? 'primary-button' : 'secondary-button'} disabled={blocked} onClick={onReject}>
                  {failedPlanningGate ? <RotateCcw size={15} /> : <X size={15} />}
                  {failedPlanningGate ? '按检查意见退回重做场景方案' : '驳回'}
                </button>
                {!failedPlanningGate && (
                  <button className="primary-button" disabled={blocked || !reviewText.trim()} onClick={onApprove}>
                    <Check size={15} />{approvalLabel}
                  </button>
                )}
              </div>
            ) : selected.status === 'approved' && selected.review_kind === 'foundation' && selected.foundation_step ? (
              <div className="review-actions">
                <button className="secondary-button" disabled={blocked} onClick={() => onRewind(selected.foundation_step!)}>
                  <RotateCcw size={15} />从此文件重新生成
                </button>
              </div>
            ) : null}
          </header>
          <div className="review-safety-note"><ShieldCheck size={15} /><span>{safetyNote}</span></div>
          {selected.review_kind === 'prose' && (
            <div className="review-stage-status" aria-label="正文审核与状态提取进度">
              <span className={machineStatus.className}><b>机械质量</b><em>{machineStatus.label}</em></span>
              <span className={aiStatus.className}><b>AI 审核</b><em>{aiStatus.label}</em></span>
              <span className={stateDeltaFailed ? 'fail' : 'pending'}>
                <b>状态差异</b><em>{stateDeltaFailed ? '提取失败，可重试' : '等待正文批准'}</em>
              </span>
            </div>
          )}
          {supportsRevision && (
            <div className="review-revision-box">
              <div className="review-audit-trigger">
                <span>
                  <b>第 1 步：AI 审核当前完整稿</b>
                  <small>只生成问题、原文锚点和修改指令，不会改动稿件。</small>
                </span>
                <button className="secondary-button" disabled={blocked || !reviewText.trim()} onClick={onAudit}>
                  <ClipboardCheck size={15} />{currentAudit || auditIsStale ? '重新审核当前稿' : 'AI审核当前稿'}
                </button>
              </div>
              {auditIsStale && <div className="review-audit-stale">正文已经变化，上一份 AI 审核仅保留在历史中，不再代表当前稿。</div>}
              {currentAudit && (
                <details className={`review-audit-result ${currentAudit.verdict}`} open={currentAudit.verdict !== 'pass'}>
                  <summary>
                    <b>{currentAudit.verdict === 'pass' ? '审核通过' : `发现 ${currentAudit.issues.length} 项问题`}</b>
                    <span>{currentAudit.summary}</span>
                  </summary>
                  <div>
                    {currentAudit.strengths.length > 0 && (
                      <p><strong>必须保留：</strong>{currentAudit.strengths.join('；')}</p>
                    )}
                    {currentAudit.issues.map((issue, index) => (
                      <article key={`${issue.location_anchor}-${index}`}>
                        <header><b>{index + 1}. {issue.category}</b><em>{issue.severity}</em></header>
                        <p><strong>原文锚点：</strong>{issue.location_anchor}</p>
                        <p><strong>问题：</strong>{issue.problem}</p>
                        <p><strong>依据：</strong>{issue.authority_basis}</p>
                        <p><strong>修改指令：</strong>{issue.revision_instruction}</p>
                      </article>
                    ))}
                  </div>
                </details>
              )}
              <label>
                <span>第 2 步：确认或微调修改意见</span>
                <textarea
                  value={revisionFeedback}
                  onChange={(event) => onFeedbackChange(event.target.value)}
                  placeholder="例如：保留现有场景，只修正抽奖积分、绑定时间和冷却规则三处矛盾；不要改动人物语气与结尾。"
                  maxLength={8000}
                />
              </label>
              <div>
                <small>审核意见会自动填入这里；你确认后，模型才会在当前稿上定向修改。</small>
                <button
                  className="secondary-button"
                  disabled={blocked || !reviewText.trim() || !revisionFeedback.trim()}
                  onClick={onRevise}
                >
                  <WandSparkles size={15} />根据意见修改当前稿
                </button>
              </div>
            </div>
          )}
          {reviewError && <div className="editor-error">{reviewError}</div>}
          {revisionHistory.length > 0 && (
            <details className="revision-history">
              <summary>定向修订历史（{revisionHistory.length}）</summary>
              <div>
                {[...revisionHistory].reverse().map((entry) => (
                  <article key={`${entry.revision_no}-${entry.created_at}`}>
                    <b>第 {entry.revision_no} 次</b>
                    <time>{new Date(entry.created_at).toLocaleString('zh-CN')}</time>
                    <p><strong>审核意见：</strong>{entry.feedback}</p>
                    <p><strong>修改摘要：</strong>{entry.change_summary}</p>
                    {entry.preserved_summary && <p><strong>保留内容：</strong>{entry.preserved_summary}</p>}
                  </article>
                ))}
              </div>
            </details>
          )}
          <textarea
            className={selected.review_kind === 'prose' ? 'workflow-editor prose-editor' : 'workflow-editor'}
            value={reviewText}
            onChange={(event) => onChange(event.target.value)}
            readOnly={selected.status !== 'pending'}
            spellCheck={selected.review_kind === 'prose'}
          />
        </section>
      )}
    </div>
  );
}

function StatusIcon({ status }: { status: WorkflowReview['status'] }) {
  return status === 'approved' ? <CheckCircle2 size={15} /> : status === 'rejected' ? <X size={15} /> : <Circle size={15} />;
}

function AdvancedTools(props: { mode: AdvancedMode; setMode: (value: AdvancedMode) => void; blocked: boolean; goal: string; setGoal: (v: string) => void; resultTarget: string; setResultTarget: (v: string) => void; eventKey: boolean; setEventKey: (v: boolean) => void; sproutGoal: string; setSproutGoal: (v: string) => void; sproutCount: number; setSproutCount: (v: number) => void; sproutStart: number; setSproutStart: (v: number) => void; sproutResult: string; setSproutResult: (v: string) => void; sproutKey: boolean; setSproutKey: (v: boolean) => void; onWrite: PipelineWorkspaceProps['onWrite']; onSprout: PipelineWorkspaceProps['onSprout'] }) {
  return <><div className="advanced-tabs"><button className={props.mode === 'write' ? 'active' : ''} onClick={() => props.setMode('write')}>补写事件</button><button className={props.mode === 'sprout' ? 'active' : ''} onClick={() => props.setMode('sprout')}>根事件干预</button></div><div className="pipeline-form compact-flow-form">{props.mode === 'write' ? <><label className="field wide"><span>补写目标</span><textarea value={props.goal} onChange={(event) => props.setGoal(event.target.value)} /></label><label className="field"><span>结果目标</span><input value={props.resultTarget} onChange={(event) => props.setResultTarget(event.target.value)} /></label><label className="toggle-row"><input type="checkbox" checked={props.eventKey} onChange={(event) => props.setEventKey(event.target.checked)} /><span>关键事件</span></label><div className="form-actions"><button className="primary-button" disabled={props.blocked || !props.goal.trim()} onClick={() => props.onWrite(props.goal.trim(), props.resultTarget.trim(), props.eventKey)}><WandSparkles size={16} />生成补写草稿</button></div></> : <><label className="field wide"><span>人工根事件</span><textarea value={props.sproutGoal} onChange={(event) => props.setSproutGoal(event.target.value)} /></label><div className="field-grid"><label className="field"><span>最大事件数</span><input type="number" min={1} max={12} value={props.sproutCount} onChange={(event) => props.setSproutCount(Number(event.target.value))} /></label><label className="field"><span>起始事件序号</span><input type="number" min={1} value={props.sproutStart} onChange={(event) => props.setSproutStart(Number(event.target.value))} /></label></div><label className="field"><span>结果目标</span><input value={props.sproutResult} onChange={(event) => props.setSproutResult(event.target.value)} /></label><label className="toggle-row"><input type="checkbox" checked={props.sproutKey} onChange={(event) => props.setSproutKey(event.target.checked)} /><span>按关键事件体量展开</span></label><div className="form-actions"><button className="primary-button" disabled={props.blocked || !props.sproutGoal.trim()} onClick={() => props.onSprout(props.sproutGoal.trim(), props.sproutCount, props.sproutStart, props.sproutResult.trim(), props.sproutKey)}><GitBranch size={16} />执行人工干预</button></div></>}</div></>;
}

function RunOverview({ result, state }: { result: RunResult; state: StateData | null }) {
  const route = record(result.execution_report?.event_route);
  return <div className="result-band pipeline-result-band"><Metric label="事件" value={result.event_id || '批量任务'} /><Metric label="正文" value={`${Number(result.word_count || 0).toLocaleString('zh-CN')} 字`} /><Metric label="叙事体量" value={String(route.narrative_weight || '未路由')} /><Metric label="激活故事线" value={values(route.active_line_ids).length} /><Metric label="读取状态卡" value={result.context_summary?.cards?.length ?? state?.latest_context?.cards.length ?? 0} /><Metric label="场景" value={result.execution_report?.scene_plan?.length ?? 0} /><Metric label="自然切章" value={result.chapters_generated ?? 0} /><Metric label="正文质量" value={result.quality_report?.score ?? '未评分'} /></div>;
}

function Metric({ label, value }: { label: string; value: unknown }) { return <div><span>{label}</span><b>{String(value)}</b></div>; }
function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function values(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }

function ExecutionDetails({ result }: { result: RunResult }) {
  const report = result.execution_report || {};
  const route = record(report.event_route); const pulse = record(report.world_pulse); const expansion = record(report.event_expansion); const check = record(report.prewrite_check); const writeback = result.state_writeback || {};
  return <section className="execution-details"><header><ListChecks size={16} /><h2>本次事件展开</h2></header><div className="execution-grid"><DetailPanel icon={Route} title="动态路由" count={values(route.expansion_routes).length}><DataRow label="展开维度" value={route.expansion_routes} /><DataRow label="故事线" value={route.active_line_ids} /><DataRow label="实体议程" value={route.entity_agenda_ids} /><DataRow label="资产" value={route.asset_ids} /></DetailPanel><DetailPanel icon={RadioTower} title="世界脉冲" count={values(pulse.entity_actions).length}><DataRow label="故事时间窗" value={pulse.story_time_window} /><DataRow label="实体行动" value={pulse.entity_actions} /><DataRow label="场外行动" value={pulse.offscreen_actions} /></DetailPanel><DetailPanel icon={Activity} title="多轮展开" count={values(expansion.expansion_passes).length}><DataRow label="戏剧核心" value={expansion.dramatic_core} /><DataRow label="明暗线交互" value={expansion.line_interactions} /><DataRow label="大场面材料" value={expansion.set_piece_material} /></DetailPanel><DetailPanel icon={ShieldCheck} title="写前检查" count={values(check.issues).length}><DataRow label="结果" value={check.passed === false ? '需重组' : '通过'} /><DataRow label="检查项" value={check.checks} /><DataRow label="修订指令" value={check.repair_instructions} /></DetailPanel></div><div className="execution-grid lower"><DetailPanel icon={Database} title="按需读取" count={result.context_summary?.cards?.length || 0}><DataRow label="焦点" value={result.context_summary?.focus} /><DataRow label="状态卡" value={result.context_summary?.cards?.map((item) => item.card_name || item.card_id)} /></DetailPanel><DetailPanel icon={BookMarked} title="自然切章" count={result.chapters_generated || 0}>{(result.chapters || []).map((chapter, index) => <DataRow key={index} label={`第 ${index + 1} 章`} value={chapter.title || chapter.chapter_intent || chapter.chapter_id} />)}</DetailPanel><DetailPanel icon={Database} title="状态回写" count={(writeback.changed_items?.length || 0) + (writeback.timeline_updates?.length || 0)}><DataRow label="摘要" value={writeback.summary} /><DataRow label="故事线" value={writeback.narrative_line_updates} /><DataRow label="实体议程" value={writeback.entity_agenda_updates} /><DataRow label="资产周期" value={writeback.asset_lifecycle_updates} /></DetailPanel></div></section>;
}

function DetailPanel({ icon: Icon, title, count, children }: { icon: typeof Route; title: string; count: number; children: React.ReactNode }) { return <section className="execution-panel"><header><Icon size={15} /><h3>{title}</h3><span>{count}</span></header><div>{children}</div></section>; }
function DataRow({ label, value }: { label: string; value: unknown }) { if (value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)) return null; return <div className="pipeline-data-row"><span>{label}</span><pre>{formatValue(value)}</pre></div>; }
