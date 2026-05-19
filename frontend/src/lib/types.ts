export type EntryRole = 'user' | 'ai_character' | 'narration';

export interface StorySummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface StorySettings {
  story_id: string;
  context_size: number;
  pre_prompt: string;
  ai_character_name: string;
  ai_persona: string;
  temperature: number;
}

export interface StoryDetail {
  story: StorySummary;
  settings: StorySettings;
}

export interface StoryEntry {
  id: number;
  story_id: string;
  role: EntryRole;
  content: string;
  turn_index: number;
  is_active: boolean;
  parent_entry_id: number | null;
  created_at: string;
}

export interface HistoryResponse {
  items: StoryEntry[];
}

export interface ChatResponse {
  user_entry: StoryEntry;
  ai_dialogue_entry: StoryEntry;
  narration_entry: StoryEntry;
}

export interface StoryImage {
  id: number;
  story_id: string;
  source_entry_id: number | null;
  source_text: string;
  prompt: string;
  image_url: string;
  status: string;
  created_at: string;
}
