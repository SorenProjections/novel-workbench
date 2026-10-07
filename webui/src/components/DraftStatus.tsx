interface DraftStatusProps {
  before: string;
  after: string;
  savedAt: string;
  warning: string;
  conflict: boolean;
}

export default function DraftStatus({ before, after, savedAt, warning, conflict }: DraftStatusProps) {
  const dirty = before !== after;
  return <div className="draft-status" role="status">
    {warning || (conflict ? '来源版本已变化；已恢复本地草稿，请对照当前版本检查' : savedAt ? `本地草稿已保存 ${savedAt}` : '当前内容与已保存版本一致')}
    {dirty && <details className="draft-diff">
      <summary>查看修改前后对照 · {before.length} → {after.length} 字符</summary>
      <div className="draft-diff-columns"><section><b>当前保存版本</b><pre>{before}</pre></section><section><b>本次修改</b><pre>{after}</pre></section></div>
    </details>}
  </div>;
}
