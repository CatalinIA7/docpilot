"use strict";
const API_URL = "http://127.0.0.1:8000";
let mode = "login";
let token = localStorage.getItem("docpilot_token");

const $ = (selector) => document.querySelector(selector);
const authView = $("#auth-view");
const appView = $("#app-view");
const authError = $("#auth-error");
const documentList = $("#document-list");
const emptyState = $("#empty-state");

function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  return fetch(`${API_URL}${path}`, { ...options, headers }).then(async (response) => {
    if (response.status === 204) return null;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  });
}

function setMode(nextMode) {
  mode = nextMode;
  $("#login-tab").classList.toggle("active", mode === "login");
  $("#register-tab").classList.toggle("active", mode === "register");
  $("#auth-submit").textContent = mode === "login" ? "Log in" : "Create account";
  $("#password").autocomplete = mode === "login" ? "current-password" : "new-password";
  authError.textContent = "";
}

async function showApp() {
  try {
    const user = await api("/auth/me");
    $("#user-email").textContent = user.email;
    authView.classList.add("hidden");
    appView.classList.remove("hidden");
    await loadDocuments();
  } catch {
    logout();
  }
}

function logout() {
  token = null;
  localStorage.removeItem("docpilot_token");
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
}

async function loadDocuments() {
  const documents = await api("/documents");
  documentList.innerHTML = "";
  emptyState.classList.toggle("hidden", documents.length > 0);
  $("#document-count").textContent = `${documents.length} document${documents.length === 1 ? "" : "s"}`;
  for (const document of documents) {
    const card = window.document.createElement("article");
    card.className = "document-card";
    card.innerHTML = `<h3></h3><div class="meta"></div><p class="preview"></p><button class="delete-button">Delete</button>`;
    card.querySelector("h3").textContent = document.filename;
    card.querySelector(".meta").textContent = `${document.file_type.toUpperCase()} • ${document.word_count} words • ${formatBytes(document.size)}`;
    card.querySelector(".preview").textContent = document.preview || "No extractable text found.";
    card.querySelector("button").addEventListener("click", async () => {
      if (!confirm(`Delete ${document.filename}?`)) return;
      await api(`/documents/${document.id}`, { method: "DELETE" });
      await loadDocuments();
    });
    documentList.appendChild(card);
  }
}

async function upload(file) {
  const formData = new FormData();
  formData.append("file", file);
  showNotice(`Uploading ${file.name}…`);
  try {
    await api("/documents", { method: "POST", body: formData });
    showNotice(`${file.name} uploaded successfully.`);
    await loadDocuments();
  } catch (error) {
    showNotice(error.message);
  }
}

function showNotice(message) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.remove("hidden");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

$("#login-tab").addEventListener("click", () => setMode("login"));
$("#register-tab").addEventListener("click", () => setMode("register"));
$("#logout-button").addEventListener("click", logout);
$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";
  try {
    const result = await api(`/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify({ email: $("#email").value, password: $("#password").value }),
    });
    token = result.access_token;
    localStorage.setItem("docpilot_token", token);
    await showApp();
  } catch (error) {
    authError.textContent = error.message;
  }
});

const fileInput = $("#file-input");
const dropZone = $("#drop-zone");
$("#upload-button").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => { if (fileInput.files[0]) upload(fileInput.files[0]); fileInput.value = ""; });
["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", (event) => { if (event.dataTransfer.files[0]) upload(event.dataTransfer.files[0]); });
dropZone.addEventListener("click", () => fileInput.click());

if (token) showApp();
