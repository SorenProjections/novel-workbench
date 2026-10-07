import { Check, KeyRound, Plus, RefreshCw, Save, Trash2, Unplug, Zap } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, displayError } from '../api';
import { newDraft, presets, profileBody, profileDraft, protocols } from '../modelProfiles';
import type { ModelDraft, ModelProtocol, ModelSettings } from '../modelProfiles';

const endpoint = '/settings/models';
const settingsApi = <T,>(path = '', options: RequestInit = {}) => api<T>(endpoint + path, {
  ...options, headers: { 'X-Model-Settings': '1' },
});

export default function ModelSettingsWorkspace() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ModelDraft>(() => newDraft());
  const [original, setOriginal] = useState(() => JSON.stringify(newDraft()));
  const [busy, setBusy] = useState('加载配置');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [testResult, setTestResult] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const feedback = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  const dirty = JSON.stringify(draft) !== original;
  const selected = settings?.profiles.find(item => item.id === selectedId);
  const active = settings?.profiles.find(item => item.id === settings.active_profile_id);
  const locked = !!busy || !!settings?.disabled;

  function select(data: ModelSettings, id: string | null) {
    const profile = data.profiles.find(item => item.id === id);
    const value = profile ? profileDraft(profile) : newDraft();
    setSelectedId(profile?.id || null); setDraft(value); setOriginal(JSON.stringify(value));
    setConfirmDelete(false); setTestResult('');
  }

  async function load() {
    setBusy('加载配置'); setError('');
    try {
      const data = await settingsApi<ModelSettings>();
      if (!mounted.current) return;
      setSettings(data); select(data, data.active_profile_id || data.profiles[0]?.id || null);
    } catch (reason) { if (mounted.current) setError(displayError(reason)); }
    finally { if (mounted.current) setBusy(''); }
  }

  useEffect(() => { mounted.current = true; void load(); return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (error) feedback.current?.scrollIntoView({ block: 'nearest' }); }, [error]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  function change<K extends keyof ModelDraft>(field: K, value: ModelDraft[K]) {
    setDraft(previous => ({ ...previous, [field]: value })); setTestResult(''); setMessage(''); setError('');
  }
  function canLeave() { return !dirty || window.confirm('当前配置尚未保存，确定放弃这些修改吗？'); }
  function choose(id: string | null) {
    if (settings && canLeave()) { select(settings, id); setMessage(''); setError(''); }
  }
  async function save() {
    if (!settings || !form.current?.reportValidity()) return;
    setBusy('保存配置'); setError(''); setMessage('');
    try {
      const data = await settingsApi<ModelSettings>(selectedId ? `/profiles/${selectedId}` : '/profiles', {
        method: selectedId ? 'PUT' : 'POST', body: JSON.stringify(profileBody(draft, settings.revision)),
      });
      if (!mounted.current) return;
      setSettings(data); select(data, data.saved_profile_id || null);
      setMessage(data.saved_profile_id === data.active_profile_id ? '配置已保存，新任务将使用更新后的配置。' : '配置已保存。点击“使用此配置”后，新任务才会切换。');
    } catch (reason) { if (mounted.current) setError(displayError(reason)); }
    finally { if (mounted.current) setBusy(''); }
  }
  async function activate(id: string | null) {
    if (!settings) return;
    setBusy('切换配置'); setError(''); setMessage('');
    try {
      const data = await settingsApi<ModelSettings>('/active', {
        method: 'POST', body: JSON.stringify({ profile_id: id, revision: settings.revision }),
      });
      if (!mounted.current) return;
      setSettings(data); setMessage('已切换。新任务立即生效，正在运行的任务保持原配置。');
    } catch (reason) { if (mounted.current) setError(displayError(reason)); }
    finally { if (mounted.current) setBusy(''); }
  }
  async function test() {
    if (!settings || !form.current?.reportValidity()) return;
    setBusy('测试连接'); setError(''); setTestResult(''); setMessage('');
    try {
      const result = await settingsApi<{ latency_ms: number; input_tokens: number; output_tokens: number }>('/test', {
        method: 'POST', body: JSON.stringify({ ...profileBody(draft, settings.revision), profile_id: selectedId }),
      });
      if (mounted.current) setTestResult(`连接成功 · ${result.latency_ms} ms · 输入 ${result.input_tokens} / 输出 ${result.output_tokens} tokens`);
    } catch (reason) { if (mounted.current) setError(displayError(reason)); }
    finally { if (mounted.current) setBusy(''); }
  }
  async function remove() {
    if (!settings || !selectedId) return;
    setBusy('删除配置'); setError(''); setMessage('');
    try {
      const data = await settingsApi<ModelSettings>(`/profiles/${selectedId}`, {
        method: 'DELETE', body: JSON.stringify({ revision: settings.revision }),
      });
      if (!mounted.current) return;
      setSettings(data); select(data, data.active_profile_id || data.profiles[0]?.id || null);
      setMessage('配置及其本机密钥已删除。');
    } catch (reason) { if (mounted.current) setError(displayError(reason)); }
    finally { if (mounted.current) setBusy(''); }
  }

  return <section className="model-settings" aria-labelledby="model-settings-title">
    <header className="model-settings-heading">
      <div><h1 id="model-settings-title">模型与 API</h1><p>为创作保存多套模型连接，按需切换。配置对当前工作区的所有作品生效。</p></div>
      <button className="secondary-button" disabled={!!busy} onClick={() => { if (canLeave()) void load(); }}><RefreshCw size={15} />刷新配置</button>
    </header>
    {error && <div ref={feedback} className="model-feedback error" role="alert">{error}</div>}
    {message && <div className="model-feedback success" role="status">{message}</div>}
    {!settings ? <p className="model-loading" role="status">{busy || '无法读取配置。请检查服务并刷新。'}</p> : <>
      <div className="model-current">
        <Check size={19} /><div><small>当前使用</small><strong>{settings.disabled ? 'Mock（离线演示锁定）' : active ? `${active.name} / ${active.model}` : settings.environment_label}</strong></div>
        {active && !settings.disabled && <button className="secondary-button" disabled={locked || dirty} onClick={() => void activate(null)}><Unplug size={15} />恢复环境配置</button>}
      </div>
      {settings.disabled && <p className="model-feedback">离线演示不调用真实模型。请启动普通工作台后在此配置。</p>}
      <div className="model-settings-layout">
        <aside className="model-profile-list" aria-label="已保存的模型配置">
          <div className="model-list-heading"><h2>已保存配置 <small>{settings.profiles.length}</small></h2><button className="icon-button" title="新增配置" disabled={locked} onClick={() => choose(null)}><Plus size={17} /></button></div>
          {settings.profiles.length === 0 && <p className="model-list-empty">保存第一套配置，即可随时切换模型。</p>}
          {settings.profiles.map(profile => <button key={profile.id} className={`model-profile ${selectedId === profile.id ? 'selected' : ''}`} disabled={!!busy} onClick={() => choose(profile.id)}>
            <span><b>{profile.name}</b>{profile.id === settings.active_profile_id && <em>使用中</em>}</span>
            <small>{profile.model}</small><small>{protocols[profile.protocol]} · {profile.has_api_key ? '密钥已保存' : '未保存密钥'}</small>
          </button>)}
        </aside>
        <form ref={form} className="model-profile-form" autoComplete="off" onSubmit={event => { event.preventDefault(); void save(); }}>
          <div className="model-form-heading"><h2>{selectedId ? '编辑配置' : '新增配置'}</h2>{dirty && <span>有未保存的修改</span>}</div>
          <fieldset disabled={locked}>
            <label className="model-field">快速填入服务配置<select aria-label="快速填入服务配置" value="" onChange={event => { setDraft(newDraft(Number(event.target.value))); setTestResult(''); setMessage(''); }}>
              <option value="" disabled>选择服务预设（会替换当前表单）</option>{presets.map((preset, index) => <option key={preset.label} value={index}>{preset.label}</option>)}
            </select></label>
            <div className="model-field-pair">
              <label className="model-field">配置名称<input required maxLength={80} value={draft.name} onChange={event => change('name', event.target.value)} placeholder="例如：日常写作、备用模型" /></label>
              <label className="model-field">API 协议<select value={draft.protocol} onChange={event => change('protocol', event.target.value as ModelProtocol)}>{Object.entries(protocols).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            </div>
            <label className="model-field">API 基础地址<input required type="url" maxLength={500} value={draft.base_url} onChange={event => change('base_url', event.target.value)} placeholder="https://api.example.com/v1" /><small>填写服务商提供的基础地址；兼容服务通常以 /v1 结尾。本机服务支持 http。</small></label>
            <label className="model-field">模型 ID<input required maxLength={150} value={draft.model} onChange={event => change('model', event.target.value)} placeholder="填写此 API 支持的模型 ID" /><small>按服务商控制台或本机模型列表填写，不使用网页聊天产品的名称。</small></label>
            <label className="model-field">API Key<input type="password" autoComplete="new-password" spellCheck={false} maxLength={4096} value={draft.api_key} disabled={draft.clear_api_key} onChange={event => change('api_key', event.target.value)} placeholder={selected?.has_api_key ? '已保存；留空保留，输入新值替换' : '输入密钥；无密钥的本地服务可留空'} />
              <small>{selected?.has_api_key ? '已保存的密钥不会回传到浏览器。更换地址或协议时，请重新输入该服务的密钥。' : '密钥仅提交到本机后端保存，不写入浏览器存储。'}</small>
            </label>
            {selected?.has_api_key && <label className="model-check"><input type="checkbox" checked={draft.clear_api_key} onChange={event => { change('clear_api_key', event.target.checked); change('api_key', ''); }} />清除已保存的 API Key</label>}
            <details className="model-advanced"><summary>高级选项</summary>
              <div className="model-field-pair">
                <label className="model-field">最大输出 tokens<input type="number" required min={1} max={262144} value={draft.max_output_tokens} onChange={event => change('max_output_tokens', Number(event.target.value))} /></label>
                <label className="model-field">生成超时（秒）<input type="number" required min={5} max={1800} value={draft.timeout_seconds} onChange={event => change('timeout_seconds', Number(event.target.value))} /></label>
                <label className="model-field">传输重试次数<input type="number" required min={0} max={2} value={draft.max_retries} onChange={event => change('max_retries', Number(event.target.value))} /></label>
                {(draft.protocol === 'openai' || draft.protocol === 'deepseek') && <label className="model-field">输出上限参数<select value={draft.token_parameter} onChange={event => change('token_parameter', event.target.value as ModelDraft['token_parameter'])}><option value="max_tokens">max_tokens（多数兼容服务）</option><option value="max_completion_tokens">max_completion_tokens（OpenAI）</option></select></label>}
                {draft.protocol === 'deepseek' && <label className="model-field">DeepSeek 思考模式<select value={draft.thinking} onChange={event => change('thinking', event.target.value as ModelDraft['thinking'])}><option value="steps">跟随创作步骤</option><option value="disabled">关闭</option><option value="enabled">开启</option></select></label>}
                {['deepseek', 'openai', 'openai_responses'].includes(draft.protocol) && <label className="model-field">推理强度<select value={draft.reasoning_effort} onChange={event => change('reasoning_effort', event.target.value as ModelDraft['reasoning_effort'])}><option value="">服务默认 / DeepSeek 跟随步骤</option>{['low', 'medium', 'high', 'max'].map(value => <option key={value} value={value}>{value}</option>)}</select></label>}
              </div>
              {draft.protocol !== 'anthropic' && <label className="model-check"><input type="checkbox" checked={draft.json_mode} onChange={event => change('json_mode', event.target.checked)} />在结构化步骤请求 JSON 模式</label>}
              <label className="model-check"><input type="checkbox" checked={draft.send_temperature} onChange={event => change('send_temperature', event.target.checked)} />发送步骤中的 temperature 参数</label>
              <p>输出上限不能超过模型支持值；推理模型可能不支持 temperature。参数报错时可关闭相应选项。重试可能增加费用。</p>
            </details>
          </fieldset>
          <div className="model-action-row">
            <button className="secondary-button" type="button" disabled={locked} onClick={() => void test()}><Zap size={15} />{busy === '测试连接' ? '测试中…' : '测试连接'}</button>
            <button className="primary-button" type="submit" disabled={locked}><Save size={15} />{busy === '保存配置' ? '保存中…' : '保存配置'}</button>
            {selectedId && <button className="secondary-button" type="button" disabled={locked || dirty || selectedId === settings.active_profile_id} onClick={() => void activate(selectedId)}><Check size={15} />{selectedId === settings.active_profile_id ? '正在使用' : '使用此配置'}</button>}
          </div>
          <p className="model-test-hint">测试会向表单中的 API 地址发送一条短请求，可能产生少量费用；不会保存或启用配置，网络超时上限 20 秒。</p>
          {testResult && <div className="model-feedback success" role="status">{testResult}</div>}
          <div className="model-storage-note"><KeyRound size={16} /><span>{settings.storage_protection === 'windows-dpapi' ? '密钥使用当前 Windows 账户加密，换电脑或账户后需重新输入。' : '密钥保存在本机权限受限的文件中（未加密），请保护工作区和备份。'} 配置切换对新任务生效，已运行任务不受影响。</span></div>
          {selectedId && <div className="model-delete-row">
            {!confirmDelete ? <button className="model-delete" type="button" disabled={locked || selectedId === settings.active_profile_id} onClick={() => setConfirmDelete(true)}><Trash2 size={14} />删除配置</button> : <><span>删除这套配置及其本机密钥？</span><button className="model-delete" type="button" disabled={locked} onClick={() => void remove()}>确认删除</button><button className="secondary-button" type="button" onClick={() => setConfirmDelete(false)}>取消</button></>}
            {selectedId === settings.active_profile_id && <small>切换到其他配置后可删除。</small>}
          </div>}
        </form>
      </div>
    </>}
  </section>;
}
