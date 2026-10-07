import {
  AlertTriangle, CheckCircle2, FileJson2, GitPullRequest, Layers3, LockKeyhole,
  RefreshCw, RotateCcw, Save, Search,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, displayError } from '../api';
import { useDraft } from '../useDraft';
import DraftStatus from './DraftStatus';
import type { AssetCatalog, AssetDetail, AssetSummary, WorkflowReview } from '../types';

interface LayeredAssetsWorkspaceProps {
  projectId: string;
  disabled: boolean;
  pendingReviews: WorkflowReview[];
  onStaged: (review: WorkflowReview) => void | Promise<void>;
  onOpenReviews: () => void;
}

const scopeLabels: Record<AssetSummary['scope'], string> = {
  foundation: '基座',
  master: '全书',
  volume: '卷级',
  event: '事件',
  runtime: '运行投影',
};

function serialize(content: unknown, kind: AssetDetail['editor_kind']): string {
  if (kind === 'text') return String(content ?? '');
  return JSON.stringify(content ?? (kind === 'collection' ? [] : {}), null, 2);
}

export default function LayeredAssetsWorkspace({
  projectId,
  disabled,
  pendingReviews,
  onStaged,
  onOpenReviews,
}: LayeredAssetsWorkspaceProps) {
  const [catalog, setCatalog] = useState<AssetCatalog | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const originalText = detail ? serialize(detail.content, detail.editor_kind) : '';
  const localDraft = useDraft(detail?.editable ? `${projectId}:asset:${detail.asset_id}` : '', originalText);
  const editorText = localDraft.text;
  const setEditorText = localDraft.change;
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const catalogRequest = useRef(0);

  const loadCatalog = useCallback(async () => {
    const request = ++catalogRequest.current;
    if (!projectId) {
      setCatalog(null);
      setSelectedId('');
      return;
    }
    setLoading(true);
    try {
      const next = await api<AssetCatalog>(`/projects/${encodeURIComponent(projectId)}/pipeline/assets`);
      if (request !== catalogRequest.current) return;
      setCatalog(next);
      setSelectedId((current) => {
        if (current && next.assets.some((asset) => asset.asset_id === current)) return current;
        return next.assets.find((asset) => asset.exists)?.asset_id || next.assets[0]?.asset_id || '';
      });
      setError('');
    } catch (nextError) {
      if (request !== catalogRequest.current) return;
      setError(displayError(nextError));
    } finally {
      if (request === catalogRequest.current) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setCatalog(null);
    setDetail(null);
    setNotice('');
    void loadCatalog();
    return () => { catalogRequest.current += 1; };
  }, [loadCatalog]);

  useEffect(() => {
    if (!projectId || !selectedId) {
      setDetail(null);
      return;
    }
    let active = true;
    setDetail(null);
    setLoading(true);
    api<AssetDetail>(`/projects/${encodeURIComponent(projectId)}/pipeline/assets/${encodeURIComponent(selectedId)}`)
      .then((next) => {
        if (!active) return;
        setDetail(next);
        setError('');
        setNotice('');
      })
      .catch((nextError) => active && setError(displayError(nextError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [projectId, selectedId]);

  const assetById = useMemo(
    () => new Map((catalog?.assets || []).map((asset) => [asset.asset_id, asset])),
    [catalog],
  );
  const term = search.trim().toLocaleLowerCase('zh-CN');
  const matches = (asset: AssetSummary) => !term || [
    asset.label, asset.asset_id, asset.description, asset.artifact_key || '', asset.json_path,
  ].some((value) => value.toLocaleLowerCase('zh-CN').includes(term));
  const pendingForAsset = pendingReviews.find(
    (review) => review.review_kind === 'asset_edit' && String(review.editable.asset_id || '') === selectedId,
  );
  const dirty = Boolean(detail && editorText !== originalText);

  const stageReview = async () => {
    if (!detail || !detail.editable || pendingForAsset) return;
    setSaving(true);
    setError('');
    try {
      const content = detail.editor_kind === 'text' ? editorText : JSON.parse(editorText);
      const review = await api<WorkflowReview>(
        `/projects/${encodeURIComponent(projectId)}/pipeline/assets/${encodeURIComponent(detail.asset_id)}/review`,
        { method: 'POST', body: JSON.stringify({ content }) },
      );
      setNotice(`已创建审核稿 ${review.staging_id}；当前权威版本尚未改变。`);
      await onStaged(review);
      await loadCatalog();
    } catch (nextError) {
      setError(displayError(nextError));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="workspace-view layered-assets-workspace">
      <header className="workspace-heading">
        <div><span className="eyebrow">Layer Registry</span><h1>分层资产工作台</h1></div>
        <label className="search-field"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索逻辑文件、ID 或路径" /></label>
      </header>

      <div className="asset-workbench-grid">
        <aside className="asset-tree" aria-label="分层资产目录">
          <header>
            <div><Layers3 size={15} /><b>逻辑文件目录</b></div>
            <button className="icon-button" onClick={() => void loadCatalog()} disabled={loading} title="刷新目录"><RefreshCw size={14} /></button>
          </header>
          <div className="asset-tree-scroll">
            {catalog?.groups.map((group) => {
              const assets = group.asset_ids.map((id) => assetById.get(id)).filter((asset): asset is AssetSummary => Boolean(asset)).filter(matches);
              if (!assets.length) return null;
              return <section key={group.group_id} className="asset-group">
                <h2><span>{group.label}</span><em>{assets.length}</em></h2>
                {assets.map((asset) => <button
                  key={asset.asset_id}
                  className={`${selectedId === asset.asset_id ? 'active' : ''} ${!asset.exists ? 'unavailable' : ''}`}
                  onClick={() => setSelectedId(asset.asset_id)}
                  title={asset.asset_id}
                >
                  {asset.derived ? <LockKeyhole size={13} /> : <FileJson2 size={13} />}
                  <span><b>{asset.label}</b><small>{scopeLabels[asset.scope]} · {asset.json_path}</small></span>
                  <em>{asset.exists ? `v${asset.version}` : '未生成'}</em>
                </button>)}
              </section>;
            })}
            {!loading && catalog && !catalog.assets.some(matches) && <div className="asset-tree-empty">没有匹配的逻辑文件</div>}
          </div>
        </aside>

        <main className="asset-editor-panel">
          {!projectId && <div className="empty-state"><Layers3 size={28} /><b>先选择一个项目</b><span>目录会根据该项目已经生成的权威层和运行投影自动建立。</span></div>}
          {projectId && !detail && <div className="empty-state"><FileJson2 size={28} /><b>{loading ? '正在读取资产' : '选择一个逻辑文件'}</b><span>{error || '每个条目都是可独立查看和审核的逻辑页面。'}</span></div>}
          {detail && <>
            <header className="asset-editor-heading">
              <div>
                <div className="asset-badges"><span>{scopeLabels[detail.scope]}</span><span>{detail.editor_kind}</span>{detail.derived && <span className="readonly">派生只读</span>}</div>
                <h2>{detail.label}</h2>
                <p>{detail.description}</p>
              </div>
              <div className="asset-version"><span>权威版本</span><b>v{detail.version}</b></div>
            </header>

            <DraftStatus before={originalText} after={editorText} savedAt={localDraft.savedAt} warning={localDraft.warning} conflict={localDraft.conflict} />
            <div className="asset-meta-strip">
              <span><b>所属文件</b>{detail.artifact_key || '运行时投影'}</span>
              <span><b>JSON 路径</b>{detail.json_path}</span>
              <span><b>负责阶段</b>{detail.owner_stage || '—'}</span>
              <span><b>条目数</b>{detail.item_count}</span>
            </div>

            {detail.derived && <div className="asset-callout readonly"><LockKeyhole size={15} /><span>这是确定性派生结果。请修改来源资产{detail.source_asset_id ? `「${detail.source_asset_id}」` : ''}，再让系统重建投影。</span></div>}
            {!detail.exists && <div className="asset-callout warning"><AlertTriangle size={15} /><span>所属阶段还未生成，因此当前页面不能提交修改。</span></div>}
            {pendingForAsset && <div className="asset-callout pending"><GitPullRequest size={15} /><span>该文件已有待审核版本：{pendingForAsset.title}</span><button onClick={onOpenReviews}>去审核中心</button></div>}
            {notice && <div className="asset-callout success"><CheckCircle2 size={15} /><span>{notice}</span><button onClick={onOpenReviews}>去审核中心</button></div>}
            {error && <div className="editor-error asset-editor-error">{error}</div>}

            <textarea
              className="asset-json-editor"
              value={editorText}
              onChange={(event) => setEditorText(event.target.value)}
              readOnly={!detail.editable || Boolean(pendingForAsset)}
              spellCheck={false}
              aria-label={`${detail.label} JSON 编辑器`}
            />

            <footer className="asset-editor-footer">
              <div className="asset-lineage">
                <span><b>依赖</b>{detail.dependencies.length ? detail.dependencies.join(' · ') : '无'}</span>
                <span><b>影响下游</b>{detail.downstream.length ? detail.downstream.join(' · ') : '无'}</span>
              </div>
              <div className="asset-editor-actions">
                <button className="secondary-button" disabled={!dirty || saving} onClick={() => setEditorText(originalText)}><RotateCcw size={14} />撤销本页修改</button>
                <button className="primary-button" disabled={disabled || saving || !dirty || !detail.editable || Boolean(pendingForAsset)} onClick={() => void stageReview()}><Save size={14} />{saving ? '正在暂存' : '提交审核稿'}</button>
              </div>
            </footer>
          </>}
        </main>
      </div>
    </section>
  );
}
