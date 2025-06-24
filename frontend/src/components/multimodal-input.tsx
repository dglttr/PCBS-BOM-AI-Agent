"use client";

import type { ChatRequestOptions, CreateMessage, Message } from "ai";
import { motion } from "framer-motion";
import type React from "react";
import {
  useRef,
  useEffect,
  useCallback,
  type Dispatch,
  type SetStateAction,
} from "react";
import { toast } from "sonner";
import { useLocalStorage, useWindowSize } from "usehooks-ts";

import { cn, sanitizeUIMessages } from "@/lib/utils";

import { ArrowUpIcon, PaperclipIcon, StopIcon, CrossIcon } from "./icons";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

const suggestedActions = [
  {
    title: "What is the weather",
    label: "in San Francisco?",
    action: "What is the weather in San Francisco?",
  },
  {
    title: "How is python useful",
    label: "for AI engineers?",
    action: "How is python useful for AI engineers?",
  },
];

export function MultimodalInput({
  input,
  setInput,
  isLoading,
  stop,
  messages,
  setMessages,
  append,
  handleSubmit,
  className,
  file,
  setFile,
}: {
  input: string;
  setInput: (value: string) => void;
  isLoading: boolean;
  stop: () => void;
  messages: Array<Message>;
  setMessages: Dispatch<SetStateAction<Array<Message>>>;
  append: (
    message: Message | CreateMessage,
    chatRequestOptions?: ChatRequestOptions,
  ) => Promise<string | null | undefined>;
  handleSubmit: (
    event?: {
      preventDefault?: () => void;
    },
    chatRequestOptions?: ChatRequestOptions,
  ) => void;
  className?: string;
  file: File | null;
  setFile: Dispatch<SetStateAction<File | null>>;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { width } = useWindowSize();

  useEffect(() => {
    if (textareaRef.current) {
      adjustHeight();
    }
  }, []);

  const adjustHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight + 2}px`;
    }
  };

  const [localStorageInput, setLocalStorageInput] = useLocalStorage(
    "input",
    "",
  );

  useEffect(() => {
    if (textareaRef.current) {
      const domValue = textareaRef.current.value;
      // Prefer DOM value over localStorage to handle hydration
      const finalValue = domValue || localStorageInput || "";
      setInput(finalValue);
      adjustHeight();
    }
    // Only run once after hydration
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setLocalStorageInput(input);
  }, [input, setLocalStorageInput]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) {
        // Limit file size to 10MB
        if (selectedFile.size > 10 * 1024 * 1024) {
            toast.error("File size cannot exceed 10MB.");
            return;
        }
        setFile(selectedFile);
    }
  };
  
  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    adjustHeight();
  };

  const submitForm = useCallback(async () => {
    if (!input && !file) return;

    if (file) {
        // If a file is attached, upload it first
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch('/api/bom/upload', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                toast.error(`File upload failed: ${errorData.detail || 'Unknown error'}`);
                return;
            }

            const { job_id, filename } = await response.json();
            
            // Append a message to the chat that includes the job_id in the content
            const messageData = {
                text: input || `Processing file: ${filename}`,
                bom_job_id: job_id
            };

            append({
                role: 'user',
                content: JSON.stringify(messageData),
            });

            // Clear file and input after successful submission
            setFile(null);
            setInput('');
            setLocalStorageInput("");

        } catch (error) {
            toast.error("An unexpected error occurred during file upload.");
            console.error(error);
        }
    } else {
        // Default behavior if no file is attached
        if (!input) return;
        handleSubmit(undefined, {});
        setLocalStorageInput("");
    }


    if (width && width > 768) {
      textareaRef.current?.focus();
    }
  }, [handleSubmit, setLocalStorageInput, width, append, input, file]);

  return (
    <div className="relative w-full flex flex-col gap-4">
      {messages.length === 0 && (
        <div className="grid sm:grid-cols-2 gap-2 w-full">
          {suggestedActions.map((suggestedAction, index) => (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ delay: 0.05 * index }}
              key={`suggested-action-${suggestedAction.title}-${index}`}
              className={index > 1 ? "hidden sm:block" : "block"}
            >
              <Button
                variant="ghost"
                onClick={async () => {
                  append({
                    role: "user",
                    content: suggestedAction.action,
                  });
                }}
                className="text-left border rounded-xl px-4 py-3.5 text-sm flex-1 gap-1 sm:flex-col w-full h-auto justify-start items-start"
              >
                <span className="font-medium">{suggestedAction.title}</span>
                <span className="text-muted-foreground">
                  {suggestedAction.label}
                </span>
              </Button>
            </motion.div>
          ))}
        </div>
      )}

      {file && (
        <div className="flex items-center gap-2 bg-muted text-sm border rounded-lg px-3 py-1.5">
          <PaperclipIcon />
          <span className="flex-1 truncate">{file.name}</span>
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            onClick={() => setFile(null)}
          >
            <CrossIcon size={14} />
          </Button>
        </div>
      )}

      <div className="relative">
        <Textarea
          ref={textareaRef}
          placeholder={file ? "Describe the context for this BOM..." : "Send a message..."}
          value={input}
          onChange={handleInput}
          className={cn(
            "min-h-[24px] max-h-[calc(75dvh)] overflow-hidden resize-none rounded-xl text-base! bg-muted pl-10",
            className,
          )}
          rows={3}
          autoFocus
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();

              if (isLoading) {
                toast.error("Please wait for the model to finish its response!");
              } else {
                submitForm();
              }
            }
          }}
        />

        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
          accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
        />

        <Button
          variant="ghost"
          size="icon"
          className="absolute bottom-2 left-2 m-0.5"
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading || !!file}
        >
          <PaperclipIcon />
        </Button>

        {isLoading ? (
          <Button
            className="rounded-full p-1.5 h-fit absolute bottom-2 right-2 m-0.5 border dark:border-zinc-600"
            onClick={(event) => {
              event.preventDefault();
              stop();
              setMessages((messages) => sanitizeUIMessages(messages));
            }}
          >
            <StopIcon size={14} />
          </Button>
        ) : (
          <Button
            className="rounded-full p-1.5 h-fit absolute bottom-2 right-2 m-0.5 border dark:border-zinc-600"
            onClick={(event) => {
              event.preventDefault();
              submitForm();
            }}
            disabled={input.length === 0 && !file}
          >
            <ArrowUpIcon size={14} />
          </Button>
        )}
      </div>
    </div>
  );
}
