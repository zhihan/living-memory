import { useState, useRef, useCallback } from "react";
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
}

export function AssistantChat({ workspaceId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const appendMessage = useCallback((msg: Omit<ChatMessage, "id">) => {
    setMessages((prev) => [...prev, { ...msg, id: crypto.randomUUID() }]);
    setTimeout(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }, 50);
  }, []);

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
    },
    []
  );

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setInput("");
    setError(null);
    setLoading(true);

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
        body: JSON.stringify({ message: trimmed }),
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
          } catch {
            // ignore unparseable chunks
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
        text: `Action executed successfully.\n${JSON.stringify(result.result, null, 2)}`,
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
      appendMessage({ role: "assistant", text: "Action cancelled." });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel action");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="assistant-chat">
      <div className="assistant-chat-header">
        <span className="assistant-chat-title">AI Assistant</span>
        <span className="assistant-chat-subtitle">
          Ask me to create meetings, draft materials, or generate reminders.
        </span>
      </div>

      <div className="assistant-chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="assistant-chat-empty">
            Try: "Create a weekly standup every Monday at 9am" or "Draft an agenda for tomorrow."
          </p>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`assistant-message assistant-message-${msg.role}`}>
            <div className="assistant-message-bubble">
              {msg.text && (
                <p className="assistant-message-text" style={{ whiteSpace: "pre-wrap" }}>
                  {msg.text}
                </p>
              )}
              {msg.proposal && (
                <div className="assistant-proposal">
                  <p className="assistant-proposal-summary">
                    <strong>Proposed action:</strong> {msg.proposal.preview_summary}
                  </p>
                  <div className="assistant-proposal-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleConfirm(msg.proposal!.action_id)}
                    >
                      Confirm
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleCancel(msg.proposal!.action_id)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="assistant-message assistant-message-assistant">
            <div className="assistant-message-bubble assistant-thinking">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}
      </div>

      {error && <p className="assistant-chat-error">{error}</p>}

      <div className="assistant-chat-input-row">
        <textarea
          className="assistant-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the assistant\u2026"
          rows={2}
          disabled={loading}
        />
        <button
          className="btn btn-primary btn-sm assistant-chat-send"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
