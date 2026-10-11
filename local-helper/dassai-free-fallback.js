const FALLBACK_MODEL = { providerID: "google-gemini", modelID: "gemini-3.8-flash" };
const RATE_LIMIT_ERROR = /\b429\b|\b402\b|free.?usage.?limit|usage limit|usage exceeded|quota|rate.?limit|too many requests|resource[_ -]?exhausted|insufficient.{0,20}(credit|fund|balance)|out of (credits|requests)|daily limit/i;
const DEDUP_TTL_MS = 30 * 60 * 1000;

function errorText(value) {
  try {
    return typeof value === "string" ? value : JSON.stringify(value);
  } catch {
    return String(value ?? "");
  }
}

function isRateLimit(value) {
  return RATE_LIMIT_ERROR.test(errorText(value));
}

function toPromptParts(parts) {
  return (Array.isArray(parts) ? parts : []).flatMap((part) => {
    if (part?.type === "text") {
      return [{ type: "text", text: String(part.text ?? "") }];
    }
    if (part?.type === "file") {
      const url = part.url || part.path;
      if (!url) return [];
      return [{
        type: "file",
        url,
        mime: part.mime || part.mediaType || "application/octet-stream",
      }];
    }
    return [];
  });
}

export const DASSAIFreeFallback = async ({ client }) => {
  // The browser chat has its own fallback logic. The Windows launcher sets this
  // flag only for its OpenCode server to prevent two retries racing each other.
  if (process.env.DASSAI_DISABLE_OPENCODE_FALLBACK === "1") return {};
  // The native OpenCode TUI needs the key in the user's environment; do not
  // launch a fallback request that cannot authenticate.
  if (!process.env.GEMINI_API_KEY) return {};

  const inFlight = new Set();
  const attempted = new Map();
  const fallbackPendingUntil = new Map();

  async function notify(title, message, variant = "info") {
    try {
      if (client.tui?.showToast) {
        await client.tui.showToast({
          body: { title, message, variant, duration: 5000 },
        });
      }
    } catch {
      // The plugin also runs in non-TUI contexts where toast is unavailable.
    }
  }

  async function handleQuotaError(sessionID, error, providerHint, modelHint) {
    if (!sessionID || !isRateLimit(error) || inFlight.has(sessionID)) return;
    inFlight.add(sessionID);

    try {
      const result = await client.session.messages({ path: { id: sessionID } });
      const messages = Array.isArray(result?.data) ? result.data : [];
      const lastAssistant = [...messages].reverse().find((m) => m?.info?.role === "assistant");
      const failedProvider = providerHint || lastAssistant?.info?.providerID || "";
      const failedModel = modelHint || lastAssistant?.info?.modelID || "";

      const pendingUntil = fallbackPendingUntil.get(sessionID) || 0;
      if (pendingUntil > Date.now()) {
        if (failedProvider === FALLBACK_MODEL.providerID) {
          await notify(
            "Geminiの無料枠も上限です",
            "Geminiの利用上限に達しました。別の無料モデルはまだ登録されていないため、再試行を止めました。",
            "warning",
          );
        }
        return;
      }
      if (pendingUntil) fallbackPendingUntil.delete(sessionID);

      if (failedProvider === FALLBACK_MODEL.providerID && failedModel === FALLBACK_MODEL.modelID) {
        await notify(
          "無料枠を使い切りました",
          "Geminiの利用上限です。ほかに接続済みの無料モデルがないため、自動切替を停止しました。",
          "warning",
        );
        return;
      }

      const lastUser = [...messages].reverse().find((m) => m?.info?.role === "user");
      if (!lastUser?.info?.id) return;
      const dedupKey = `${sessionID}:${lastUser.info.id}`;
      const now = Date.now();
      for (const [key, timestamp] of attempted) {
        if (now - timestamp > DEDUP_TTL_MS) attempted.delete(key);
      }
      if (attempted.has(dedupKey)) return;
      attempted.set(dedupKey, now);

      const parts = toPromptParts(lastUser.parts);
      if (!parts.some((part) => part.type === "text" || part.type === "file")) return;

      await notify(
        "無料枠の上限を検出",
        `${failedModel || failedProvider || "現在のモデル"} から Gemini 3.8 Flash へ切り替えて再試行します。`,
        "warning",
      );

      try {
        await client.session.abort({ path: { id: sessionID } });
      } catch {
        // It may already have stopped after reporting the provider error.
      }
      await new Promise((resolve) => setTimeout(resolve, 500));

      fallbackPendingUntil.set(sessionID, Date.now() + DEDUP_TTL_MS);
      await client.session.promptAsync({
        path: { id: sessionID },
        body: {
          parts,
          model: FALLBACK_MODEL,
          ...(lastAssistant?.info?.agent ? { agent: lastAssistant.info.agent } : {}),
        },
      });
      await notify("モデルを切り替えました", "Gemini 3.8 Flash で同じメッセージを再試行中です。", "success");
    } catch (err) {
      fallbackPendingUntil.delete(sessionID);
      await notify("自動切替に失敗しました", errorText(err), "error");
    } finally {
      inFlight.delete(sessionID);
    }
  }

  return {
    event: async ({ event }) => {
      if (event?.type === "session.error") {
        const props = event.properties || {};
        await handleQuotaError(props.sessionID, props.error);
        return;
      }
      if (event?.type === "message.updated") {
        const info = event.properties?.info;
        if (info?.role === "assistant" && info?.status === "completed" && !info?.error) {
          fallbackPendingUntil.delete(info.sessionID);
        }
        if (info?.role === "assistant" && info?.error) {
          await handleQuotaError(info.sessionID, info.error, info.providerID, info.modelID);
          if (info.providerID === FALLBACK_MODEL.providerID && !isRateLimit(info.error)) {
            fallbackPendingUntil.delete(info.sessionID);
          }
        }
      }
    },
  };
};
