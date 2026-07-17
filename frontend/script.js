"use strict";

const STORAGE_KEY = "docpilot-v1.1-state";
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["pdf", "txt", "doc", "docx"]);

const elements = {
  uploadButton: document.querySelector("#upload-button"),
  fileInput: document.querySelector("#file-input"),
  dropZone: document.querySelector("#drop-zone"),
  documentList: document.querySelector("#document-list"),
  documentLibrary: document.querySelector("#document-library"),
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  chatMessages: document.querySelector("#chat-messages"),
  historyList: document.querySelector("#history-list"),
  newChatButton: document.querySelector("#new-chat-button"),
  navItems: document.querySelectorAll(".nav-item"),
  views: document.querySelectorAll(".view"),
  viewTitle: document.querySelector("#view-title"),
  persistenceToggle: document.querySelector("#persistence-toggle"),
  clearDataButton: document.querySelector("#clear-data-button"),
  toastRegion: document.querySelector("#toast-region")
};

let state = loadState();
let isReplying = false;

init();

function init() {
  bindEvents();
  renderAll();
}

function defaultState() {
  return {
    persistence: true,
    documents: [],
    messages: [
      {
        id: crypto.randomUUID(),
        sender: "assistant",
        text: "Upload a document and ask me questions about its content. This frontend prototype validates files and simulates sourced answers."
      }
    ],
    history: []
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw);
    return { ...defaultState(), ...parsed };
  } catch {
    return defaultState();
  }
}

function saveState() {
  if (state.persistence) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function bindEvents() {
  elements.uploadButton.addEventListener("click", openFilePicker);
  elements.dropZone.addEventListener("click", openFilePicker);
  elements.dropZone.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openFilePicker();
    }
  });
  elements.fileInput.addEventListener("change", () => {
    handleFiles(elements.fileInput.files);
    elements.fileInput.value = "";
  });
  ["dragenter", "dragover"].forEach(type => elements.dropZone.addEventListener(type, event => {
    event.preventDefault();
    elements.dropZone.classList.add("is-dragging");
  }));
  elements.dropZone.addEventListener("dragleave", event => {
    if (!event.relatedTarget || !elements.dropZone.contains(event.relatedTarget)) {
      elements.dropZone.classList.remove("is-dragging");
    }
  });
  elements.dropZone.addEventListener("drop", event => {
    event.preventDefault();
    elements.dropZone.classList.remove("is-dragging");
    handleFiles(event.dataTransfer.files);
  });
  elements.documentList.addEventListener("click", handleDeleteClick);
  elements.documentLibrary.addEventListener("click", handleDeleteClick);
  elements.chatForm.addEventListener("submit", handleMessageSubmit);
  elements.messageInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      elements.chatForm.requestSubmit();
    }
  });
  elements.newChatButton.addEventListener("click", startNewConversation);
  elements.navItems.forEach(item => item.addEventListener("click", () => switchView(item.dataset.view)));
  elements.persistenceToggle.addEventListener("change", () => {
    state.persistence = elements.persistenceToggle.checked;
    saveState();
    showToast(state.persistence ? "Local session saving enabled." : "Local session saving disabled.", "success");
  });
  elements.clearDataButton.addEventListener("click", clearLocalData);
}

function openFilePicker() {
  elements.fileInput.click();
}

function handleFiles(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;

  let added = 0;
  files.forEach(file => {
    const extension = getExtension(file.name);
    if (!ALLOWED_EXTENSIONS.has(extension)) {
      showToast(`${file.name}: unsupported file type.`, "error");
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      showToast(`${file.name}: file exceeds the 10 MB limit.`, "error");
      return;
    }
    const duplicate = state.documents.some(doc => doc.name.toLowerCase() === file.name.toLowerCase() && doc.size === file.size);
    if (duplicate) {
      showToast(`${file.name}: already added.`, "error");
      return;
    }
    state.documents.push({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      extension,
      addedAt: new Date().toISOString()
    });
    added += 1;
  });

  if (added) {
    saveState();
    renderDocuments();
    showToast(`${added} document${added === 1 ? "" : "s"} added.`, "success");
  }
}

