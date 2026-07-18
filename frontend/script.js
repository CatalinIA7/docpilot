"use strict";
const API_URL = "http://127.0.0.1:8000";
let mode = "login";
let token = localStorage.getItem("docpilot_token");
let currentDocuments = [];
let isSearchActive = false;
// Track the previous view state so Back can restore list or search results without refetching
let previousView = null;

const $ = (selector) => document.querySelector(selector);
const authView = $("#auth-view");
const appView = $("#app-view");
const authError = $("#auth-error");
const passwordInput = $("#password");
const passwordToggle = $("#password-toggle");
const documentList = $("#document-list");
const emptyState = $("#empty-state");
const documentDetailView = $("#document-detail-view");
const detailLoading = $("#detail-loading");
const detailError = $("#detail-error");
const detailContent = $("#detail-content");
const detailBackButton = $("#detail-back-button");
const detailFilename = $("#detail-filename");
const detailMeta = $("#detail-meta");
const detailFileType = $("#detail-file-type");
const detailUploadDate = $("#detail-upload-date");
const detailWordCount = $("#detail-word-count");
const detailText = $("#detail-text");
const detailDeleteButton = $("#detail-delete-button");
const searchInput = $("#search-input");
const searchError = $("#search-error");
const listLoading = $("#list-loading");
const uploadButton = $("#upload-button");
const searchButton = $("#search-button");
const clearSearchButton = $("#clear-search-button");
const chatQuestion = $("#chat-question");
const chatAskButton = $("#chat-ask-button");
const chatError = $("#chat-error");
const chatAnswerContainer = $("#chat-answer-container");
const chatAnswer = $("#chat-answer");

function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  return fetch(`${API_URL}${path}`, { ...options, headers }).then(async (response) => {
    if (response.status === 204) return null;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || "Request failed");
      error.status = response.status;
      throw error;
    }
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

function setSearchError(message = "") {
  searchError.textContent = message;
}

function setListLoading(isLoading = false) {
  if (!listLoading) return;
  listLoading.classList.toggle("hidden", !isLoading);
  // Disable relevant buttons while loading
  if (uploadButton) uploadButton.disabled = isLoading;
  if (searchButton) searchButton.disabled = isLoading;
  if (clearSearchButton) clearSearchButton.disabled = isLoading;
  // Avoid conflicting messages
  if (isLoading) {
    setSearchError("");
    document.getElementById("notice").classList.add("hidden");
  }
}

function showDocumentDetailView() {
  documentList.classList.add("hidden");
  emptyState.classList.add("hidden");
  documentDetailView.classList.remove("hidden");
}

function hideDocumentDetailView() {
  documentDetailView.classList.add("hidden");
  documentList.classList.remove("hidden");
  emptyState.classList.toggle("hidden", currentDocuments.length > 0);
}

function setDetailState(isLoading = false, errorMessage = "") {
  detailLoading.classList.toggle("hidden", !isLoading);
  detailError.classList.toggle("hidden", !errorMessage);
  detailContent.classList.toggle("hidden", isLoading || Boolean(errorMessage));
  detailError.textContent = errorMessage;
}

function renderDocumentDetail(document) {
  detailFilename.textContent = document.filename;
  detailMeta.textContent = `${document.file_type.toUpperCase()} • ${document.word_count} words`;
  detailFileType.textContent = document.file_type.toUpperCase();
  detailUploadDate.textContent = formatDate(document.created_at);
  detailWordCount.textContent = `${document.word_count}`;
  detailText.textContent = document.text || "No extracted text found.";
  // Track current detail document for deletion
  currentDetailId = document.id;
  currentDetailFilename = document.filename;
  if (detailDeleteButton) {
    detailDeleteButton.disabled = false;
  }
  // Reset chat state for new document
  resetChatPanel();
  setDetailState(false);
  detailContent.classList.remove("hidden");
}

let currentDetailId = null;
let currentDetailFilename = "";
let isDeletingDetail = false;
let isChatPending = false;

function resetChatPanel() {
  if (chatQuestion) chatQuestion.value = "";
  if (chatError) chatError.classList.add("hidden");
  if (chatAnswerContainer) chatAnswerContainer.classList.add("hidden");
  isChatPending = false;
  if (chatAskButton) chatAskButton.disabled = false;
}

