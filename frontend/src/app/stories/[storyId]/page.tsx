'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { FormEvent, useEffect, useMemo, useState } from 'react';

import {
  generateImage,
  getEntries,
  getStory,
  listImages,
  rewindStory,
  sendMessage,
  toAbsoluteImageUrl,
  updateSettings
} from '../../../lib/api';
import { StoryEntry, StoryImage, StorySettings } from '../../../lib/types';

const ROLE_LABEL: Record<StoryEntry['role'], string> = {
  user: 'あなた',
  ai_character: 'AI登場人物',
  narration: 'ナレーション'
};

export default function StoryPage() {
  const params = useParams<{ storyId: string }>();
  const storyId = params.storyId;

  const [title, setTitle] = useState('');
  const [entries, setEntries] = useState<StoryEntry[]>([]);
  const [images, setImages] = useState<StoryImage[]>([]);
  const [settings, setSettings] = useState<StorySettings | null>(null);
  const [message, setMessage] = useState('');
  const [imageText, setImageText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [story, history, storyImages] = await Promise.all([
          getStory(storyId),
          getEntries(storyId, 60),
          listImages(storyId)
        ]);
        setTitle(story.story.title);
        setSettings(story.settings);
        setEntries(history.items);
        setImages(storyImages);
        setHasMore(history.items.length >= 60);
      } catch (e) {
        setError(e instanceof Error ? e.message : '読み込みに失敗しました');
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [storyId]);

  const canSubmit = message.trim().length > 0 && !sending;

  const submitMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    setSending(true);
    setError(null);
    try {
      const response = await sendMessage(storyId, message.trim());
      setEntries((prev) => [...prev, response.user_entry, response.ai_dialogue_entry, response.narration_entry]);
      setMessage('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'メッセージ送信に失敗しました');
    } finally {
      setSending(false);
    }
  };

  const saveSettings = async () => {
    if (!settings) {
      return;
    }
    setSavingSettings(true);
    setError(null);
    try {
      const updated = await updateSettings(storyId, {
        context_size: settings.context_size,
        pre_prompt: settings.pre_prompt,
        ai_character_name: settings.ai_character_name,
        ai_persona: settings.ai_persona,
        temperature: settings.temperature
      });
      setSettings(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : '設定保存に失敗しました');
    } finally {
      setSavingSettings(false);
    }
  };

  const loadOlder = async () => {
    if (entries.length === 0 || loadingOlder || !hasMore) {
      return;
    }
    setLoadingOlder(true);
    setError(null);
    try {
      const oldestId = entries[0]?.id;
      const history = await getEntries(storyId, 60, oldestId);
      setEntries((prev) => [...history.items, ...prev]);
      if (history.items.length < 60) {
        setHasMore(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '過去ログ取得に失敗しました');
    } finally {
      setLoadingOlder(false);
    }
  };

  const doRewind = async (entryId: number) => {
    const confirmed = window.confirm('この地点まで巻き戻します。以降の文章は非表示になります。続行しますか？');
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      await rewindStory(storyId, entryId);
      const [history, storyImages] = await Promise.all([getEntries(storyId, 60), listImages(storyId)]);
      setEntries(history.items);
      setImages(storyImages);
      setHasMore(history.items.length >= 60);
    } catch (e) {
      setError(e instanceof Error ? e.message : '巻き戻しに失敗しました');
    }
  };

  const createImage = async (sourceText: string, sourceEntryId?: number) => {
    if (!sourceText.trim()) {
      return;
    }
    setGeneratingImage(true);
    setError(null);
    try {
      const image = await generateImage(storyId, sourceText.trim(), sourceEntryId);
      setImages((prev) => [image, ...prev]);
      setImageText('');
    } catch (e) {
      setError(e instanceof Error ? e.message : '挿絵生成に失敗しました');
    } finally {
      setGeneratingImage(false);
    }
  };

  const createImageFromSelection = async () => {
    const selection = window.getSelection()?.toString().trim() ?? '';
    if (!selection) {
      setError('文章を選択してから「選択テキストで挿絵生成」を押してください。');
      return;
    }
    await createImage(selection);
  };

  const roleClass = (role: StoryEntry['role']): string => {
    if (role === 'user') return 'entry user';
    if (role === 'ai_character') return 'entry ai-character';
    return 'entry narration';
  };

  const imageCountLabel = useMemo(() => `${images.length}枚`, [images.length]);

  if (loading) {
    return <main className="story-shell">読み込み中...</main>;
  }

  return (
    <main className="story-shell">
      <header className="story-header">
        <Link href="/" className="back-link">
          一覧に戻る
        </Link>
        <h1>{title}</h1>
        <p>挿絵: {imageCountLabel}</p>
      </header>

      {error && <p className="error-text">{error}</p>}

      <section className="story-layout">
        <aside className="settings-panel">
          <h2>物語設定</h2>
          {settings && (
            <>
              <label>
                コンテキストサイズ
                <input
                  type="number"
                  min={5}
                  max={200}
                  value={settings.context_size}
                  onChange={(e) =>
                    setSettings((prev) => (prev ? { ...prev, context_size: Number(e.target.value) } : prev))
                  }
                />
              </label>

              <label>
                プレプロンプト
                <textarea
                  rows={4}
                  value={settings.pre_prompt}
                  onChange={(e) => setSettings((prev) => (prev ? { ...prev, pre_prompt: e.target.value } : prev))}
                />
              </label>

              <label>
                AI登場人物名
                <input
                  type="text"
                  value={settings.ai_character_name}
                  onChange={(e) =>
                    setSettings((prev) => (prev ? { ...prev, ai_character_name: e.target.value } : prev))
                  }
                />
              </label>

              <label>
                人格設定
                <textarea
                  rows={4}
                  value={settings.ai_persona}
                  onChange={(e) => setSettings((prev) => (prev ? { ...prev, ai_persona: e.target.value } : prev))}
                />
              </label>

              <label>
                Temperature
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={settings.temperature}
                  onChange={(e) =>
                    setSettings((prev) => (prev ? { ...prev, temperature: Number(e.target.value) } : prev))
                  }
                />
              </label>

              <button className="secondary-btn" onClick={saveSettings} disabled={savingSettings}>
                {savingSettings ? '保存中...' : '設定を保存'}
              </button>
            </>
          )}

          <h2>挿絵生成</h2>
          <button className="secondary-btn" onClick={createImageFromSelection} disabled={generatingImage}>
            選択テキストで挿絵生成
          </button>
          <textarea
            rows={4}
            placeholder="任意の段落を貼り付けて挿絵生成"
            value={imageText}
            onChange={(e) => setImageText(e.target.value)}
          />
          <button className="secondary-btn" onClick={() => createImage(imageText)} disabled={generatingImage}>
            {generatingImage ? '生成中...' : 'このテキストで生成'}
          </button>
        </aside>

        <section className="chat-panel">
          <div className="timeline-tools">
            <button className="ghost-btn" disabled={!hasMore || loadingOlder} onClick={loadOlder}>
              {loadingOlder ? '読み込み中...' : hasMore ? '過去を読み込む' : 'これ以上過去ログはありません'}
            </button>
          </div>

          <div className="entries-panel">
            {entries.map((entry) => (
              <article key={entry.id} className={roleClass(entry.role)}>
                <header>
                  <strong>{ROLE_LABEL[entry.role]}</strong>
                  <div className="entry-actions">
                    <button className="mini-btn" onClick={() => createImage(entry.content, entry.id)}>
                      この文で挿絵
                    </button>
                    <button className="mini-btn warning" onClick={() => doRewind(entry.id)}>
                      ここまで巻き戻す
                    </button>
                  </div>
                </header>
                <p>{entry.content}</p>
              </article>
            ))}
          </div>

          <form className="chat-input" onSubmit={submitMessage}>
            <textarea
              rows={4}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="物語に加えたい文章を入力してください"
            />
            <button className="primary-btn" type="submit" disabled={!canSubmit}>
              {sending ? '送信中...' : '送信'}
            </button>
          </form>
        </section>

        <aside className="images-panel">
          <h2>挿絵ギャラリー</h2>
          <div className="images-grid">
            {images.map((image) => (
              <figure key={image.id} className="image-card">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={toAbsoluteImageUrl(image.image_url)} alt="挿絵" loading="lazy" />
                <figcaption>{image.source_text.slice(0, 60)}</figcaption>
              </figure>
            ))}
            {images.length === 0 && <p>まだ挿絵はありません。</p>}
          </div>
        </aside>
      </section>
    </main>
  );
}
