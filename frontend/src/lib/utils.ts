import type { Message } from "@ai-sdk/react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function sanitizeUIMessages(messages: Array<Message>): Array<Message> {
  const messagesWithSanitizedParts = messages.map((message) => {
    if (message.role !== "assistant" || !message.parts) {
      return message;
    }

    const toolResultIds: string[] = [];
    for (const part of message.parts) {
      if (
        part.type === "tool-invocation" &&
        part.toolInvocation.state === "result"
      ) {
        toolResultIds.push(part.toolInvocation.toolCallId);
      }
    }

    const sanitizedParts = message.parts.filter((part) => {
      if (part.type !== "tool-invocation") {
        return true;
      }
      const { toolInvocation } = part;
      return (
        toolInvocation.state === "result" ||
        toolResultIds.includes(toolInvocation.toolCallId)
      );
    });

    return {
      ...message,
      parts: sanitizedParts,
    };
  });

  return messagesWithSanitizedParts.filter(
    (message) =>
      message.content.length > 0 ||
      (message.parts &&
        message.parts.some((part) => part.type === "tool-invocation")),
  );
}
