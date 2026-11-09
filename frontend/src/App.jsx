
import { useEffect, useRef, useState } from "react";
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import {
  Sparkles,
  Plus,
  MessageSquare,
  Search,
  Paperclip,
  ArrowUp,
  PanelLeftClose,
  PanelLeftOpen,
  Trash2,
  Pencil,
  Copy,
  Check,
  RefreshCw,
  Square,
  X,
  RotateCcw,
  FileText,
  FileSpreadsheet,
  Image as ImageIcon,
  Settings,
  Brain,
  Save,
  PlusCircle,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";

import "highlight.js/styles/github-dark.css";
import "./App.css";

const API = "http://127.0.0.1:8000";

function CodeBlock({ children, ...props }) {
  const [copied, setCopied] = useState(false);

  const codeText = React.Children.toArray(children)
    .map((child) =>
      typeof child === "string" ? child : child.props?.children || ""
    )
    .join("");

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(codeText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (error) {
      console.error("Could not copy code:", error);
    }
  };

  return (
    <div className="markdown-code-block">
      <div className="code-toolbar">
        <span>CODE</span>
        <button type="button" onClick={copyCode}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre {...props}>{children}</pre>
    </div>
  );
}

function MarkdownMessage({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        pre: CodeBlock,
        a: ({ children, href, ...props }) => (
          <a href={href} target="_blank" rel="noreferrer" {...props}>
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function TypingIndicator({ label = "Zyricon is thinking" }) {
  return (
    <div className="typing-indicator" role="status" aria-label={label}>
      <span className="typing-dots"><i /><i /><i /></span>
      <small className="typing-label">{label}</small>
    </div>
  );
}

function App() {
  const [introVisible, setIntroVisible] = useState(true);
  const [introVariant, setIntroVariant] = useState("first");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [conversationAction, setConversationAction] = useState(null);
  const [conversationActionTitle, setConversationActionTitle] = useState("");
  const [conversationActionError, setConversationActionError] = useState("");
  const [conversationActionLoading, setConversationActionLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingStarted, setStreamingStarted] = useState(false);
  const [requestStatus, setRequestStatus] = useState("Zyricon is thinking");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editText, setEditText] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false);
  const [memories, setMemories] = useState([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memorySaving, setMemorySaving] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [automaticMemory, setAutomaticMemory] = useState(true);
  const [newMemory, setNewMemory] = useState("");
  const [newMemoryCategory, setNewMemoryCategory] = useState("general");
  const [editingMemoryId, setEditingMemoryId] = useState(null);
  const [editingMemoryText, setEditingMemoryText] = useState("");
  const fileInputRef = useRef(null);

  const chatScrollRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);
  const scrollFrameRef = useRef(null);
  const inputRef = useRef(null);
  const activeRequestRef = useRef(null);
  const activeRequestIdRef = useRef(null);
  const activeConversationRef = useRef(null);

  useEffect(() => {
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reducedMotion) {
      setIntroVisible(false);
      return;
    }

    let hasVisited = false;
    try {
      hasVisited = window.localStorage.getItem("zyricon-intro-seen") === "1";
      window.localStorage.setItem("zyricon-intro-seen", "1");
    } catch {
      // If storage is unavailable, show the full intro for this visit.
    }

    setIntroVariant(hasVisited ? "returning" : "first");
    setIntroVisible(true);

    // Keep the React overlay mounted for the complete CSS intro sequence.
    const duration = hasVisited ? 1700 : 3200;
    const timeout = window.setTimeout(() => setIntroVisible(false), duration);
    return () => window.clearTimeout(timeout);
  }, []);

  useEffect(() => {
    loadConversations();
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    activeConversationRef.current = activeConversationId;
    shouldAutoScrollRef.current = true;
  }, [activeConversationId]);

  useEffect(() => {
    if (!loading && !editingMessageId) inputRef.current?.focus();
  }, [loading, editingMessageId]);

  // Keep the composer compact for short messages and expand it for longer ones.
  useEffect(() => {
    const composerInput = inputRef.current;
    if (!composerInput) return;

    composerInput.style.height = "auto";
    const nextHeight = Math.min(composerInput.scrollHeight, 160);
    composerInput.style.height = `${nextHeight}px`;
    composerInput.style.overflowY = composerInput.scrollHeight > 160 ? "auto" : "hidden";
  }, [input]);

  // Follow every rendered stream update without repeatedly restarting smooth-scroll.
  // Manual upward scrolling pauses follow mode until the user returns near the bottom
  // or starts a new request.
  useEffect(() => {
    const container = chatScrollRef.current;
    if (!container || !shouldAutoScrollRef.current) return;

    if (scrollFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
    }

    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      if (!shouldAutoScrollRef.current || !chatScrollRef.current) return;

      const currentContainer = chatScrollRef.current;
      currentContainer.scrollTop = currentContainer.scrollHeight;
    });

    return () => {
      if (scrollFrameRef.current !== null) {
        window.cancelAnimationFrame(scrollFrameRef.current);
        scrollFrameRef.current = null;
      }
    };
  }, [messages, loading]);

  const handleChatScroll = () => {
    const container = chatScrollRef.current;
    if (!container) return;

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= 120;
  };

  const loadConversations = async () => {
    try {
      const response = await fetch(`${API}/conversations`);
      if (!response.ok) throw new Error("Could not load conversations");
      setConversations(await response.json());
    } catch (error) {
      console.error("History error:", error);
    } finally {
      setLoadingHistory(false);
    }
  };

  const loadConversationMessages = async (conversationId) => {
    const response = await fetch(`${API}/conversations/${conversationId}`);
    if (!response.ok) throw new Error("Could not refresh conversation");
    const data = await response.json();
    if (activeConversationRef.current === conversationId) {
      setMessages((data.messages || []).map((message) => ({ ...message, attachments: message.attachments || [] })));
    }
  };

  const createNewChat = async () => {
    if (loading) return;
    try {
      const response = await fetch(`${API}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New chat" }),
      });
      if (!response.ok) throw new Error("Could not create conversation");
      const conversation = await response.json();
      setConversations((previous) => [conversation, ...previous]);
      setActiveConversationId(conversation.id);
      activeConversationRef.current = conversation.id;
      setMessages([]);
      setInput("");
      setEditingMessageId(null);
      inputRef.current?.focus();
    } catch (error) {
      console.error("New chat error:", error);
      alert("Could not create a new chat. Check your backend.");
    }
  };

  const openConversation = async (conversationId) => {
    if (loading) return;
    setMobileSidebarOpen(false);
    try {
      const response = await fetch(`${API}/conversations/${conversationId}`);
      if (!response.ok) throw new Error("Could not open conversation");
      const data = await response.json();
      setActiveConversationId(conversationId);
      activeConversationRef.current = conversationId;
      setMessages((data.messages || []).map((message) => ({ ...message, attachments: message.attachments || [] })));
      setInput("");
      setEditingMessageId(null);
      inputRef.current?.focus();
    } catch (error) {
      console.error("Open chat error:", error);
      alert("Could not open this conversation.");
    }
  };

  const openConversationAction = (type, conversation) => {
    setConversationAction({ type, conversation });
    setConversationActionTitle(conversation.title || "");
    setConversationActionError("");
  };

  const closeConversationAction = () => {
    if (conversationActionLoading) return;
    setConversationAction(null);
    setConversationActionTitle("");
    setConversationActionError("");
  };

  const submitConversationAction = async (event) => {
    event?.preventDefault();
    if (!conversationAction || conversationActionLoading) return;

    const { type, conversation } = conversationAction;
    setConversationActionError("");
    setConversationActionLoading(true);

    try {
      if (type === "rename") {
        const title = conversationActionTitle.trim();
        if (!title) {
          setConversationActionError("Enter a conversation name to continue.");
          setConversationActionLoading(false);
          return;
        }

        const response = await fetch(`${API}/conversations/${conversation.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title }),
        });
        if (!response.ok) throw new Error("Rename failed");
        await loadConversations();
      } else {
        const response = await fetch(`${API}/conversations/${conversation.id}`, {
          method: "DELETE",
        });
        if (!response.ok) throw new Error("Delete failed");

        setConversations((previous) =>
          previous.filter((item) => item.id !== conversation.id)
        );

        if (activeConversationRef.current === conversation.id) {
          setActiveConversationId(null);
          activeConversationRef.current = null;
          setMessages([]);
          setInput("");
          setEditingMessageId(null);
        }
      }

      setConversationAction(null);
      setConversationActionTitle("");
    } catch (error) {
      console.error(`${type === "rename" ? "Rename" : "Delete"} conversation error:`, error);
      setConversationActionError(
        type === "rename"
          ? "Could not rename this conversation. Please try again."
          : "Could not delete this conversation. Please try again."
      );
    } finally {
      setConversationActionLoading(false);
    }
  };

  const copyMessage = async (message) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => setCopiedMessageId(null), 1800);
    } catch (error) {
      console.error("Could not copy message:", error);
    }
  };

  const startRequest = (status = "Zyricon is thinking") => {
    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    activeRequestRef.current = controller;
    activeRequestIdRef.current = requestId;
    setStreamingStarted(false);
    setRequestStatus(status);
    setLoading(true);
    shouldAutoScrollRef.current = true;
    return { requestId, controller };
  };

  const finishRequest = () => {
    activeRequestRef.current = null;
    activeRequestIdRef.current = null;
    setLoading(false);
    setStreamingStarted(false);
    setRequestStatus("Zyricon is thinking");
    inputRef.current?.focus();
  };

  const consumeAssistantStream = async (response, requestId, conversationId) => {
    if (!response.ok) {
      let detail = "The streaming request failed.";
      try {
        const errorData = await response.json();
        detail = errorData.detail || detail;
      } catch {
        // Keep the fallback message when the server does not return JSON.
      }
      throw new Error(detail);
    }

    if (!response.body) {
      throw new Error("Streaming is not supported by this browser response.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const streamMessageId = `stream-${requestId}`;
    let buffer = "";
    let completion = null;

    const handleEvent = (block) => {
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");

      if (!data) return;

      const payload = JSON.parse(data);

      if (payload.type === "token") {
        if (activeConversationRef.current === conversationId) {
          setStreamingStarted(true);
        }
        setMessages((previous) => {
          if (activeConversationRef.current !== conversationId) return previous;
          const existing = previous.some((item) => item.id === streamMessageId);
          if (existing) {
            return previous.map((item) =>
              item.id === streamMessageId
                ? { ...item, content: item.content + payload.text, streaming: true }
                : item
            );
          }

          return [
            ...previous,
            {
              id: streamMessageId,
              role: "assistant",
              content: payload.text,
              attachments: [],
              streaming: true,
            },
          ];
        });
      } else if (payload.type === "done") {
        completion = payload;
        setMessages((previous) => {
          if (activeConversationRef.current !== conversationId) return previous;
          return previous.map((item) =>
            item.id === streamMessageId ? { ...item, streaming: false } : item
          );
        });
      } else if (payload.type === "error") {
        throw new Error(payload.message || "AI response failed.");
      }
    };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        let boundary;

        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const block = buffer.slice(0, boundary).trim();
          buffer = buffer.slice(boundary + 2);
          if (block) handleEvent(block);
        }
      }

      buffer += decoder.decode();
      if (buffer.trim()) handleEvent(buffer.trim());

      if (!completion) {
        throw new Error("The stream ended before Zyricon completed its response.");
      }

      return completion;
    } catch (error) {
      setMessages((previous) => {
        if (activeConversationRef.current !== conversationId) return previous;
        return previous.map((item) =>
          item.id === streamMessageId ? { ...item, streaming: false } : item
        );
      });
      throw error;
    } finally {
      reader.releaseLock();
    }
  };

  const ensureConversation = async () => {
    let conversationId = activeConversationRef.current;
    if (conversationId) return conversationId;

    const response = await fetch(`${API}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New chat" }),
    });
    if (!response.ok) throw new Error("Could not create conversation");

    const conversation = await response.json();
    conversationId = conversation.id;
    setActiveConversationId(conversationId);
    activeConversationRef.current = conversationId;
    setConversations((previous) => [conversation, ...previous]);
    return conversationId;
  };

  const MAX_FILES = 5;
  const MAX_FILE_SIZE = 10 * 1024 * 1024;
  const ACCEPTED_FILES = ".pdf,.docx,.txt,.csv,.xlsx,.png,.jpg,.jpeg,.webp";

  const addAttachments = (fileList) => {
    const incoming = Array.from(fileList || []);
    const next = [];
    for (const file of incoming) {
      const extension = file.name.split(".").pop()?.toLowerCase();
      const allowed = ["pdf", "docx", "txt", "csv", "xlsx", "png", "jpg", "jpeg", "webp"];
      if (!allowed.includes(extension)) {
        alert(`${file.name}: this file type is not supported.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        alert(`${file.name}: maximum file size is 10 MB.`);
        continue;
      }
      next.push({ file, id: `${file.name}-${file.size}-${file.lastModified}`, preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null });
    }
    setAttachments((current) => {
      const combined = [...current, ...next];
      if (combined.length > MAX_FILES) {
        combined.slice(MAX_FILES).forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
        alert("You can attach up to 5 files per message.");
      }
      return combined.slice(0, MAX_FILES);
    });
  };

  const removeAttachment = (id) => {
    setAttachments((current) => {
      const item = current.find((file) => file.id === id);
      if (item?.preview) URL.revokeObjectURL(item.preview);
      return current.filter((file) => file.id !== id);
    });
  };

  const attachmentIcon = (name) => {
    const ext = name.split(".").pop()?.toLowerCase();
    if (["csv", "xlsx"].includes(ext)) return <FileSpreadsheet size={17} />;
    if (["png", "jpg", "jpeg", "webp"].includes(ext)) return <ImageIcon size={17} />;
    return <FileText size={17} />;
  };

  const sendMessage = async (text = input, retryPayload = null) => {
    const trimmedInput = text.trim();
    const filesToSend = retryPayload?.files || [...attachments];
    if ((!trimmedInput && filesToSend.length === 0) || loading) return;

    setAttachments([]);
    setInput("");
    const tempId = retryPayload?.tempId || `temp-${Date.now()}`;

    if (retryPayload?.tempId) {
      setMessages((previous) => previous
        .filter((item) => item.id !== retryPayload.errorId)
        .map((item) => item.id === tempId ? { ...item, pending: true } : item));
    } else {
      setMessages((previous) => [
        ...previous,
        {
          id: tempId,
          role: "user",
          content: trimmedInput,
          attachments: filesToSend.map((item) => ({
            name: item.file.name,
            size: item.file.size,
            type: item.file.type,
          })),
          pending: true,
        },
      ]);
    }

    const { requestId, controller } = startRequest();
    let conversationId;

    try {
      conversationId = await ensureConversation();
      let response;

      if (filesToSend.length > 0) {
        const formData = new FormData();
        formData.append("message", trimmedInput);
        formData.append("request_id", requestId);
        filesToSend.forEach((item) => formData.append("files", item.file));

        response = await fetch(
          `${API}/conversations/${conversationId}/messages/with-attachments/stream`,
          {
            method: "POST",
            signal: controller.signal,
            body: formData,
          }
        );
      } else {
        response = await fetch(
          `${API}/conversations/${conversationId}/messages/stream`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            body: JSON.stringify({
              message: trimmedInput,
              request_id: requestId,
            }),
          }
        );
      }

      const completion = await consumeAssistantStream(response, requestId, conversationId);
      filesToSend.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));

      if (completion.cancelled) {
        await loadConversationMessages(conversationId);
        await loadConversations();
        return;
      }

      await loadConversationMessages(conversationId);
      await loadConversations();
    } catch (error) {
      filesToSend.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
      if (error.name !== "AbortError") {
        console.error("Chat error:", error);
        const errorId = `error-${Date.now()}`;
        setMessages((previous) => [
          ...previous.map((message) =>
            message.id === tempId ? { ...message, pending: false } : message
          ),
          {
            id: errorId,
            role: "assistant",
            content: `I couldn't complete that request: ${error.message}`,
            attachments: [],
            isError: true,
            retryPayload: { text: trimmedInput, files: filesToSend, tempId },
          },
        ]);
      }
    } finally {
      finishRequest();
    }
  };

  const stopGeneration = async () => {
    const requestId = activeRequestIdRef.current;
    const conversationId = activeConversationRef.current;
    if (!requestId || !conversationId) return;

    try {
      await fetch(`${API}/conversations/${conversationId}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId }),
      });
      // Keep the stream connection open briefly so the server can send its
      // cancelled completion event and persist any partial response.
    } catch (error) {
      console.error("Stop request error:", error);
    }
  };

  const beginEdit = (message) => {
    if (loading || message.role !== "user" || typeof message.id !== "number") return;
    setEditingMessageId(message.id);
    setEditText(message.content);
  };

  const cancelEdit = () => {
    setEditingMessageId(null);
    setEditText("");
  };

  const saveEdit = async (message) => {
    const content = editText.trim();
    const conversationId = activeConversationRef.current;
    if (!content || !conversationId || loading) return;

    try {
      const response = await fetch(
        `${API}/conversations/${conversationId}/messages/${message.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not edit message");

      setMessages((previous) => {
        const index = previous.findIndex((item) => item.id === message.id);
        return previous
          .slice(0, index + 1)
          .map((item) =>
            item.id === message.id ? { ...item, content: data.content } : item
          );
      });
      setEditingMessageId(null);
      setEditText("");

      const { requestId, controller } = startRequest();
      try {
        const replyResponse = await fetch(
          `${API}/conversations/${conversationId}/messages/${message.id}/reply/stream`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            body: JSON.stringify({ request_id: requestId }),
          }
        );
        const completion = await consumeAssistantStream(replyResponse, requestId, conversationId);
        if (!completion.cancelled) {
          await loadConversationMessages(conversationId);
          await loadConversations();
        }
      } finally {
        finishRequest();
      }
    } catch (error) {
      console.error("Edit error:", error);
      alert(error.message || "Could not edit this message.");
    }
  };

  const regenerateMessage = async (message) => {
    const conversationId = activeConversationRef.current;
    if (!conversationId || loading || message.role !== "assistant") return;

    setMessages((previous) => previous.filter((item) => item.id !== message.id));
    const { requestId, controller } = startRequest("Regenerating response");

    try {
      const response = await fetch(
        `${API}/conversations/${conversationId}/messages/${message.id}/regenerate/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({ request_id: requestId }),
        }
      );
      const completion = await consumeAssistantStream(response, requestId, conversationId);
      if (!completion.cancelled) {
        await loadConversationMessages(conversationId);
        await loadConversations();
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        console.error("Regenerate error:", error);
        await loadConversationMessages(conversationId);
        setMessages((previous) => [
          ...previous,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: `I couldn't regenerate that response: ${error.message}`,
            attachments: [],
            isError: true,
            retryPayload: { type: "regenerate", messageId: message.id },
          },
        ]);
      }
    } finally {
      finishRequest();
    }
  };

  const retryFailedMessage = (errorMessage) => {
    const payload = errorMessage.retryPayload;
    if (!payload || loading) return;

    if (payload.type === "regenerate") {
      const originalMessage = messages.find((item) => item.id === payload.messageId);
      setMessages((previous) => previous.filter((item) => item.id !== errorMessage.id));
      if (originalMessage) regenerateMessage(originalMessage);
      return;
    }

    sendMessage(payload.text, { ...payload, errorId: errorMessage.id });
  };

  const loadMemories = async () => {
    setMemoryLoading(true);
    setMemoryError("");
    try {
      const [memoryResponse, settingsResponse] = await Promise.all([
        fetch(`${API}/memory`),
        fetch(`${API}/memory/settings`),
      ]);
      if (!memoryResponse.ok || !settingsResponse.ok) {
        throw new Error("Could not load memory settings. Check that the updated backend is running.");
      }
      const memoryData = await memoryResponse.json();
      const settingsData = await settingsResponse.json();
      setMemories(memoryData.memories || []);
      setAutomaticMemory(Boolean(settingsData.automatic_memory));
    } catch (error) {
      setMemoryError(error.message);
    } finally {
      setMemoryLoading(false);
    }
  };

  const openMemoryManager = async () => {
    setMemoryManagerOpen(true);
    await loadMemories();
  };

  const saveNewMemory = async () => {
    const value = newMemory.trim();
    if (value.length < 2 || memorySaving) return;
    setMemorySaving(true);
    setMemoryError("");
    try {
      const response = await fetch(`${API}/memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory: value, category: newMemoryCategory }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not save memory.");
      setNewMemory("");
      await loadMemories();
    } catch (error) {
      setMemoryError(error.message);
    } finally {
      setMemorySaving(false);
    }
  };

  const saveEditedMemory = async (memory) => {
    const value = editingMemoryText.trim();
    if (value.length < 2 || memorySaving) return;
    setMemorySaving(true);
    setMemoryError("");
    try {
      const response = await fetch(`${API}/memory/${memory.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory: value, category: memory.category || "general" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not save the edited memory.");
      setEditingMemoryId(null);
      setEditingMemoryText("");
      await loadMemories();
    } catch (error) {
      setMemoryError(error.message);
      await loadMemories();
    } finally {
      setMemorySaving(false);
    }
  };

  const deleteMemory = async (memory) => {
    if (!window.confirm("Delete this saved memory?")) return;
    setMemoryError("");
    try {
      const response = await fetch(`${API}/memory/${memory.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Could not delete this memory.");
      setMemories((items) => items.filter((item) => item.id !== memory.id));
    } catch (error) {
      setMemoryError(error.message);
    }
  };

  const clearAllMemories = async () => {
    if (!memories.length || !window.confirm("Clear every saved memory? This cannot be undone.")) return;
    setMemoryError("");
    try {
      const response = await fetch(`${API}/memory`, { method: "DELETE" });
      if (!response.ok) throw new Error("Could not clear saved memories.");
      setMemories([]);
    } catch (error) {
      setMemoryError(error.message);
    }
  };

  const toggleAutomaticMemory = async () => {
    const nextValue = !automaticMemory;
    setMemoryError("");
    try {
      const response = await fetch(`${API}/memory/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ automatic_memory: nextValue }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not update this setting.");
      setAutomaticMemory(Boolean(data.automatic_memory));
    } catch (error) {
      setMemoryError(error.message);
    }
  };

  const handleSuggestion = (text) => {
    setInput(text);
    inputRef.current?.focus();
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const activeConversation = conversations.find(
    (item) => item.id === activeConversationId
  );
  const filteredConversations = conversations.filter((item) =>
    item.title.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className={`app ${introVisible ? "app--intro-active" : "app--intro-enter"} ${sidebarCollapsed ? "app--sidebar-collapsed" : ""}`}>
      {introVisible && (
        <div
          className={`intro-screen intro-screen--${introVariant}`}
          aria-label="Zyricon"
          role="status"
        >
          <div className="intro-lockup">
            <div className="intro-symbol"><Sparkles size={27} strokeWidth={1.6} /></div>
            <div className="intro-wordmark">zyricon<span>.</span></div>
            <div className="intro-caption">YOUR PERSONAL INTELLIGENCE SPACE</div>
          </div>
        </div>
      )}
      <aside className="sidebar">
        <div className="brand">
          <div className="logo"><Sparkles size={18} /></div>
          <span>zyricon<span className="dot">.</span></span>
          <button
            className="collapse"
            type="button"
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        <button className="new-chat" onClick={createNewChat} disabled={loading}>
          <Plus size={17} /> New chat
        </button>

        <div className="search">
          <Search size={16} />
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search conversations"
          />
        </div>

        <div className="section-title recent">RECENT</div>
        <div className="conversation-list">
          {loadingHistory && <div className="nav">Loading chats...</div>}
          {!loadingHistory && filteredConversations.length === 0 && (
            <div className="nav">
              {searchTerm ? "No matching chats" : "No conversations yet"}
            </div>
          )}

          {filteredConversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`conversation-item ${
                activeConversationId === conversation.id ? "selected" : ""
              }`}
            >
              <button
                className="conversation-open"
                onClick={() => openConversation(conversation.id)}
                disabled={loading}
                title={conversation.title}
              >
                <MessageSquare size={15} />
                <span>{conversation.title}</span>
              </button>
              <div className="conversation-actions">
                <button
                  title="Rename conversation"
                  onClick={() => openConversationAction("rename", conversation)}
                  type="button"
                >
                  <Pencil size={13} />
                </button>
                <button
                  title="Delete conversation"
                  onClick={() => openConversationAction("delete", conversation)}
                  type="button"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="sidebar-bottom">
          <button className="memory-manager-trigger" type="button" onClick={openMemoryManager}>
            <Brain size={17} />
            <span>Memory manager</span>
            <Settings size={15} className="memory-settings-icon" />
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <button
            className="mobile-sidebar-trigger"
            type="button"
            onClick={() => setSidebarCollapsed(false)}
            aria-label="Open sidebar"
            title="Open sidebar"
          >
            <PanelLeftOpen size={19} />
          </button>
          <span className="breadcrumb">
            <strong>{activeConversation?.title || "New chat"}</strong>
          </span>
        </header>

        {messages.length === 0 && (
          <section className="welcome">
            <div className="orb"><Sparkles size={28} /></div>
            <div className="eyebrow">YOUR INTELLIGENCE SPACE</div>
            <h1>Where ideas become <span>reality.</span></h1>
            <p>
              Ask questions, explore ideas, solve problems.
              <br />
              Your next big thought starts here.
            </p>
            <div className="suggestions">
              <button onClick={() => handleSuggestion("Help me build a website")}>
                <span>✳</span><strong>Build something</strong>
                <small>Turn an idea into a project</small>
              </button>
              <button onClick={() => handleSuggestion("Teach me machine learning")}>
                <span>⌘</span><strong>Learn something</strong>
                <small>Explore a new topic</small>
              </button>
              <button onClick={() => handleSuggestion("Help me solve a problem")}>
                <span>◈</span><strong>Solve a problem</strong>
                <small>Think through challenges</small>
              </button>
              <button onClick={() => handleSuggestion("Give me creative ideas")}>
                <span>✧</span><strong>Get creative</strong>
                <small>Discover new possibilities</small>
              </button>
            </div>
          </section>
        )}

        {messages.length > 0 && (
          <section className="chat-messages" ref={chatScrollRef} onScroll={handleChatScroll}>
            {messages.map((msg, index) => (
              <article key={msg.id} className={`message ${msg.role}`}>
                {msg.role === "assistant" && (
                  <div className="message-avatar"><Sparkles size={16} /></div>
                )}

                <div className="message-content">
                  {msg.role === "assistant" && <strong>Zyricon</strong>}

                  <div className={`message-body ${msg.streaming ? "message-body--streaming" : ""}`}>
                    {editingMessageId === msg.id ? (
                      <div className="message-edit-box">
                        <textarea
                          value={editText}
                          onChange={(event) => setEditText(event.target.value)}
                          autoFocus
                          rows={Math.max(3, Math.min(8, editText.split("\n").length + 1))}
                        />
                        <div className="edit-actions">
                          <button type="button" onClick={cancelEdit}>
                            <X size={14} /> Cancel
                          </button>
                          <button
                            type="button"
                            className="edit-save"
                            onClick={() => saveEdit(msg)}
                            disabled={!editText.trim()}
                          >
                            <Check size={14} /> Save & submit
                          </button>
                        </div>
                      </div>
                    ) : msg.role === "assistant" && msg.isError ? (
                      <div className="message-error-content">
                        <p>{msg.content}</p>
                        <button
                          type="button"
                          className="retry-message"
                          onClick={() => retryFailedMessage(msg)}
                          disabled={loading}
                        >
                          <RotateCcw size={13} /> Retry
                        </button>
                      </div>
                    ) : msg.role === "assistant" ? (
                      <MarkdownMessage content={msg.content} />
                    ) : (
                      <p>{msg.content}</p>
                    )}
                  </div>

                  {msg.role === "user" && msg.attachments?.length > 0 && (
                    <div className="message-attachments">
                      {msg.attachments.map((file, fileIndex) => (
                        <div className="message-attachment" key={`${file.name}-${fileIndex}`}>
                          {attachmentIcon(file.name)}
                          <span>{file.name}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.role === "assistant" ? (
                    <div className="message-tools">
                      <button
                        type="button"
                        className={copiedMessageId === msg.id ? "is-copied" : ""}
                        onClick={() => copyMessage(msg)}
                        title={copiedMessageId === msg.id ? "Copied to clipboard" : "Copy message"}
                        aria-label={copiedMessageId === msg.id ? "Message copied" : "Copy message"}
                      >
                        {copiedMessageId === msg.id ? <Check size={13} /> : <Copy size={13} />}
                        {copiedMessageId === msg.id ? "Copied" : "Copy"}
                      </button>
                      {!msg.isError && index === messages.length - 1 && (
                        <button
                          type="button"
                          onClick={() => regenerateMessage(msg)}
                          disabled={loading}
                          title="Regenerate response"
                        >
                          <RotateCcw size={13} /> Regenerate
                        </button>
                      )}
                    </div>
                  ) : (
                    !msg.pending && typeof msg.id === "number" && (
                      <div className="message-tools user-message-tools">
                        <button
                          type="button"
                          onClick={() => beginEdit(msg)}
                          disabled={loading}
                          title="Edit message"
                        >
                          <Pencil size={13} /> Edit
                        </button>
                      </div>
                    )
                  )}
                </div>
              </article>
            ))}

            {loading && !streamingStarted && (
              <article className="message assistant">
                <div className="message-avatar"><Sparkles size={16} /></div>
                <div className="message-content">
                  <strong>Zyricon</strong>
                  <TypingIndicator label={requestStatus} />
                </div>
              </article>
            )}
          </section>
        )}

        <div className="composer-area" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!loading) addAttachments(event.dataTransfer.files); }}>
          <div className="composer">
            {attachments.length > 0 && (
              <div className="attachment-preview-list">
                {attachments.map((item) => (
                  <div className="attachment-preview" key={item.id}>
                    {item.preview ? <img src={item.preview} alt="" /> : attachmentIcon(item.file.name)}
                    <span title={item.file.name}>{item.file.name}</span>
                    <button type="button" onClick={() => removeAttachment(item.id)} aria-label={`Remove ${item.file.name}`} disabled={loading}><X size={13} /></button>
                  </div>
                ))}
              </div>
            )}
            <textarea
              ref={inputRef}
              autoFocus
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Zyricon..."
              aria-label="Message Zyricon"
              disabled={loading}
            />
            <input
              ref={fileInputRef}
              className="attachment-file-input"
              type="file"
              accept={ACCEPTED_FILES}
              multiple
              onChange={(event) => { addAttachments(event.target.files); event.target.value = ""; }}
            />
            <div className="composer-bottom">
              <button
                className="attach"
                type="button"
                title="Attach files"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading || attachments.length >= MAX_FILES}
              >
                <Paperclip size={17} /> Attach
              </button>

              {loading ? (
                <button
                  className="send stop-generation"
                  onClick={stopGeneration}
                  type="button"
                  title="Stop generating"
                  aria-label="Stop generating"
                >
                  <Square size={15} />
                </button>
              ) : (
                <button
                  className="send"
                  onClick={() => sendMessage()}
                  disabled={!input.trim() && attachments.length === 0}
                  type="button"
                  title="Send message"
                  aria-label="Send message"
                >
                  <ArrowUp size={19} />
                </button>
              )}
            </div>
          </div>
          <small className="disclaimer">
            Zyricon can make mistakes. Verify important information.
          </small>
        </div>
      </main>

      {conversationAction && (
        <div
          className="conversation-dialog-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeConversationAction();
          }}
        >
          <section
            className={`conversation-dialog ${conversationAction.type === "delete" ? "conversation-dialog--delete" : "conversation-dialog--rename"}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="conversation-dialog-title"
            onKeyDown={(event) => {
              if (event.key === "Escape") closeConversationAction();
            }}
          >
            <header className="conversation-dialog-header">
              <div className={`conversation-dialog-icon ${conversationAction.type === "delete" ? "danger" : "edit"}`}>
                {conversationAction.type === "delete" ? <Trash2 size={19} /> : <Pencil size={19} />}
              </div>
              <button
                className="conversation-dialog-close"
                type="button"
                onClick={closeConversationAction}
                disabled={conversationActionLoading}
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </header>

            <form onSubmit={submitConversationAction}>
              <div className="conversation-dialog-copy">
                <h2 id="conversation-dialog-title">
                  {conversationAction.type === "delete" ? "Delete conversation?" : "Rename conversation"}
                </h2>
                {conversationAction.type === "delete" ? (
                  <>
                    <p>This will permanently delete <strong>“{conversationAction.conversation.title}”</strong> and its messages.</p>
                    <p className="conversation-dialog-note">This action cannot be undone.</p>
                  </>
                ) : (
                  <>
                    <p>Give this conversation a name that is easy to recognize.</p>
                    <label className="conversation-dialog-label" htmlFor="conversation-rename-input">Conversation name</label>
                    <input
                      id="conversation-rename-input"
                      className="conversation-dialog-input"
                      value={conversationActionTitle}
                      onChange={(event) => setConversationActionTitle(event.target.value)}
                      placeholder="Enter a conversation name"
                      maxLength={100}
                      autoFocus
                      disabled={conversationActionLoading}
                    />
                    <small className="conversation-dialog-counter">{conversationActionTitle.length}/100</small>
                  </>
                )}
                {conversationActionError && (
                  <div className="conversation-dialog-error" role="alert">{conversationActionError}</div>
                )}
              </div>

              <footer className="conversation-dialog-actions">
                <button className="conversation-dialog-cancel" type="button" onClick={closeConversationAction} disabled={conversationActionLoading}>
                  Cancel
                </button>
                <button
                  className={`conversation-dialog-confirm ${conversationAction.type === "delete" ? "danger" : "primary"}`}
                  type="submit"
                  disabled={conversationActionLoading || (conversationAction.type === "rename" && !conversationActionTitle.trim())}
                >
                  {conversationActionLoading ? "Please wait…" : conversationAction.type === "delete" ? "Delete conversation" : "Save changes"}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}

      {memoryManagerOpen && (
        <div className="memory-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setMemoryManagerOpen(false); }}>
          <section className="memory-modal" role="dialog" aria-modal="true" aria-labelledby="memory-modal-title">
            <header className="memory-modal-header">
              <div className="memory-modal-heading">
                <div className="memory-modal-icon"><Brain size={19} /></div>
                <div>
                  <h2 id="memory-modal-title">Memory manager</h2>
                  <p>Manage what Zyricon remembers across conversations.</p>
                </div>
              </div>
              <button className="memory-close" type="button" onClick={() => setMemoryManagerOpen(false)} aria-label="Close memory manager"><X size={19} /></button>
            </header>

            {memoryError && <div className="memory-error">{memoryError}</div>}

            <div className="memory-setting-row">
              <div className="memory-setting-copy">
                <strong>Automatic memory</strong>
                <span>{automaticMemory ? "Zyricon can save useful long-term details from chats." : "Automatic extraction is paused. Existing memories are retained."}</span>
              </div>
              <button type="button" className={`memory-toggle ${automaticMemory ? "enabled" : ""}`} onClick={toggleAutomaticMemory} aria-label="Toggle automatic memory">
                {automaticMemory ? <ToggleRight size={31} /> : <ToggleLeft size={31} />}
                <span>{automaticMemory ? "On" : "Off"}</span>
              </button>
            </div>

            <div className="memory-add-section">
              <label htmlFor="new-memory-input">Add a memory</label>
              <textarea id="new-memory-input" value={newMemory} onChange={(event) => setNewMemory(event.target.value)} placeholder="Example: My current goal is to become a Data Scientist." maxLength={500} rows={3} />
              <div className="memory-add-controls">
                <select value={newMemoryCategory} onChange={(event) => setNewMemoryCategory(event.target.value)} aria-label="Memory category">
                  <option value="general">General</option>
                  <option value="goal">Goal</option>
                  <option value="project">Project</option>
                  <option value="work">Work</option>
                  <option value="preference">Preference</option>
                  <option value="skill">Skill</option>
                </select>
                <button type="button" className="memory-primary-button" onClick={saveNewMemory} disabled={newMemory.trim().length < 2 || memorySaving}>
                  <PlusCircle size={15} /> Save memory
                </button>
              </div>
            </div>

            <div className="memory-list-header">
              <div><strong>Saved memories</strong><span>{memories.length} stored</span></div>
              <button type="button" onClick={clearAllMemories} disabled={!memories.length || memorySaving}>Clear all</button>
            </div>

            <div className="memory-list">
              {memoryLoading ? <div className="memory-empty">Loading saved memories...</div> : memories.length === 0 ? (
                <div className="memory-empty"><Brain size={23} /><strong>No saved memories yet</strong><span>Add a memory above or continue chatting with automatic memory enabled.</span></div>
              ) : memories.map((memory) => (
                <article className="memory-item" key={memory.id}>
                  <div className="memory-item-main">
                    <span className="memory-category">{memory.category || "general"}</span>
                    {editingMemoryId === memory.id ? (
                      <textarea className="memory-edit-input" value={editingMemoryText} onChange={(event) => setEditingMemoryText(event.target.value)} maxLength={500} rows={3} />
                    ) : <p>{memory.memory}</p>}
                    <small>Updated {memory.updated_at ? new Date(memory.updated_at).toLocaleString() : "recently"}</small>
                  </div>
                  <div className="memory-item-actions">
                    {editingMemoryId === memory.id ? (
                      <>
                        <button type="button" title="Save changes" onClick={() => saveEditedMemory(memory)} disabled={editingMemoryText.trim().length < 2 || memorySaving}><Save size={15} /></button>
                        <button type="button" title="Cancel editing" onClick={() => { setEditingMemoryId(null); setEditingMemoryText(""); }}><X size={15} /></button>
                      </>
                    ) : (
                      <>
                        <button type="button" title="Edit memory" onClick={() => { setEditingMemoryId(memory.id); setEditingMemoryText(memory.memory); }}><Pencil size={15} /></button>
                        <button type="button" title="Delete memory" onClick={() => deleteMemory(memory)}><Trash2 size={15} /></button>
                      </>
                    )}
                  </div>
                </article>
              ))}
            </div>
            <footer className="memory-modal-footer">Saved memories are shared across your conversations on this device.</footer>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;