function handleDeleteClick(event) {
  const button = event.target.closest("[data-delete-document]");
  if (!button) return;
  const document = state.documents.find(doc => doc.id === button.dataset.deleteDocument);
  state.documents = state.documents.filter(doc => doc.id !== button.dataset.deleteDocument);
  saveState();
  renderDocuments();
  showToast(`${document?.name || "Document"} removed.`, "success");
}

async function handleMessageSubmit(event) {
  event.preventDefault();
  if (isReplying) return;
  const text = elements.messageInput.value.trim();
  if (!text) return;

  addMessage({ sender: "user", text });
  elements.messageInput.value = "";
  addHistoryItem(text);

  isReplying = true;
  elements.sendButton.disabled = true;
  const typingId = showTypingIndicator();
  await delay(650);
  removeMessageElement(typingId);

  const response = buildPrototypeResponse(text);
  addMessage(response);
  isReplying = false;
  elements.sendButton.disabled = false;
  elements.messageInput.focus();
}

function buildPrototypeResponse(question) {
  if (!state.documents.length) {
    return { sender: "assistant", text: "Please upload a supported document first. I can currently demonstrate the interface, while real document reading will arrive with the backend." };
  }

  const firstDocument = state.documents[0];
  return {
    sender: "assistant",
    text: `I received your question: “${question}”\n\nThis is a simulated V1.1 answer. The next backend version will extract the document text, retrieve matching passages, and generate a grounded response.`,
    citations: [{ documentName: firstDocument.name, meta: "Prototype source · Document metadata only" }]
  };
}

function addMessage(message) {
  const fullMessage = { id: crypto.randomUUID(), ...message };
  state.messages.push(fullMessage);
  saveState();
  renderMessage(fullMessage);
  scrollChatToBottom();
}

function renderMessage(message) {
  const article = document.createElement("article");
  article.className = `message ${message.sender}-message`;
  article.dataset.messageId = message.id;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = message.sender === "assistant" ? "AI" : "You";

  const wrapper = document.createElement("div");
  wrapper.className = "message-content-wrapper";
  const content = document.createElement("div");
  content.className = "message-content";
  const paragraph = document.createElement("p");
  paragraph.textContent = message.text;
  content.appendChild(paragraph);
  wrapper.appendChild(content);

  if (message.citations?.length) {
    const citations = document.createElement("div");
    citations.className = "citation-cards";
    message.citations.forEach((citation, index) => {
      const card = document.createElement("div");
      card.className = "citation-card";
      const label = document.createElement("span");
      label.className = "citation-label";
      label.textContent = `Source ${index + 1}`;
      const name = document.createElement("strong");
      name.textContent = citation.documentName;
      const meta = document.createElement("span");
      meta.className = "citation-meta";
      meta.textContent = citation.meta;
      card.append(label, name, meta);
      citations.appendChild(card);
    });
    wrapper.appendChild(citations);
  }

  article.append(avatar, wrapper);
  elements.chatMessages.appendChild(article);
}

function showTypingIndicator() {
  const id = crypto.randomUUID();
  const article = document.createElement("article");
  article.className = "message assistant-message";
  article.dataset.messageId = id;
  article.innerHTML = '<div class="avatar">AI</div><div class="message-content"><div class="typing-dots" aria-label="DocPilot is typing"><span></span><span></span><span></span></div></div>';
  elements.chatMessages.appendChild(article);
  scrollChatToBottom();
  return id;
}

function removeMessageElement(id) {
  elements.chatMessages.querySelector(`[data-message-id="${id}"]`)?.remove();
}

