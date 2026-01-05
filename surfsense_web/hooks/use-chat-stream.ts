import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { getBearerToken } from "@/lib/auth-utils";
import { setActivePodcastTaskId } from "@/lib/chat/podcast-state";

/**
 * Tools that should render custom UI in the chat.
 */
export const TOOLS_WITH_UI = new Set([
	"generate_podcast",
	"link_preview",
	"display_image",
	"scrape_webpage",
	"write_todos",
]);

/**
 * Type for thinking step data from the backend
 */
export interface ThinkingStepData {
	id: string;
	title: string;
	status: "pending" | "in_progress" | "completed";
	items: string[];
}

interface StreamChatParams {
	searchSpaceId: number;
	chatId: number;
	userQuery: string;
	messageHistory: any[];
	attachments?: any[];
	mentionedDocumentIds?: number[];
	assistantMsgId: string;
	onMessageUpdate: (assistantMsgId: string, content: any[]) => void;
	onThinkingUpdate: (assistantMsgId: string, steps: ThinkingStepData[]) => void;
	onFinish?: (contentParts: any[], thinkingSteps: ThinkingStepData[]) => void;
	onError?: (error: Error) => void;
}

export function useChatStream() {
	const [isRunning, setIsRunning] = useState(false);
	const abortControllerRef = useRef<AbortController | null>(null);

	const cancelRun = useCallback(() => {
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
			abortControllerRef.current = null;
		}
		setIsRunning(false);
	}, []);

	const streamChat = useCallback(
		async ({
			searchSpaceId,
			chatId,
			userQuery,
			messageHistory,
			attachments = [],
			mentionedDocumentIds = [],
			assistantMsgId,
			onMessageUpdate,
			onThinkingUpdate,
			onFinish,
			onError,
		}: StreamChatParams) => {
			if (abortControllerRef.current) {
				abortControllerRef.current.abort();
			}
			const controller = new AbortController();
			abortControllerRef.current = controller;
			setIsRunning(true);

			// State for stream reconstruction
			const currentThinkingSteps = new Map<string, ThinkingStepData>();
			type ContentPart =
				| { type: "text"; text: string }
				| {
						type: "tool-call";
						toolCallId: string;
						toolName: string;
						args: Record<string, unknown>;
						result?: unknown;
				  };
			const contentParts: ContentPart[] = [];
			let currentTextPartIndex = -1;
			const toolCallIndices = new Map<string, number>();

			// Helpers
			const appendText = (delta: string) => {
				if (
					currentTextPartIndex >= 0 &&
					contentParts[currentTextPartIndex]?.type === "text"
				) {
					(contentParts[currentTextPartIndex] as { type: "text"; text: string }).text +=
						delta;
				} else {
					contentParts.push({ type: "text", text: delta });
					currentTextPartIndex = contentParts.length - 1;
				}
			};

			const addToolCall = (
				toolCallId: string,
				toolName: string,
				args: Record<string, unknown>
			) => {
				if (TOOLS_WITH_UI.has(toolName)) {
					contentParts.push({
						type: "tool-call",
						toolCallId,
						toolName,
						args,
					});
					toolCallIndices.set(toolCallId, contentParts.length - 1);
					currentTextPartIndex = -1;
				}
			};

			const updateToolCall = (
				toolCallId: string,
				update: { args?: Record<string, unknown>; result?: unknown }
			) => {
				const index = toolCallIndices.get(toolCallId);
				if (index !== undefined && contentParts[index]?.type === "tool-call") {
					const tc = contentParts[index] as ContentPart & { type: "tool-call" };
					if (update.args) tc.args = update.args;
					if (update.result !== undefined) tc.result = update.result;
				}
			};

			const buildContentForUI = () => {
				const filtered = contentParts.filter((part) => {
					if (part.type === "text") return part.text.length > 0;
					if (part.type === "tool-call") return TOOLS_WITH_UI.has(part.toolName);
					return false;
				});
				return filtered.length > 0
					? filtered
					: [{ type: "text", text: "" }];
			};

			try {
				const token = getBearerToken();
				if (!token) throw new Error("Not authenticated");

				const backendUrl =
					process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";

				const response = await fetch(`${backendUrl}/api/v1/new_chat`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${token}`,
					},
					body: JSON.stringify({
						chat_id: chatId,
						user_query: userQuery,
						search_space_id: searchSpaceId,
						messages: messageHistory,
						attachments: attachments.length > 0 ? attachments : undefined,
						mentioned_document_ids:
							mentionedDocumentIds.length > 0 ? mentionedDocumentIds : undefined,
					}),
					signal: controller.signal,
				});

				if (!response.ok) {
					throw new Error(`Backend error: ${response.status}`);
				}

				if (!response.body) {
					throw new Error("No response body");
				}

				const reader = response.body.getReader();
				const decoder = new TextDecoder();
				let buffer = "";

				while (true) {
					const { done, value } = await reader.read();
					if (done) break;

					buffer += decoder.decode(value, { stream: true });
					const events = buffer.split(/\r?\n\r?\n/);
					buffer = events.pop() || "";

					for (const event of events) {
						const lines = event.split(/\r?\n/);
						for (const line of lines) {
							if (!line.startsWith("data: ")) continue;
							const data = line.slice(6).trim();
							if (!data || data === "[DONE]") continue;

							try {
								const parsed = JSON.parse(data);

								switch (parsed.type) {
									case "text-delta":
										appendText(parsed.delta);
										onMessageUpdate(assistantMsgId, buildContentForUI());
										break;

									case "tool-input-start":
										addToolCall(parsed.toolCallId, parsed.toolName, {});
										onMessageUpdate(assistantMsgId, buildContentForUI());
										break;

									case "tool-input-available":
										if (toolCallIndices.has(parsed.toolCallId)) {
											updateToolCall(parsed.toolCallId, { args: parsed.input || {} });
										} else {
											addToolCall(parsed.toolCallId, parsed.toolName, parsed.input || {});
										}
										onMessageUpdate(assistantMsgId, buildContentForUI());
										break;

									case "tool-output-available":
										updateToolCall(parsed.toolCallId, { result: parsed.output });
										if (parsed.output?.status === "processing" && parsed.output?.task_id) {
											const idx = toolCallIndices.get(parsed.toolCallId);
											if (idx !== undefined) {
												const part = contentParts[idx];
												if (
													part?.type === "tool-call" &&
													part.toolName === "generate_podcast"
												) {
													setActivePodcastTaskId(parsed.output.task_id);
												}
											}
										}
										onMessageUpdate(assistantMsgId, buildContentForUI());
										break;

									case "data-thinking-step": {
										const stepData = parsed.data as ThinkingStepData;
										if (stepData?.id) {
											currentThinkingSteps.set(stepData.id, stepData);
											onThinkingUpdate(
												assistantMsgId,
												Array.from(currentThinkingSteps.values())
											);
										}
										break;
									}

									case "error":
										throw new Error(parsed.errorText || "Server error");
								}
							} catch (e) {
								if (e instanceof SyntaxError) continue;
								throw e;
							}
						}
					}
				}

				if (onFinish) {
					onFinish(contentParts, Array.from(currentThinkingSteps.values()));
				}
			} catch (error) {
				if (error instanceof Error && error.name === "AbortError") {
                    if (onFinish) {
                        onFinish(contentParts, Array.from(currentThinkingSteps.values()));
                    }
					return;
				}
				console.error("[useChatStream] Stream error:", error);
				if (onError && error instanceof Error) {
					onError(error);
				} else {
                    toast.error("Failed to get response. Please try again.");
                }
			} finally {
				setIsRunning(false);
				abortControllerRef.current = null;
			}
		},
		[]
	);

	return { streamChat, cancelRun, isRunning };
}
