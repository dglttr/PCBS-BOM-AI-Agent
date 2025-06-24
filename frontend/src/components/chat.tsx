"use client";

import { PreviewMessage, ThinkingMessage } from "@/components/message";
import { MultimodalInput } from "@/components/multimodal-input";
import { Overview } from "@/components/overview";
import { useScrollToBottom } from "@/hooks/use-scroll-to-bottom";
import { useChat, type Message } from "@ai-sdk/react";
import { useState, useCallback, useMemo, useEffect } from "react";
import { toast } from "sonner";
import { BomDisplay } from "./bom-display";
import { BomQuestionnaire } from "./bom-questionnaire";
import { BomProcessingResult, isBomProcessingResult } from "@/lib/types";

const ALLOWED_FILE_TYPES = [
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
  ];

interface QuestionnaireData {
    jobId: string;
    questions: string[];
}

export function Chat() {
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [bomResult, setBomResult] = useState<BomProcessingResult | null>(null);
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireData | null>(null);

  const {
    messages,
    setMessages,
    handleSubmit,
    input,
    setInput,
    append,
    stop,
    isLoading: isChatLoading,
  } = useChat({
    maxSteps: 4,
    onError: (error: Error) => {
      if (error.message.includes("Too many requests")) {
        toast.error(
          "You are sending too many messages. Please try again later.",
        );
      }
    },
  });

  const [isProcessing, setIsProcessing] = useState(false);
  const isLoading = isChatLoading || isProcessing;

  const handleDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    // Use relatedTarget to prevent flickering when dragging over child elements
    if (!event.currentTarget.contains(event.relatedTarget as Node)) {
        setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const droppedFile = event.dataTransfer.files[0];
    if (droppedFile) {
        if (!ALLOWED_FILE_TYPES.includes(droppedFile.type)) {
            toast.error("Invalid file type. Please upload a CSV or Excel file.");
            return;
        }
        if (droppedFile.size > 10 * 1024 * 1024) {
            toast.error("File size cannot exceed 10MB.");
            return;
        }
        if (files.length + 1 > 10) {
            toast.error("You can upload a maximum of 10 files.");
            return;
        }
        setFiles(prevFiles => [...prevFiles, droppedFile]);
    }
  }, [files.length]);

  const displayMessages = useMemo(() => {
    return messages.map((msg) => {
      if (msg.role === 'user') {
        try {
          const parsedContent = JSON.parse(msg.content);
          if (parsedContent.text) {
            return { ...msg, content: parsedContent.text };
          }
        } catch {
          // Not JSON, return original
        }
      }
      return msg;
    });
  }, [messages]);

  // Effect to process messages for special commands
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.role === 'assistant') {
      try {
        const parsedContent = JSON.parse(lastMessage.content);
        if (parsedContent?.type === 'bom_questionnaire' && parsedContent.data) {
          setQuestionnaire({
            jobId: parsedContent.data.job_id,
            questions: parsedContent.data.questions,
          });
          setBomResult(null); // Clear previous results
        }
      } catch {
        // Not our special command, do nothing
      }
    }
  }, [messages]);

  const handleQuestionnaireSubmit = useCallback(async (answers: Record<string, string>) => {
    if (!questionnaire) return;
    setIsProcessing(true);
    setQuestionnaire(null); // Hide questionnaire form

    try {
        const response = await fetch(`/api/bom/process/${questionnaire.jobId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ assumptions: answers }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "Failed to process BOM.");
        }

        const resultData = await response.json();
        if (isBomProcessingResult(resultData)) {
            setBomResult(resultData);
            if (resultData.results.processing_error) {
                toast.error("BOM Processing Warning", {
                    description: resultData.results.processing_error,
                });
            }
        } else {
            throw new Error("Received unexpected data structure from server.");
        }
    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : "An unknown error occurred.";
        toast.error("Processing Failed", { description: errorMessage });
    } finally {
        setIsProcessing(false);
    }
  }, [questionnaire]);

  const [messagesContainerRef, messagesEndRef] =
    useScrollToBottom<HTMLDivElement>();

  return (
    <div 
        className="relative flex flex-col min-w-0 h-[calc(100dvh-52px)] bg-background"
        onDragEnter={handleDragEnter}
        onDragOver={(e) => e.preventDefault()} // Necessary to allow dropping
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
    >
        {isDragging && (
            <div className="absolute inset-0 z-10 bg-black/50 flex items-center justify-center rounded-lg border-2 border-dashed border-primary">
                <p className="text-primary-foreground text-lg font-semibold">
                    Drop BOM file here
                </p>
            </div>
        )}
      <div
        ref={messagesContainerRef}
        className="flex flex-col min-w-0 gap-6 flex-1 overflow-y-scroll pt-4"
      >
        {displayMessages.length === 0 && <Overview />}

        {displayMessages.map((message: Message, index: number) => {
          // Hide the assistant message that contains the raw questionnaire data
          try {
            const parsed = JSON.parse(message.content)
            if (parsed.type === 'bom_questionnaire') return null;
          } catch {}

          return (
            <PreviewMessage
              key={message.id}
              message={message}
              isLoading={isLoading && messages.length - 1 === index}
            />
          )
        })}

        {(isLoading && !bomResult && !questionnaire) && <ThinkingMessage />}

        {questionnaire && (
            <BomQuestionnaire
                jobId={questionnaire.jobId}
                questions={questionnaire.questions}
                onSubmit={handleQuestionnaireSubmit}
            />
        )}
        
        {bomResult && <BomDisplay data={bomResult} />}

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
