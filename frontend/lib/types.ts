export type Story = {
  id: string;
  title: string;
  active_branch_id: string;
  llm_model: string;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  story_id: string;
  branch_id: string;
  parent_message_id: string | null;
  role: "user" | "assistant";
  kind: "user" | "dialogue" | "narration" | "chat";
  content: string;
  created_at: string;
};

export type MessagePage = {
  items: Message[];
  has_more: boolean;
  next_before_message_id: string | null;
};

export type BranchSummary = {
  branch_id: string;
  message_count: number;
  last_message_at: string | null;
  is_active: boolean;
};

export type StorySettings = {
  story_id: string;
  context_size: number;
  character_name: string;
  temperature: number;
  top_p: number;
};

export type IllustrationJob = {
  id: string;
  story_id: string;
  message_id: string | null;
  source_text: string;
  status: "queued" | "running" | "done" | "error";
  image_url: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};
