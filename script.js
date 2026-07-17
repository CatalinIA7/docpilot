"use strict";

const uploadButton = document.querySelector("#upload-button");
const fileInput = document.querySelector("#file-input");
const dropZone = document.querySelector("#drop-zone");
const documentList = document.querySelector("#document-list");

const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const chatMessages = document.querySelector("#chat-messages");

const uploadedDocuments = [];

uploadButton.addEventListener("click", () => {
  fileInput.click();
});

dropZone.addEventListener("click", () => {
  fileInput.click();
});

dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

function handleFiles(files) {
  const selectedFiles = Array.from(files);

  selectedFiles.forEach((file) => {
    uploadedDocuments.push({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size
    });
  });

  renderDocuments();
}

fileInput.addEventListener("change", () => {
  handleFiles(fileInput.files);
  fileInput.value = "";
});

dropZone.addEventListener("dragenter", (event) => {
  event.preventDefault();
  dropZone.classList.add("is-dragging");
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("is-dragging");
});

dropZone.addEventListener("dragleave", (event) => {
  if (event.relatedTarget && dropZone.contains(event.relatedTarget)) {
    return;
  }

  dropZone.classList.remove("is-dragging");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragging");
  handleFiles(event.dataTransfer.files);
});

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();

  if (!message) {
    return;
  }

  addMessage(message, "user");

  messageInput.value = "";

  window.setTimeout(() => {
    const response =
      uploadedDocuments.length > 0
        ? "This is a prototype response. In the next version, the backend will search your uploaded document and generate a sourced answer."
        : "Please upload a document before asking questions about its content.";

    addMessage(response, "assistant");
  }, 500);
});

function renderDocuments() {
  documentList.innerHTML = "";

  if (uploadedDocuments.length === 0) {
    documentList.innerHTML =
      '<p class="empty-message">No documents uploaded.</p>';

    return;
  }

  uploadedDocuments.forEach((document) => {
    const documentElement = document.createElement("div");
    documentElement.className = "document-item";
    documentElement.title = document.name;

    const icon = document.createElement("div");
    icon.className = "document-icon";
    icon.textContent = "DOC";

    const meta = document.createElement("div");
    meta.className = "document-meta";

    const name = document.createElement("div");
    name.className = "document-name";
    name.textContent = document.name;

    const details = document.createElement("div");
    details.className = "document-details";
    details.textContent = `${formatFileSize(document.size)} • Ready for chat`;

    meta.append(name, details);
    documentElement.append(icon, meta);
    documentList.appendChild(documentElement);
  });
}

function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function addMessage(text, sender) {
  const article = document.createElement("article");

  article.className = `message ${sender}-message`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = sender === "assistant" ? "AI" : "You";

  const content = document.createElement("div");
  content.className = "message-content";

  const paragraph = document.createElement("p");
  paragraph.textContent = text;

  content.appendChild(paragraph);
  article.append(avatar, content);
  chatMessages.appendChild(article);

  chatMessages.scrollTop = chatMessages.scrollHeight;
}