"use client";

import { PreviewMessage, ThinkingMessage } from "@/components/message";
import { MultimodalInput } from "@/components/multimodal-input";
import { Overview } from "@/components/overview";
import { useScrollToBottom } from "@/hooks/use-scroll-to-bottom";
import { useChat, type Message } from "@ai-sdk/react";
import { useState, useCallback, useMemo, useEffect } from "react";
import { toast } from "sonner";

const ALLOWED_FILE_TYPES = [
    "text/csv",
];

export function Chat() {
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [activeToolName, setActiveToolName] = useState<string | undefined>(undefined);
  const [hasStreamingStarted, setHasStreamingStarted] = useState(false);

  const {
    messages,
    setMessages,
    handleSubmit,
    input,
    setInput,
    append,
    stop,
    isLoading: isChatLoading,
    data,
  } = useChat({
    maxSteps: 4,
    onError: (error: Error) => {
      if (error.message.includes("Too many requests")) {
        toast.error(
          "You are sending too many messages. Please try again later.",
        );
      }
    },
    onFinish: () => {
      // Reset states when the chat finishes
      setActiveToolName(undefined);
      setHasStreamingStarted(false);
    }
  });

  const [isProcessing, setIsProcessing] = useState(false);
  const isLoading = isChatLoading || isProcessing;

  // Process messages to detect tool start markers and update activeToolName
  useEffect(() => {
    // Look for special tool markers in the messages
    const lastMessage = messages[messages.length - 1];
    
    if (lastMessage?.role === 'assistant') {
      // If the last message has any real content (not just the marker), 
      // consider streaming has started
      if (typeof lastMessage.content === 'string') {
        const contentWithoutMarker = lastMessage.content.replace(/__TOOL_START:.*?__/g, '').trim();
        
        if (contentWithoutMarker) {
          setHasStreamingStarted(true);
        }
        
        // Check for tool start marker
        if (lastMessage.content.includes('__TOOL_START:optimize_production_plan__')) {
          console.log("Optimize production plan - tool start marker found");
          setActiveToolName('optimize_production_plan');
          
          // Remove the marker message by creating a filtered copy of messages
          const filteredMessages = messages.map(msg => {
            if (msg.id === lastMessage.id) {
              return {
                ...msg,
                content: msg.content.replace(/__TOOL_START:.*?__/g, '')
              };
            }
            return msg;
          });
          setMessages(filteredMessages);
        }
      }
    }
  }, [messages, setMessages]);

  const handleDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!event.currentTarget.contains(event.relatedTarget as Node)) {
        setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const droppedFiles = Array.from(event.dataTransfer.files);
    if (droppedFiles.length > 0) {
      if (files.length + droppedFiles.length > 10) {
        toast.error("You can upload a maximum of 10 files.");
        return;
      }
      
      // Validate file types - accept both text/csv and files with .csv extension
      const validFiles = droppedFiles.filter(file => {
        const isCSV = file.type === "text/csv" || file.name.toLowerCase().endsWith('.csv');
        console.log("Dropped file validation:", file.name, file.type, isCSV);
        return isCSV;
      });
      
      if (validFiles.length !== droppedFiles.length) {
        toast.error("Only CSV files are allowed.");
        // Still add the valid files
        if (validFiles.length > 0) {
          console.log("Valid files dropped:", validFiles.map(f => f.name).join(', '));
          setFiles(prevFiles => [...prevFiles, ...validFiles]);
        }
        return;
      }
      
      console.log("All files valid, adding to state");
      setFiles(prevFiles => [...prevFiles, ...droppedFiles]);
    }
  }, [files.length]);

  // Process messages for display
  const displayMessages = useMemo(() => {
    return messages.map((message) => {
      if (message.role === "user") {
        try {
          const parsed = JSON.parse(message.content);
          // Check if this is a production plan message
          if (parsed.production_plan_job_id && parsed.text) {
            // Create a new message with just the text
            return {
              ...message,
              content: parsed.text
            };
          }
          // Check if this is a special message type that should be filtered
          if (parsed.type) {
            // Return null for messages that should be filtered out
            return null;
          }
        } catch {
          // Not JSON or doesn't have the expected structure, return as is
        }
      } else if (message.role === "assistant" && typeof message.content === 'string') {
        // Filter out any tool marker messages
        if (message.content.includes('__TOOL_START:')) {
          // Return the message with the markers removed
          return {
            ...message,
            content: message.content
              .replace(/__TOOL_START:.*?__/g, '')
          };
        }
      }
      return message;
    }).filter(message => {
      // Filter out empty messages
      if (message && typeof message.content === 'string') {
        return message.content.trim() !== '';
      }
      return true;
    }) as Message[]; // Filter out null messages
  }, [messages]);

  const [messagesContainerRef, messagesEndRef] =
    useScrollToBottom<HTMLDivElement>();

  // Determine if we should show the thinking message
  const showThinkingMessage = isLoading && (!hasStreamingStarted || !displayMessages.length);

  return (
    <div 
        className="relative flex flex-col min-w-0 h-[calc(100dvh-52px)] bg-background"
        onDragEnter={handleDragEnter}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
    >
        {isDragging && (
            <div className="absolute inset-0 z-10 bg-black/50 flex items-center justify-center rounded-lg border-2 border-dashed border-primary">
                <p className="text-primary-foreground text-lg font-semibold">
                    Drop production plan CSV here
                </p>
            </div>
        )}
      
      <div
        ref={messagesContainerRef}
        className="flex flex-col min-w-0 gap-6 flex-1 overflow-y-scroll pt-4"
      >
        {displayMessages.length === 0 && <Overview />}

        {displayMessages.map((message: Message, index: number) => (
          <PreviewMessage
            key={message.id}
            message={message}
            isLoading={isLoading && messages.length - 1 === index}
          />
        ))}

        {showThinkingMessage && <ThinkingMessage toolName={activeToolName} />}

        <div
          ref={messagesEndRef}
          className="shrink-0 min-w-[24px] min-h-[24px]"
        />
      </div>

      <form className="flex mx-auto px-4 bg-background pb-4 md:pb-6 gap-2 w-full md:max-w-3xl">
        <MultimodalInput
          input={input}
          setInput={setInput}
          handleSubmit={handleSubmit}
          isLoading={isLoading}
          stop={stop}
          messages={messages}
          setMessages={setMessages}
          append={append}
          files={files}
          setFiles={setFiles}
        />
      </form>
    </div>
  );
}
