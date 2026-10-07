import { BookOpen, CircleHelp, Cloud, RefreshCw, ServerCog } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, displayError } from './api';
import { attachRunEvents, isTerminalEvent } from './runStream';
import ChapterWorkspace from './components/ChapterWorkspace';
import ContextWorkspace from './components/ContextWorkspace';
import EntityLibrary from './components/EntityLibrary';
import Inspector from './components/Inspector';
import LayeredAssetsWorkspace from './components/LayeredAssetsWorkspace';
import PipelineWorkspace from './components/PipelineWorkspace';
import Sidebar from './components/Sidebar';
import StoryEcosystem from './components/StoryEcosystem';
import type {
  ActivityEntry,
  CardType,
  ChapterSummary,
  ProjectMeta,
  ProjectSummary,
  RunResult,
  StateData,
  WorkspaceView,
  WorkflowData,
  WorkflowReview,
} from './types';

const streamEvents = [
  'init_start', 'init_done', 'init_failed', 'volume_plan_start', 'volume_plan_done', 'volume_plan_failed',
  'volume_start', 'volume_done', 'sprout_start', 'sprout_done', 'chapter_start', 'chapter_done', 'chapter_failed',
  'sprout_event_start', 'sprout_event_done', 'sprout_event_failed',
  'graph_start', 'graph_done', 'step', 'heartbeat', 'result', 'error',
  'cancelled',
];

function eventLabel(name: string, data: Record<string, unknown>): string {
  if (typeof data.title === 'string') return data.title;
  if (typeof data.message === 'string') return data.message;
  if (typeof data.step_key === 'string') {
    const key = data.step_key;
    const stepLabels: Array<[string, string]> = [
      ['graph1.', '作品基座'], ['graph2.longline', '全书总纲'], ['graph2.story', '全书伏笔、成长与关系'],
      ['graph2.map', '主要地图'], ['graph3.volume.story', '卷故事引擎'], ['graph3.volume.map', '卷地图'],
      ['graph3.volume.event', '卷事件设计'], ['graph4.event.budget', '事件体量'], ['graph4.event.route', '动态路由'],
      ['graph4.event.world_pulse', '世界脉冲'], ['graph4.event.expand', '多轮展开'], ['graph4.event.plan', '场景编织'],
      ['graph4.event.prewrite_check', '写前一致性检查'], ['graph4.event.namecheck', '命名检查'],
      ['graph4.event.jit_cards', '即时材料卡'], ['graph4.event.blocks.write', '正文生成'],
      ['graphE.', '事实提取与状态提交'], ['graph5.', '自然切章'],
    ];
    return stepLabels.find(([prefix]) => key.startsWith(prefix))?.[1] || key;
  }
  const labels: Record<string, string> = {
    init_start: '初始化开始', init_done: '初始化完成', init_failed: '初始化失败',
    volume_plan_start: '卷规划开始', volume_plan_done: '卷规划完成', volume_plan_failed: '卷规划失败',
    volume_start: '批量连载开始', volume_done: '批量连载完成', sprout_start: '根事件干预开始', sprout_done: '根事件干预完成',
    sprout_event_start: '干预事件开始', sprout_event_done: '干预事件完成', sprout_event_failed: '干预事件失败',
    chapter_start: '章节开始', chapter_done: '章节完成', chapter_failed: '章节失败',
    graph_start: '流程图开始', graph_done: '流程图完成', step: '步骤更新', heartbeat: '等待模型返回', result: '任务结束', error: '运行错误',
  };
  return labels[name] || name;
}

function eventLevel(name: string): ActivityEntry['level'] {
  if (name === 'error' || name.endsWith('_failed')) return 'error';
  if (name.endsWith('_done') || name === 'result') return 'success';
  if (name === 'heartbeat') return 'warning';
  return 'info';
}

