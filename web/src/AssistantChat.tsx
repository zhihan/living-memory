import { useState, useRef, useCallback, useEffect } from "react";
import { auth } from "./firebase";

const BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL ?? "";

interface ActionProposal {
  action_id: string;
  action_type: string;
  preview_summary: string;
  payload: Record<string, unknown>;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  proposal?: ActionProposal;
}

async function getToken(): Promise<string> {
  if (!auth.currentUser) throw new Error("Not signed in");
  return auth.currentUser.getIdToken();
}

async function confirmAction(actionId: string): Promise<{ status: string; result: unknown }> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}/v2/assistant/actions/${actionId}/confirm`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(body.detail || resp.statusText);
  }
  return resp.json();
}

async function cancelAction(actionId: string): Promise<void> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}/v2/assistant/actions/${actionId}/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(body.detail || resp.statusText);
  }
}

interface Props {
  workspaceId: string;
  context?: Record<string, unknown>;
}

export function AssistantChat({ workspaceId, context }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }, 30);
  }, []);

  const appendMessage = useCallback((msg: Omit<ChatMessage, "id">) => {
    setMessages((prev) => [...prev, { ...msg, id: crypto.randomUUID() }]);
    scrollToBottom();
  }, [scrollToBottom]);

  const updateLastAssistantMessage = useCallback(
    (updater: (prev: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        const idx = [...prev].reverse().findIndex((m) => m.role === "assistant");
        if (idx === -1) return prev;
        const realIdx = prev.length - 1 - idx;
        const updated = [...prev];
        updated[realIdx] = updater(updated[realIdx]);
        return updated;
      });
      scrollToBottom();
    },
    [scrollToBottom]
  );

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setInput("");
    setError(null);
    setLoading(true);

    // Build history from existing messages (exclude empty assistant placeholders)
    const history = messages
      .filter((m) => m.text)
      .map((m) => ({ role: m.role, text: m.text }));

    appendMessage({ role: "user", text: trimmed });
    appendMessage({ role: "assistant", text: "" });

    try {
      const token = await getToken();
      const resp = await fetch(`${BASE_URL}/v2/workspaces/${workspaceId}/assistant`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: trimmed,
          workspace_context: context,
          history,
        }),
      });

      if (!resp.ok || !resp.body) {
        const body = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(body.detail || resp.statusText);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine || trimmedLine === "data: [DONE]") continue;
          if (!trimmedLine.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(trimmedLine.slice(6));
            if (event.type === "text_chunk") {
              updateLastAssistantMessage((prev) => ({
                ...prev,
                text: prev.text + (event.text as string),
              }));
            } else if (event.type === "action_proposal") {
              updateLastAssistantMessage((prev) => ({
                ...prev,
                proposal: {
                  action_id: event.action_id as string,
                  action_type: event.action_type as string,
                  preview_summary: event.preview_summary as string,
                  payload: event.payload as Record<string, unknown>,
                },
              }));
            }
          } catch (err) {
            console.warn("Failed to parse SSE chunk:", trimmedLine, err);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant" && !last.text) return prev.slice(0, -1);
        return prev;
      });
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  async function handleConfirm(actionId: string) {
    try {
      const result = await confirmAction(actionId);
      setMessages((prev) =>
        prev.map((m) =>
          m.proposal?.action_id === actionId ? { ...m, proposal: undefined } : m
        )
      );
      appendMessage({
        role: "assistant",
        text: `Done. ${JSON.stringify(result.result, null, 2)}`,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm action");
    }
  }

  async function handleCancel(actionId: string) {
    try {
      await cancelAction(actionId);
      setMessages((prev) =>
        prev.map((m) =>
          m.proposal?.action_id === actionId ? { ...m, proposal: undefined } : m
        )
      );
      appendMessage({ role: "assistant", text: "Cancelled." });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel action");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="chat">
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="chat-empty">Ask anything about this schedule.</p>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg chat-msg-${msg.role}`}>
            {msg.text && <span className="chat-msg-text">{msg.text}</span>}
            {msg.proposal && (
              <span className="chat-proposal">
                <span className="chat-proposal-text">{msg.proposal.preview_summary}</span>
                <button
                  className="btn btn-primary btn-xs"
                  onClick={() => handleConfirm(msg.proposal!.action_id)}
                >
                  Confirm
                </button>
                <button
                  className="btn btn-secondary btn-xs"
                  onClick={() => handleCancel(msg.proposal!.action_id)}
                >
                  Cancel
                </button>
              </span>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-msg chat-msg-assistant">
            <span className="chat-dots"><span /><span /><span /></span>
          </div>
        )}
      </div>
      {error && <p className="chat-error">{error}</p>}
      <div className="chat-input-row">
        <input
          ref={inputRef}
          className="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message…"
          disabled={loading}
        />
        <button
          className="btn btn-primary btn-xs chat-send"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
