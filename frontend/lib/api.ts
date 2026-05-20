import type { BranchSummary, IllustrationJob, Message, MessagePage, Story, StorySettings } from "./types";


const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";


async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}


export async function listStories(): Promise<Story[]> {
  return request<Story[]>("/api/stories");
}


export async function createStory(title: string): Promise<Story> {
  return request<Story>("/api/stories", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}


export async function getStory(storyId: string): Promise<Story> {
  return request<Story>(`/api/stories/${storyId}`);
}


export async function listMessages(
  storyId: string,
  branchId: string,
  options?: { limit?: number; beforeMessageId?: string | null }
): Promise<MessagePage> {
  const query = new URLSearchParams();
  query.set("branch_id", branchId);
  query.set("limit", String(options?.limit ?? 40));
  if (options?.beforeMessageId) {
    query.set("before_message_id", options.beforeMessageId);
  }
  return request<MessagePage>(`/api/stories/${storyId}/messages?${query.toString()}`);
}


export async function listBranches(storyId: string): Promise<BranchSummary[]> {
  const data = await request<{ items: BranchSummary[] }>(`/api/stories/${storyId}/branches`);
  return data.items;
}


export async function sendChat(storyId: string, payload: {
  content: string;
  branch_id: string;
  parent_message_id: string | null;
}): Promise<{ branch_id: string; messages: Message[] }> {
  return request<{ branch_id: string; messages: Message[] }>(`/api/stories/${storyId}/chat`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


export async function getSettings(storyId: string): Promise<StorySettings> {
  return request<StorySettings>(`/api/stories/${storyId}/settings`);
}


export async function updateSettings(storyId: string, payload: StorySettings): Promise<StorySettings> {
  return request<StorySettings>(`/api/stories/${storyId}/settings`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}


export async function rewindBranch(storyId: string, messageId: string): Promise<{
  new_branch_id: string;
  from_message_id: string;
  messages: Message[];
}> {
  return request<{ new_branch_id: string; from_message_id: string; messages: Message[] }>(
    `/api/stories/${storyId}/rewind`,
    {
      method: "POST",
      body: JSON.stringify({ message_id: messageId }),
    }
  );
}


export async function createIllustration(storyId: string, sourceText: string, messageId: string | null): Promise<IllustrationJob> {
  return request<IllustrationJob>(`/api/stories/${storyId}/illustrations`, {
    method: "POST",
    body: JSON.stringify({ source_text: sourceText, message_id: messageId }),
  });
}


export async function getIllustration(storyId: string, jobId: string): Promise<IllustrationJob> {
  return request<IllustrationJob>(`/api/stories/${storyId}/illustrations/${jobId}`);
}
