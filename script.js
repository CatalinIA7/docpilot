"use strict";

const uploadButton = document.querySelector("#upload-button");
const fileInput = document.querySelector("#file-input");
const documentList = document.querySelector("#document-list");

const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const chatMessages = document.querySelector("#chat-messages");

const uploadedDocuments = [];

uploadButton.addEventListener("click", () => {
  fileInput.click();
});

fileInput.addEventListener("change", () => {
  const files = Array.from(fileInput.files);

  files.forEach((file) => {
    uploadedDocuments.push({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size
    });
  });

  renderDocuments();
  fileInput.value = "";
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
    documentElement.textContent = document.name;
    documentElement.title = document.name;

    documentList.appendChild(documentElement);
  });
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