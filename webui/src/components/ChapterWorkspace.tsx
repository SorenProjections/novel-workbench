import { BookOpenText, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { formatDate, formatNumber } from '../format';
import type { ChapterSummary } from '../types';

interface ChapterWorkspaceProps {
  chapters: ChapterSummary[];
  chapterText: string;
  selectedChapterId: string;
  onSelect: (chapterId: string) => void;
}

export default function ChapterWorkspace({ chapters, chapterText, selectedChapterId, onSelect }: ChapterWorkspaceProps) {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => chapters.filter((chapter) => {
    const needle = query.trim().toLowerCase();
    return !needle || `${chapter.title || ''} ${chapter.chapter_id} ${chapter.chapter_index}`.toLowerCase().includes(needle);
  }), [chapters, query]);
  const selected = chapters.find((chapter) => chapter.chapter_id === selectedChapterId);

  return (
    <section className="workspace-view chapter-workspace">
      <header className="workspace-heading">
        <div>
          <span className="eyebrow">发布层</span>
          <h1>章节</h1>
        </div>
        <div className="search-field">
          <Search size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索章节" />
        </div>
      </header>
      {chapters.length === 0 ? (
        <div className="empty-state"><BookOpenText size={24} /><b>暂无已发布章节</b></div>
      ) : (
        <div className="chapter-split">
          <div className="chapter-index">
            {filtered.map((chapter) => (
              <button key={chapter.chapter_id} className={selectedChapterId === chapter.chapter_id ? 'active' : ''} onClick={() => onSelect(chapter.chapter_id)}>
                <span>第 {chapter.chapter_index} 章</span>
                <b>{chapter.title || chapter.chapter_id}</b>
                <small>{chapter.chapter_intent || '未标注意图'} · {formatNumber(chapter.word_count)} 字</small>
              </button>
            ))}
          </div>
          <article className="chapter-reader">
            {selected ? (
              <>
                <header>
                  <span>{formatDate(selected.committed_at || selected.created_at)}</span>
                  <h2>{selected.title || `第 ${selected.chapter_index} 章`}</h2>
                </header>
                <div className="prose">{chapterText || '正在读取章节…'}</div>
              </>
            ) : <div className="empty-state"><BookOpenText size={24} /><b>选择一章开始阅读</b></div>}
          </article>
        </div>
      )}
    </section>
  );
}
