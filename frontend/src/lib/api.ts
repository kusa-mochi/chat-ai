import {
  ChatResponse,
  HistoryResponse,
  StoryDetail,
  StoryImage,
  StorySettings,
  StorySummary
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {})
    },
    cache: 'no-store'
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function listStories(): Promise<StorySummary[]> {
  return request<StorySummary[]>('/stories');
}

export async function createStory(title?: string): Promise<StoryDetail> {
  return request<StoryDetail>('/stories', {
    method: 'POST',
    body: JSON.stringify({ title })
  });
}

export async function getStory(storyId: string): Promise<StoryDetail> {
  return request<StoryDetail>(`/stories/${storyId}`);
}

export async function getEntries(storyId: string, limit = 80, beforeEntryId?: number): Promise<HistoryResponse> {
  const before = beforeEntryId ? `&before_entry_id=${beforeEntryId}` : '';
  return request<HistoryResponse>(`/stories/${storyId}/entries?limit=${limit}${before}`);
}

export async function sendMessage(storyId: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>(`/stories/${storyId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message })
  });
}

export async function updateSettings(
  storyId: string,
  payload: Partial<Pick<StorySettings, 'context_size' | 'pre_prompt' | 'ai_character_name' | 'ai_persona' | 'temperature'>>
): Promise<StorySettings> {
  return request<StorySettings>(`/stories/${storyId}/settings`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export async function rewindStory(storyId: string, entryId: number): Promise<{ deactivated_entry_ids: number[] }> {
  return request<{ deactivated_entry_ids: number[] }>(`/stories/${storyId}/rewind`, {
    method: 'POST',
    body: JSON.stringify({ entry_id: entryId })
  });
}

export async function generateImage(
  storyId: string,
  sourceText: string,
  sourceEntryId?: number
): Promise<StoryImage> {
  return request<StoryImage>(`/stories/${storyId}/images`, {
    method: 'POST',
    body: JSON.stringify({ source_text: sourceText, source_entry_id: sourceEntryId })
  });
}

export async function listImages(storyId: string): Promise<StoryImage[]> {
  return request<StoryImage[]>(`/stories/${storyId}/images`);
}

export function toAbsoluteImageUrl(imageUrl: string): string {
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
    return imageUrl;
  }
  return `${API_BASE}${imageUrl}`;
}