function addHistoryItem(question) {
  state.history.unshift({ id: crypto.randomUUID(), title: question.slice(0, 48), createdAt: new Date().toISOString() });
  state.history = state.history.slice(0, 5);
  saveState();
  renderHistory();
}

function startNewConversation() {
  state.messages = [{ id: crypto.randomUUID(), sender: "assistant", text: "New conversation started. Upload a document or ask another question." }];
  saveState();
  renderMessages();
  switchView("chat");
  showToast("New conversation started.", "success");
}

function switchView(viewName) {
  const titleMap = { chat: "Chat with your documents", documents: "Document library", settings: "Settings" };
  elements.navItems.forEach(item => item.classList.toggle("active", item.dataset.view === viewName));
  elements.views.forEach(view => {
    const active = view.id === `${viewName}-view`;
    view.hidden = !active;
    view.classList.toggle("active-view", active && viewName === "chat");
  });
  elements.viewTitle.textContent = titleMap[viewName];
}

function clearLocalData() {
  localStorage.removeItem(STORAGE_KEY);
  state = defaultState();
  renderAll();
  switchView("chat");
  showToast("Local DocPilot data cleared.", "success");
}

function renderAll() {
  elements.persistenceToggle.checked = state.persistence;
  renderDocuments();
  renderMessages();
  renderHistory();
}

function renderDocuments() {
  elements.documentList.innerHTML = "";
  elements.documentLibrary.innerHTML = "";
  if (!state.documents.length) {
    elements.documentList.innerHTML = '<p class="empty-message">No documents uploaded.</p>';
    elements.documentLibrary.innerHTML = '<p class="empty-message">Your library is empty.</p>';
    return;
  }

  state.documents.forEach(doc => {
    const sidebarItem = document.createElement("div");
    sidebarItem.className = "document-item";
    sidebarItem.innerHTML = `<div class="document-icon">${escapeHTML(doc.extension.toUpperCase())}</div><div class="document-meta"><div class="document-name"></div><div class="document-details">${formatFileSize(doc.size)} · Ready</div></div><button class="delete-document" type="button" data-delete-document="${doc.id}" aria-label="Remove document">×</button>`;
    sidebarItem.querySelector(".document-name").textContent = doc.name;
    elements.documentList.appendChild(sidebarItem);

    const card = document.createElement("article");
    card.className = "library-card";
    const name = document.createElement("strong");
    name.textContent = doc.name;
    const meta = document.createElement("span");
    meta.textContent = `${doc.extension.toUpperCase()} · ${formatFileSize(doc.size)}`;
    const remove = document.createElement("button");
    remove.className = "danger-button";
    remove.type = "button";
    remove.dataset.deleteDocument = doc.id;
    remove.textContent = "Remove";
    card.append(name, meta, remove);
    elements.documentLibrary.appendChild(card);
  });
}

function renderMessages() {
  elements.chatMessages.innerHTML = "";
  state.messages.forEach(renderMessage);
  scrollChatToBottom();
}

function renderHistory() {
  elements.historyList.innerHTML = "";
  if (!state.history.length) {
    elements.historyList.innerHTML = '<p class="empty-message">No recent chats.</p>';
    return;
  }
  state.history.forEach(item => {
    const button = document.createElement("button");
    button.className = "history-item";
    button.type = "button";
    const title = document.createElement("span");
    title.className = "history-title";
    title.textContent = item.title;
    const meta = document.createElement("span");
    meta.className = "history-meta";
    meta.textContent = formatRelativeDate(item.createdAt);
    button.append(title, meta);
    button.addEventListener("click", () => switchView("chat"));
    elements.historyList.appendChild(button);
  });
}

function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastRegion.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3200);
}

function getExtension(filename) {
  return filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRelativeDate(dateString) {
  const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.floor(hours / 24)} day(s) ago`;
}

function scrollChatToBottom() {
  requestAnimationFrame(() => { elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight; });
}

function delay(ms) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

function escapeHTML(value) {
  return value.replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}
