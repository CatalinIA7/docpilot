# DocPilot V1.1

DocPilot is a frontend prototype for an AI document workspace. Users can add document metadata, manage a local library, ask questions in a chat interface, and preview how sourced AI answers will work.

## Features

- Drag-and-drop and click-to-upload interface
- PDF, TXT, DOC and DOCX validation
- 10 MB file-size limit
- Duplicate-file detection
- Document deletion
- Toast success and error notifications
- Simulated AI response with prototype citation
- Typing indicator
- New-conversation reset
- Recent-question history
- Chat and document metadata persistence with `localStorage`
- Documents and Settings views
- Responsive layout

## Important limitation

V1.1 does not read the contents of uploaded files. Browsers only retain document metadata in this prototype. A future FastAPI backend will handle uploads, text extraction, retrieval and real AI responses.

## Run locally

Open `index.html` in a browser, or use the VS Code Live Server extension.

## Roadmap

- V2: FastAPI backend and real file uploads
- V3: text extraction and OpenAI integration
- V4: embeddings, retrieval and page-level citations
- V5: authentication and private cloud workspaces

## Technologies

HTML, CSS and vanilla JavaScript.
