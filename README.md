# Story Chat AI

日本語の自然言語入力をもとに、AIが「もう一人の登場人物」と「ナレーション」を担当して物語を紡ぐWebアプリです。
システム全体をDocker Composeで起動し、文脈はVector Search Engine (Qdrant) に蓄積されます。

## Stack

- Frontend: Next.js (App Router) + TypeScript (`strict: true`)
- Backend: FastAPI + SQLAlchemy + PostgreSQL
- Vector Search Engine: Qdrant
- LLM Runtime: Ollama (Docker container)
- Orchestration: Docker Compose

## Features

- チャット入力から物語生成（日本語）
- AIが登場人物セリフ (`ai_character`) とナレーション (`narration`) を生成
- 新しい物語の作成と複数物語の保存
- 縦スクロールで過去ログを遡って閲覧
- 物語ごとの設定調整
	- コンテキストサイズ
	- プレプロンプト
	- AI登場人物名
	- 人格設定
	- Temperature
- 任意テキスト/任意発話から挿絵生成
- 任意地点までの巻き戻し（以降の発話を非アクティブ化）
- 発話内容のベクトル蓄積と類似検索コンテキスト利用

## Project Layout

```
.
├── backend
│   ├── app
│   │   ├── routes
│   │   ├── ai.py
│   │   ├── image_service.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── vector_store.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend
│   ├── src
│   │   ├── app
│   │   └── lib
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Quick Start

1. 環境変数ファイルを作成

```bash
cp .env.example .env
```

2. Ollamaモデルを取得（初回のみ）

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b-instruct
docker compose exec ollama ollama pull nomic-embed-text
```

3. コンテナ起動

```bash
docker compose up --build
```

4. ブラウザでアクセス

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api/v1`
- Qdrant: `http://localhost:6333`
- Ollama: `http://localhost:11434`

## API Overview

- `GET /api/v1/health`
- `POST /api/v1/stories` 新規物語
- `GET /api/v1/stories` 物語一覧
- `GET /api/v1/stories/{story_id}` 物語詳細
- `GET /api/v1/stories/{story_id}/settings` 設定取得
- `PUT /api/v1/stories/{story_id}/settings` 設定更新
- `GET /api/v1/stories/{story_id}/entries` 発話履歴（`before_entry_id` 対応）
- `POST /api/v1/stories/{story_id}/chat` 物語進行
- `POST /api/v1/stories/{story_id}/rewind` 巻き戻し
- `POST /api/v1/stories/{story_id}/images` 挿絵生成
- `GET /api/v1/stories/{story_id}/images` 挿絵一覧

## Notes

- LAN内で完結するため、テキスト生成と埋め込みはOllamaコンテナを利用します。
- モデル未取得時やOllama到達不可時は、テキスト生成/埋め込みともにフォールバック動作します。
- 現在の挿絵生成はLAN-onlyモードとしてSVGベースのローカル生成です。

## Requirement Mapping

- チャット形式で日本語入力し、AIが物語を継続: 対応
- AIがコンテナ上で稼働: 対応 (`backend` + `ollama`)
- AIが登場人物とナレーションを担当: 対応 (`ai_character`, `narration`)
- Webブラウザ利用: 対応 (`frontend`)
- システム全体をDocker Compose管理: 対応
- 入力/生成文脈をVector Search Engineへ蓄積: 対応 (`qdrant`)
- 物語ごとの設定画面: 対応
- 任意テキストから挿絵生成: 対応
- 途中からやり直し: 対応 (rewind)
- 縦スクロールで過去閲覧: 対応
- 新しい物語ボタン: 対応
- 複数物語保存: 対応
- フロントはNext.js + TypeScript strict: 対応