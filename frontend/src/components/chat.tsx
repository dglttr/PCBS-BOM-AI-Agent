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

interface QuestionnaireData {
    jobId: string;
    questions: string[];
}

const ALLOWED_FILE_TYPES = [
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
  ];

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
        setFiles(prevFiles => [...prevFiles, ...droppedFiles]);
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
                    setBomResult(null);
                } else if (parsedContent?.type === 'bom_result' && isBomProcessingResult(parsedContent.data)) {
                    setBomResult(parsedContent.data);
                    if (parsedContent.data.results.processing_error) {
                        toast.error("BOM Processing Warning", {
                            description: parsedContent.data.results.processing_error,
                        });
                    }
                }
            } catch {
                // Not our special command, do nothing
            }
        }
    }, [messages]);

  const handleQuestionnaireSubmit = useCallback(async (answers: Record<string, string>) => {
    if (!questionnaire) return;
    setIsProcessing(true);
    setQuestionnaire(null);

    const messageData = {
        text: "Here are my project requirements. Please proceed with the analysis.",
        assumptions: answers,
        bom_job_ids: [questionnaire.jobId] // The agent expects a list
    };

    append({
        role: 'user',
        content: JSON.stringify(messageData),
    });

    setIsProcessing(false);
  }, [questionnaire, append]);

  const [messagesContainerRef, messagesEndRef] =
    useScrollToBottom<HTMLDivElement>();

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
                    Drop BOM files here
                </p>
            </div>
        )}
      <div
        ref={messagesContainerRef}
        className="flex flex-col min-w-0 gap-6 flex-1 overflow-y-scroll pt-4"
      >
        {displayMessages.length === 0 && <Overview />}

        {displayMessages.map((message: Message, index: number) => {
          try {
            const parsed = JSON.parse(message.content)
            if (parsed.type === 'bom_questionnaire' || parsed.type === 'bom_result') return null;
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
