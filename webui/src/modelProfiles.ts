export type ModelProtocol = 'deepseek' | 'openai' | 'openai_responses' | 'anthropic' | 'gemini';

export interface ModelOptions {
  name: string;
  protocol: ModelProtocol;
  base_url: string;
  model: string;
  timeout_seconds: number;
  max_output_tokens: number;
  max_retries: number;
  token_parameter: 'max_tokens' | 'max_completion_tokens';
  json_mode: boolean;
  send_temperature: boolean;
  thinking: 'steps' | 'disabled' | 'enabled';
  reasoning_effort: '' | 'low' | 'medium' | 'high' | 'max';
}

export interface ModelProfile extends ModelOptions { id: string; has_api_key: boolean }
export interface ModelSettings {
  revision: number;
  profiles: ModelProfile[];
  active_profile_id: string | null;
  storage_protection: 'windows-dpapi' | 'file-permissions';
  environment_label: string;
  disabled: boolean;
  saved_profile_id?: string;
}
export interface ModelDraft extends ModelOptions { api_key: string; clear_api_key: boolean }

export const presets: Array<{ label: string; options: Partial<ModelOptions> }> = [
  { label: 'DeepSeek', options: { name: 'DeepSeek', protocol: 'deepseek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-v4-pro' } },
  { label: 'OpenAI Chat Completions', options: { name: 'OpenAI', protocol: 'openai', base_url: 'https://api.openai.com/v1', token_parameter: 'max_completion_tokens' } },
  { label: 'OpenAI Responses', options: { name: 'OpenAI Responses', protocol: 'openai_responses', base_url: 'https://api.openai.com/v1' } },
  { label: 'Claude / Anthropic', options: { name: 'Claude', protocol: 'anthropic', base_url: 'https://api.anthropic.com/v1' } },
  { label: 'Gemini', options: { name: 'Gemini', protocol: 'gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta' } },
  { label: 'Ollama（本机）', options: { name: 'Ollama', protocol: 'openai', base_url: 'http://localhost:11434/v1', max_output_tokens: 8192, json_mode: false } },
  { label: '自定义兼容服务', options: { name: '', protocol: 'openai', base_url: '' } },
];

export const protocols: Record<ModelProtocol, string> = {
  deepseek: 'DeepSeek', openai: 'OpenAI 兼容 / Chat Completions',
  openai_responses: 'OpenAI Responses', anthropic: 'Claude Messages', gemini: 'Gemini generateContent',
};

export function newDraft(preset = 0): ModelDraft {
  return {
    name: '', protocol: 'openai', base_url: '', model: '', timeout_seconds: 600,
    max_output_tokens: 32768, max_retries: 0, token_parameter: 'max_tokens',
    json_mode: true, send_temperature: false, thinking: 'steps', reasoning_effort: '',
    ...presets[preset].options, api_key: '', clear_api_key: false,
  };
}

export function profileDraft(profile: ModelProfile): ModelDraft {
  const { id: _id, has_api_key: _hasKey, ...options } = profile;
  return { ...options, api_key: '', clear_api_key: false };
}

export function profileBody(draft: ModelDraft, revision: number) {
  const { api_key: key, ...options } = draft;
  return { ...options, revision, ...(key.trim() ? { api_key: key.trim() } : {}) };
}
