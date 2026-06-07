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


type ChatStreamHandlers = {
  onUser?: (message: Message) => void;
  onDelta?: (chunk: string) => void;
};


function parseSseEvent(block: string): { event: string; data: string } | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: dataLines.join("\n"),
  };
}


export async function sendChatStream(
  storyId: string,
  payload: {
    content: string;
    branch_id: string;
    parent_message_id: string | null;
  },
  handlers?: ChatStreamHandlers
): Promise<{ branch_id: string; messages: Message[] }> {
  const response = await fetch(`${API_BASE}/api/stories/${storyId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("ストリーム応答を受信できませんでした");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: { branch_id: string; messages: Message[] } | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    while (true) {
      const boundary = buffer.indexOf("\n\n");
      if (boundary < 0) {
        break;
      }

      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const event = parseSseEvent(block);
      if (!event) {
        continue;
      }

      if (event.event === "delta") {
        handlers?.onDelta?.(event.data);
        continue;
      }

      if (event.event === "user") {
        try {
          handlers?.onUser?.(JSON.parse(event.data) as Message);
        } catch {
          // Ignore malformed side-channel messages.
        }
        continue;
      }

      if (event.event === "error") {
        let message = event.data || "ストリーム送信に失敗しました";
        try {
          const parsed = JSON.parse(event.data) as { message?: string; detail?: string };
          message = parsed.message || parsed.detail || message;
        } catch {
          // Keep original error text when not JSON.
        }
        throw new Error(message);
      }

      if (event.event === "done") {
        donePayload = JSON.parse(event.data) as { branch_id: string; messages: Message[] };
      }
    }
  }

  if (!donePayload) {
    throw new Error("ストリームが完了する前に切断されました");
  }

  return donePayload;
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