async function askAIQuestion() {
  if (isChatPending || !currentDetailId) return;
  const question = (chatQuestion.value || "").trim();
  if (!question) {
    if (chatError) {
      chatError.textContent = "Please enter a question.";
      chatError.classList.remove("hidden");
    }
    return;
  }
  isChatPending = true;
  if (chatAskButton) chatAskButton.disabled = true;
  if (chatError) chatError.classList.add("hidden");
  try {
    const response = await api(`/documents/${currentDetailId}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    if (chatAnswer) chatAnswer.textContent = response.answer || "No answer received.";
    if (chatAnswerContainer) chatAnswerContainer.classList.remove("hidden");
  } catch (error) {
    let friendlyMessage = "Unable to get an answer. Please try again.";
    if (error.status === 502) {
      friendlyMessage = "The AI service is temporarily unavailable. Please try again later.";
    } else if (error.status === 503) {
      friendlyMessage = "The AI service is not configured. Please contact the administrator.";
    } else if (error.status === 400) {
      friendlyMessage = error.message || friendlyMessage;
    } else if (error.message === "Request failed" || error.message === "Failed to fetch") {
      friendlyMessage = "Network error. Please check your connection and try again.";
    }
    if (chatError) {
      chatError.textContent = friendlyMessage;
      chatError.classList.remove("hidden");
    }
  } finally {
    isChatPending = false;
    if (chatAskButton) chatAskButton.disabled = false;
  }
}

async function deleteDetailDocument() {
  if (isDeletingDetail || !currentDetailId) return;
  if (!confirm(`Delete ${currentDetailFilename}? This action cannot be undone.`)) return;
  isDeletingDetail = true;
  setDetailState(true);
  const prevDeleteText = detailDeleteButton ? detailDeleteButton.textContent : null;
  if (detailDeleteButton) {
    detailDeleteButton.disabled = true;
    detailDeleteButton.textContent = 'Deleting…';
  }
  try {
    await api(`/documents/${currentDetailId}`, { method: "DELETE" });
    // Remove from in-memory lists (current list and any cached previous view)
    currentDocuments = currentDocuments.filter((d) => d.id !== currentDetailId);
    if (previousView && previousView.documents) {
      previousView.documents = previousView.documents.filter((d) => d.id !== currentDetailId);
    }
    // Return to normal document list and show success message
    previousView = null;
    renderDocuments(currentDocuments);
    hideDocumentDetailView();
    showNotice(`${currentDetailFilename} deleted successfully.`);
  } catch (error) {
    if (error.status === 401) {
      handleAuthExpiry();
      return;
    }
    if (error.status === 404) {
      setDetailState(false, "Document not found.");
    } else {
      setDetailState(false, error.message || "Unable to delete document. Please try again.");
    }
    if (detailDeleteButton) {
      detailDeleteButton.disabled = false;
      if (prevDeleteText !== null) detailDeleteButton.textContent = prevDeleteText;
    }
  } finally {
    isDeletingDetail = false;
  }
}

async function openDocument(documentId) {
  // Save current view so Back can restore it without another API request
  previousView = {
    isSearchActive,
    searchQuery: searchInput.value,
    documents: currentDocuments.slice(),
  };
  showDocumentDetailView();
  setDetailState(true);
  try {
    const authToken = localStorage.getItem("docpilot_token");
    if (!authToken) {
      logout();
      return;
    }
    const response = await fetch(`${API_URL}/documents/${documentId}`, {
      headers: {
        Authorization: `Bearer ${authToken}`,
        "Content-Type": "application/json",
      },
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
      handleAuthExpiry();
      return;
    }
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error("Document not found.");
      }
      throw new Error(data.detail || "Unable to load document. Please try again.");
    }
    renderDocumentDetail(data);
  } catch (error) {
    const friendly = error.message === "Request failed" || error.message === "Failed to fetch"
      ? "Unable to reach the server. Please try again."
      : error.message;
    setDetailState(false, friendly || "Unable to load document. Please try again.");
  }
}

function handleDetailBack() {
  // If we have a previous view saved, restore it (preserve search query and results)
  if (previousView) {
    isSearchActive = previousView.isSearchActive;
    searchInput.value = previousView.searchQuery || "";
    // Restore documents into the list without making an API call
    renderDocuments(previousView.documents || []);
    previousView = null;
    documentDetailView.classList.add("hidden");
    documentList.classList.remove("hidden");
    return;
  }
  // Fallback to default hide behavior (returns to normal list)
  hideDocumentDetailView();
}

function renderDocuments(documents) {
  currentDocuments = documents;
  documentList.innerHTML = "";
  emptyState.classList.toggle("hidden", documents.length > 0);
  $("#document-count").textContent = `${documents.length} document${documents.length === 1 ? "" : "s"}`;
  if (documents.length === 0) {
    if (isSearchActive) {
      emptyState.querySelector("h2").textContent = "No matching documents found";
      emptyState.querySelector("p").textContent = "Try a different term or clear the search.";
    } else {
      emptyState.querySelector("h2").textContent = "No documents yet";
      emptyState.querySelector("p").textContent = "Upload a DOCX or PDF to extract and store its text.";
    }
  }
  for (const document of documents) {
    const card = window.document.createElement("article");
    card.className = "document-card";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.setAttribute("aria-label", `Open document ${document.filename}`);
    card.innerHTML = `<h3></h3><div class="meta"></div><p class="preview"></p><button type="button" class="delete-button">Delete</button>`;
    card.querySelector("h3").textContent = document.filename;
    card.querySelector(".meta").textContent = `${document.file_type.toUpperCase()} • ${document.word_count} words • ${formatDate(document.created_at)}`;
    card.querySelector(".preview").textContent = document.preview || "No extractable text found.";
    const deleteButton = card.querySelector(".delete-button");
    deleteButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (!confirm(`Delete ${document.filename}?`)) return;
      try {
        await api(`/documents/${document.id}`, { method: "DELETE" });
        await loadDocuments();
      } catch (error) {
        if (error.status === 401) {
          handleAuthExpiry();
          return;
        }
        const friendly = error.message === "Request failed" || error.message === "Failed to fetch"
          ? "Unable to reach the server. Please try again."
          : error.message;
        showNotice(friendly);
      }
    });
    card.addEventListener("click", () => openDocument(document.id));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDocument(document.id);
      }
    });
    documentList.appendChild(card);
  }
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
  previousView = null;
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
}

async function loadDocuments() {
  isSearchActive = false;
  setSearchError();
  setListLoading(true);
  try {
    const documents = await api("/documents");
    renderDocuments(documents);
  } catch (error) {
    if (error.status === 401) {
      handleAuthExpiry();
      return;
    }
    const friendly = error.message === "Request failed" || error.message === "Failed to fetch"
      ? "Unable to reach the server. Please try again."
      : error.message;
    showNotice(friendly);
    renderDocuments([]);
  } finally {
    setListLoading(false);
  }
}

async function searchDocuments() {
  const query = searchInput.value.trim();
  if (!query) {
    setSearchError("Please enter a search term.");
    return;
  }
  setSearchError("");
  isSearchActive = true;
  setListLoading(true);
  documentList.innerHTML = '<p class="preview">Searching…</p>';
  emptyState.classList.add("hidden");
  $("#document-count").textContent = "Searching…";
  try {
    const documents = await api(`/documents/search?q=${encodeURIComponent(query)}`);
    renderDocuments(documents);
  } catch (error) {
    if (error.status === 401) {
      handleAuthExpiry();
      return;
    }
    if (error.status === 400) {
      setSearchError("Please enter a search term.");
      await loadDocuments();
      return;
    }
    const friendlyMessage = error.message === "Request failed" || error.message === "Failed to fetch"
      ? "Unable to reach the server. Please try again."
      : error.message;
    setSearchError(friendlyMessage);
    renderDocuments([]);
  }
    setListLoading(false);
}

function formatDate(value) {
  return new Date(value).toLocaleDateString();
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
  // Avoid message conflicts
  setSearchError("");
  setDetailState(false, "");
  notice.textContent = message;
  notice.classList.remove("hidden");
}

function handleAuthExpiry() {
  showNotice("Session expired. Please log in again.");
  logout();
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

// Password visibility toggle (keyboard-accessible, type=button to avoid form submit)
if (passwordToggle && passwordInput) {
  passwordToggle.addEventListener('click', () => {
    const isPassword = passwordInput.type === 'password';
    passwordInput.type = isPassword ? 'text' : 'password';
    passwordToggle.textContent = isPassword ? 'Hide' : 'Show';
    passwordToggle.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
    passwordInput.focus();
  });
  // allow Enter/Space to toggle when button focused (button handles this by default, but ensure clarity)
  passwordToggle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      passwordToggle.click();
    }
  });
}

const fileInput = $("#file-input");
const dropZone = $("#drop-zone");
detailBackButton.addEventListener("click", handleDetailBack);
if (detailDeleteButton) detailDeleteButton.addEventListener("click", deleteDetailDocument);
if (chatAskButton) chatAskButton.addEventListener("click", askAIQuestion);
if (chatQuestion) chatQuestion.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    askAIQuestion();
  }
});
$("#upload-button").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => { if (fileInput.files[0]) upload(fileInput.files[0]); fileInput.value = ""; });
["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", (event) => { if (event.dataTransfer.files[0]) upload(event.dataTransfer.files[0]); });
dropZone.addEventListener("click", () => fileInput.click());
$("#search-button").addEventListener("click", searchDocuments);
$("#clear-search-button").addEventListener("click", async () => {
  searchInput.value = "";
  setSearchError("");
  await loadDocuments();
});
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    searchDocuments();
  }
});

if (token) showApp();