export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState(() => localStorage.getItem('novelwb.project') || '');
  const [meta, setMeta] = useState<ProjectMeta | null>(null);
  const [state, setState] = useState<StateData | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [chapterText, setChapterText] = useState('');
  const [selectedChapterId, setSelectedChapterId] = useState('');
  const [view, setView] = useState<WorkspaceView>('pipeline');
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [lastResult, setLastResult] = useState<RunResult | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowData | null>(null);
  const [running, setRunning] = useState(false);
  const [runMessage, setRunMessage] = useState('');
  const [progress, setProgress] = useState(0);
  const [notice, setNotice] = useState('');
  const [healthy, setHealthy] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState('');
  const streamRef = useRef<EventSource | null>(null);
  const activeRunRef = useRef<string>('');

  const addActivity = useCallback((event: string, message: string, data?: Record<string, unknown>) => {
    setActivity((current) => [{
      id: `${Date.now()}-${Math.random()}`,
      at: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      event,
      message,
      data,
      level: eventLevel(event),
    }, ...current].slice(0, 160));
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const rows = await api<ProjectSummary[]>('/projects');
      setProjects(rows);
      setProjectId((current) => {
        if (current && rows.some((row) => row.project_id === current)) return current;
        return rows[0]?.project_id || '';
      });
    } catch (error) {
      setNotice(displayError(error));
    }
  }, []);

  const refreshProject = useCallback(async (id = projectId) => {
    if (!id) {
      setMeta(null); setState(null); setChapters([]); setWorkflow(null); return;
    }
    try {
      const [nextMeta, nextState, nextChapters, nextWorkflow] = await Promise.all([
        api<ProjectMeta>(`/projects/${encodeURIComponent(id)}`),
        api<StateData>(`/projects/${encodeURIComponent(id)}/pipeline/state`),
        api<ChapterSummary[]>(`/projects/${encodeURIComponent(id)}/chapters`),
        api<WorkflowData>(`/projects/${encodeURIComponent(id)}/pipeline/workflow`),
      ]);
      setMeta(nextMeta);
      setState(nextState);
      setChapters(nextChapters);
      setWorkflow(nextWorkflow);
      setLastSyncedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
      setNotice('');
    } catch (error) {
      setNotice(displayError(error));
    }
  }, [projectId]);

  useEffect(() => {
    void loadProjects();
    fetch('/health').then((response) => setHealthy(response.ok)).catch(() => setHealthy(false));
    return () => streamRef.current?.close();
  }, [loadProjects]);

  useEffect(() => {
    if (!projectId) return;
    localStorage.setItem('novelwb.project', projectId);
    setSelectedChapterId('');
    setChapterText('');
    void refreshProject(projectId);
  }, [projectId, refreshProject]);

  const createProject = async () => {
    const id = window.prompt('项目名')?.trim();
    if (!id) return;
    try {
      await api('/projects', { method: 'POST', body: JSON.stringify({ project_id: id }) });
      await loadProjects();
      setProjectId(id);
      addActivity('project_created', `已创建项目 ${id}`);
    } catch (error) {
      setNotice(displayError(error));
    }
  };

  const selectChapter = async (chapterId: string) => {
    if (!projectId) return;
    setSelectedChapterId(chapterId);
    setChapterText('');
    try {
      const data = await api<{ chapter_id: string; text: string }>(`/projects/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(chapterId)}`);
      setChapterText(data.text);
    } catch (error) {
      setChapterText(displayError(error));
    }
  };

  const stopRun = useCallback(() => {
    const runId = activeRunRef.current;
    if (!projectId || !runId) {
      streamRef.current?.close();
      streamRef.current = null;
      setRunning(false);
      setRunMessage('当前任务无法继续取消');
      return;
    }
    setRunMessage('已请求取消，等待当前模型调用返回');
    addActivity('cancel_requested', '已向后端请求取消运行', { run_id: runId });
    void api(`/projects/${encodeURIComponent(projectId)}/pipeline/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
    }).catch((error) => {
      setRunMessage(displayError(error));
      addActivity('error', displayError(error));
    });
  }, [addActivity, projectId]);

  const connectRun = useCallback((
    runId: string,
    options: { workflowReview?: boolean } = {},
  ) => {
    if (!projectId) return;
    streamRef.current?.close();
    setRunning(true);
    setProgress(2);
    setRunMessage('正在建立运行连接');
    setLastResult(null);
    activeRunRef.current = runId;
    localStorage.setItem(`novelwb.run.${projectId}`, JSON.stringify({ runId, ...options }));
    const stream = new EventSource(`/projects/${encodeURIComponent(projectId)}/pipeline/runs/${encodeURIComponent(runId)}/events`);
    streamRef.current = stream;

    attachRunEvents(stream, streamEvents, (eventName, data) => {
      const label = eventLabel(eventName, data);
      setRunMessage(label);
      if (eventName !== 'heartbeat') addActivity(eventName, label, data);

      const done = Number(data.completed_events ?? data.completed_slots ?? data.completed ?? 0);
      const total = Number(data.event_count ?? data.chapter_count ?? data.total_slots ?? 0);
      if (total > 0) setProgress(Math.min(98, (done / total) * 100));
      else if (eventName === 'graph_done') setProgress((current) => Math.min(90, current + 22));
      else if (eventName === 'step') setProgress((current) => Math.min(92, current + 3));

      if (eventName === 'result') {
        if (options.workflowReview) {
          const review = data.review && typeof data.review === 'object'
            ? data.review as Record<string, unknown>
            : data;
          addActivity('review_ready', label, review);
        } else {
          const result = (data.result && typeof data.result === 'object' ? data.result : data) as RunResult;
          setLastResult(result);
        }
        setProgress(100);
        void refreshProject(projectId);
      }
      if (eventName === 'cancelled') {
        setProgress(0);
        setRunMessage('运行已取消，已保存的断点保留');
      }
      if (isTerminalEvent(eventName)) {
        setRunning(false);
        stream.close(); streamRef.current = null; activeRunRef.current = '';
        localStorage.removeItem(`novelwb.run.${projectId}`);
      }
    }, () => {
      if (streamRef.current !== stream) return;
      // EventSource reconnects to the subscription endpoint with Last-Event-ID.
      setRunMessage('连接中断，正在重新连接当前运行');
    });
  }, [addActivity, projectId, refreshProject]);

  const startStream = useCallback(async (
    path: string, params: Record<string, string | number | boolean>,
    options: { workflowReview?: boolean } = {},
  ) => {
    if (!projectId) return;
    const runId = `run_ui_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`;
    const kind = path === 'workflow/generate/stream' ? 'workflow' : path.replace('/stream', '');
    setRunning(true); setRunMessage('正在创建运行任务');
    try {
      await api(`/projects/${encodeURIComponent(projectId)}/pipeline/runs`, {
        method: 'POST', body: JSON.stringify({ run_id: runId, kind, params }),
      });
      connectRun(runId, options);
    } catch (error) {
      setRunning(false); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    }
  }, [projectId, connectRun, addActivity]);

  useEffect(() => {
    streamRef.current?.close(); streamRef.current = null; activeRunRef.current = '';
    setRunning(false);
    if (!projectId) return;
    let active = true;
    try {
      const saved = localStorage.getItem(`novelwb.run.${projectId}`);
      if (saved) {
        const state = JSON.parse(saved) as { runId: string; workflowReview?: boolean };
        api(`/projects/${encodeURIComponent(projectId)}/pipeline/runs/${encodeURIComponent(state.runId)}`)
          .then(() => active && connectRun(state.runId, state))
          .catch((error) => { if (active) { setNotice(displayError(error)); localStorage.removeItem(`novelwb.run.${projectId}`); } });
      } else {
        api<Array<{ run_id: string; status: string; kind: string }>>(`/projects/${encodeURIComponent(projectId)}/pipeline/runs`)
          .then((runs) => {
            if (!active) return;
            const current = runs.find((run) => ['queued', 'running'].includes(run.status));
            if (current) connectRun(current.run_id, { workflowReview: current.kind === 'workflow' });
          }).catch((error) => active && setNotice(displayError(error)));
      }
    } catch (error) { setNotice(displayError(error)); }
    return () => { active = false; streamRef.current?.close(); };
  }, [projectId, connectRun]);

  const runWrite = async (goal: string, resultTarget: string, isKey: boolean) => {
    if (!projectId) return;
    setRunning(true); setProgress(8); setRunMessage('正在生成事件'); setLastResult(null);
    addActivity('write_start', '人工补写生成开始');
    try {
      const result = await api<RunResult>(`/projects/${encodeURIComponent(projectId)}/pipeline/write-event/preview`, {
        method: 'POST', body: JSON.stringify({ event_goal: goal, result_target: resultTarget, is_key_event: isKey }),
      });
      setLastResult(result); setProgress(100); setRunMessage('草稿已生成，等待审核');
      addActivity('review', '事件草稿等待审核', result);
    } catch (error) {
      setProgress(0); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const approveWrite = async (stagingId: string, draftText: string) => {
    if (!projectId || !stagingId) return;
    setRunning(true); setProgress(20); setRunMessage('正在校验并提交事件');
    try {
      const result = await api<RunResult>(`/projects/${encodeURIComponent(projectId)}/pipeline/write-event/approve`, {
        method: 'POST', body: JSON.stringify({ staging_id: stagingId, draft_text: draftText }),
      });
      setLastResult(result); setProgress(100); setRunMessage('事件已批准并提交');
      addActivity('result', '事件已批准并提交', result);
      await refreshProject(projectId);
    } catch (error) {
      setProgress(0); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const rejectWrite = async (stagingId: string) => {
    if (!projectId || !stagingId) return;
    setRunning(true); setRunMessage('正在丢弃待审草稿');
    try {
      await api(`/projects/${encodeURIComponent(projectId)}/pipeline/write-event/reject`, {
        method: 'POST', body: JSON.stringify({ staging_id: stagingId }),
      });
      setLastResult(null); setProgress(0); setRunMessage('待审草稿已拒绝');
      addActivity('review_rejected', '待审草稿已拒绝');
    } catch (error) {
      setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const generateWorkflowReview = (stage: string, payload: Record<string, unknown>) => {
    if (!projectId) return;
    const params: Record<string, string | number | boolean> = { stage };
    for (const [key, value] of Object.entries(payload)) {
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        params[key] = value;
      }
    }
    setLastResult(null);
    startStream('workflow/generate/stream', params, { workflowReview: true });
  };

  const approveWorkflowReview = async (stagingId: string, editable: Record<string, unknown>) => {
    if (!projectId) return;
    const review = workflow?.reviews.find((item) => item.staging_id === stagingId);
    const isFoundationFile = review?.review_kind === 'foundation' && Boolean(review.foundation_step);
    const isMasterFile = review?.review_kind === 'master_plan' && Boolean(review.master_step);
    const isVolumeFile = review?.review_kind === 'volume_plan' && Boolean(review.volume_step);
    const isEventPlanFile = review?.review_kind === 'event_plan' && Boolean(review.event_plan_step);
    const isSequentialFile = isFoundationFile || isMasterFile || isVolumeFile || isEventPlanFile;
    setRunning(true); setProgress(20); setRunMessage(isSequentialFile ? '正在批准当前文件' : '正在批准审核稿');
    try {
      const result = await api<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/pipeline/workflow/reviews/${encodeURIComponent(stagingId)}/approve`, {
        method: 'POST', body: JSON.stringify({ editable }),
      });
      const message = isSequentialFile ? '当前文件已批准，下一文件已解锁' : '审核已批准';
      setProgress(100); setRunMessage(message); addActivity('review_approved', message, result);
      await refreshProject(projectId);
    } catch (error) {
      setProgress(0); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const reviseWorkflowReview = async (
    stagingId: string,
    editable: Record<string, unknown>,
    feedback: string,
  ) => {
    if (!projectId) return;
    setRunning(true); setProgress(20); setRunMessage('正在根据审核意见修改当前稿');
    try {
      const review = await api<WorkflowReview>(
        `/projects/${encodeURIComponent(projectId)}/pipeline/workflow/reviews/${encodeURIComponent(stagingId)}/revise`,
        { method: 'POST', body: JSON.stringify({ editable, feedback }) },
      );
      const message = `已完成第 ${review.revision_count || 1} 次定向修订，仍需审核批准`;
      setProgress(100); setRunMessage(message);
      addActivity('review_revised', message, {
        staging_id: stagingId,
        revision_count: review.revision_count,
      });
      await refreshProject(projectId);
    } catch (error) {
      setProgress(0); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const auditWorkflowReview = async (stagingId: string, editable: Record<string, unknown>) => {
    if (!projectId) return;
    setRunning(true); setProgress(20); setRunMessage('正在独立审核当前完整稿');
    try {
      const review = await api<WorkflowReview>(
        `/projects/${encodeURIComponent(projectId)}/pipeline/workflow/reviews/${encodeURIComponent(stagingId)}/audit`,
        { method: 'POST', body: JSON.stringify({ editable }) },
      );
      const issueCount = review.current_audit?.issues.length || 0;
      const message = review.current_audit?.verdict === 'pass'
        ? 'AI 审核通过，未发现必须修改的问题'
        : `AI 审核完成，生成了 ${issueCount} 条具体修改意见`;
      setProgress(100); setRunMessage(message);
      addActivity('review_audited', message, {
        staging_id: stagingId,
        audit_count: review.audit_count,
        verdict: review.current_audit?.verdict,
      });
      await refreshProject(projectId);
    } catch (error) {
      setProgress(0); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const rewindFoundation = async (stepKey: string) => {
    if (!projectId || !stepKey) return;
    const confirmed = window.confirm(
      `确定从 ${stepKey} 退回重新生成吗？受它影响的后续基座文件会暂时失效，但历史版本会保留在快照中。`,
    );
    if (!confirmed) return;
    setRunning(true); setProgress(20); setRunMessage('正在创建快照并退回基座文件');
    try {
      const result = await api<Record<string, unknown>>(
        `/projects/${encodeURIComponent(projectId)}/pipeline/workflow/foundation/rewind`,
        { method: 'POST', body: JSON.stringify({ step_key: stepKey }) },
      );
      setProgress(100); setRunMessage('已安全退回，可以重新生成当前文件');
      addActivity('foundation_rewind', '已安全退回作品基座', result);
      await refreshProject(projectId);
    } catch (error) {
      setProgress(0); setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const rejectWorkflowReview = async (stagingId: string) => {
    if (!projectId) return;
    setRunning(true); setRunMessage('正在驳回候选');
    try {
      const result = await api<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/pipeline/workflow/reviews/${encodeURIComponent(stagingId)}/reject`, { method: 'POST' });
      const message = result.reopened_step === 'scene_plan'
        ? '检查意见已保存，连续场景方案已重新解锁'
        : '候选已驳回';
      setProgress(0); setRunMessage(message); addActivity('review_rejected', message, result);
      await refreshProject(projectId);
    } catch (error) {
      setRunMessage(displayError(error)); addActivity('error', displayError(error));
    } finally { setRunning(false); }
  };

  const assetReviewStaged = async (review: WorkflowReview) => {
    addActivity('review_ready', `分层资产审核稿已创建：${review.title}`, { staging_id: review.staging_id });
    await refreshProject(projectId);
  };

  const cardsFor = (type: CardType) => state?.status_cards[`${type}_cards`] || [];
  let content: React.ReactNode;
  if (view === 'pipeline') {
    content = <PipelineWorkspace
      projectId={projectId}
      disabled={!projectId}
      running={running}
      runMessage={runMessage}
      progress={progress}
      lastResult={lastResult}
      activity={activity}
      state={state}
      workflow={workflow}
      onGenerateWorkflow={generateWorkflowReview}
      onApproveWorkflow={approveWorkflowReview}
      onAuditWorkflow={auditWorkflowReview}
      onReviseWorkflow={reviseWorkflowReview}
      onRejectWorkflow={rejectWorkflowReview}
      onRewindFoundation={rewindFoundation}
      onAuto={(startIndex, maxEvents, onlyKey) => startStream('auto-volume/stream', { start_index: startIndex, max_events: maxEvents, only_key: onlyKey })}
      onWrite={runWrite}
      onApprove={approveWrite}
      onReject={rejectWrite}
      onSprout={(goal, count, startIndex, resultTarget, isKey) => startStream('sprout/stream', { root_event_goal: goal, event_count: count, start_index: startIndex, result_target: resultTarget, is_key_event: isKey })}
      onStop={stopRun}
    />;
  } else if (view === 'assets') {
    content = <LayeredAssetsWorkspace
      projectId={projectId}
      disabled={!projectId || running}
      pendingReviews={workflow?.pending_reviews || []}
      onStaged={assetReviewStaged}
      onOpenReviews={() => setView('pipeline')}
    />;
  } else if (view === 'chapters') {
    content = <ChapterWorkspace chapters={chapters} chapterText={chapterText} selectedChapterId={selectedChapterId} onSelect={selectChapter} />;
  } else if (view === 'context') {
    content = <ContextWorkspace context={state?.latest_context || null} lastResult={lastResult} />;
  } else if (view === 'ecosystem') {
    content = <StoryEcosystem state={state} />;
  } else {
    content = <EntityLibrary type={view} cards={cardsFor(view)} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark"><BookOpen size={20} /><span><b>小说工作台</b><small>Novel Workbench</small></span></div>
        <div className="topbar-project"><span>{projectId || '未选择项目'}</span>{running && <i>运行中</i>}</div>
        <div className="topbar-actions">
          {lastSyncedAt && !running && <span className="sync-status">已同步 {lastSyncedAt}</span>}
          <span className={healthy ? 'health online' : 'health'}><Cloud size={15} />{healthy ? '服务在线' : '服务离线'}</span>
          <button className="icon-button" onClick={() => void refreshProject()} title="同步工作台"><RefreshCw size={16} /></button>
          <a className="icon-button" href="/docs" target="_blank" rel="noreferrer" title="接口文档"><ServerCog size={16} /></a>
          <a className="icon-button" href="/health" target="_blank" rel="noreferrer" title="健康检查"><CircleHelp size={16} /></a>
        </div>
      </header>
      {notice && <div className="global-notice">{notice}<button onClick={() => setNotice('')}>关闭</button></div>}
      <main className="workbench-grid">
        <Sidebar projects={projects} projectId={projectId} meta={meta} state={state} view={view} onProjectChange={setProjectId} onViewChange={setView} onRefresh={loadProjects} onCreate={createProject} />
        <div className="workspace-canvas">{content}</div>
        <Inspector state={state} activity={activity} lastResult={lastResult} />
      </main>
    </div>
  );
}
