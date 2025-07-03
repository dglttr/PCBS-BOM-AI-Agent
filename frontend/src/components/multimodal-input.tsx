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

const suggestedActions: {
  title: string;
  label: string;
  action: string;
}[] = [];

interface UploadResult {
  job_id: string;
  message: string;
}

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
  files,
  setFiles,
}: {
  input: string;
  setInput: (value: string) => void;
  isLoading: boolean;
  stop: () => void;
  messages: Array<Message>;
  setMessages: Dispatch<SetStateAction<Array<Message>>>;
  append: (
    message: Message | CreateMessage,
    chatRequestOptions?: ChatRequestOptions
  ) => Promise<string | null | undefined>;
  handleSubmit: (
    event?: {
      preventDefault?: () => void;
    },
    chatRequestOptions?: ChatRequestOptions
  ) => void;
  className?: string;
  files: File[];
  setFiles: Dispatch<SetStateAction<File[]>>;
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
      textareaRef.current.style.height = `${
        textareaRef.current.scrollHeight + 2
      }px`;
    }
  };

  const [localStorageInput, setLocalStorageInput] = useLocalStorage(
    "input",
    ""
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
    const selectedFiles = event.target.files;
    if (selectedFiles) {
      const newFiles = Array.from(selectedFiles);
      if (files.length + newFiles.length > 10) {
        toast.error("You can upload a maximum of 10 files.");
        return;
      }
      
      // Validate file types - accept both text/csv and files with .csv extension
      const invalidFiles = newFiles.filter(file => {
        const isCSV = file.type === "text/csv" || file.name.toLowerCase().endsWith('.csv');
        console.log("File validation:", file.name, file.type, isCSV);
        return !isCSV;
      });
      
      if (invalidFiles.length > 0) {
        toast.error("Only CSV files are allowed.");
        return;
      }
      
      console.log("Files added:", newFiles.map(f => f.name).join(', '));
      setFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    adjustHeight();
  };

  const submitForm = useCallback(async () => {
    if (!input && files.length === 0) return;

    if (files.length > 0) {
      console.log("Submitting files:", files.map(f => `${f.name} (${f.type})`).join(', '));
      const formData = new FormData();
      formData.append("file", files[0]);

      try {
        console.log("Sending file to API:", files[0].name);
        const response = await fetch("/api/production/upload", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json();
          console.error("File upload failed:", errorData);
          toast.error(
            `File upload failed: ${errorData.detail || "Unknown error"}`
          );
          return;
        }

        const uploadResults: UploadResult = await response.json();
        console.log("Upload successful:", uploadResults);

        // Read the CSV file to display its content
        const reader = new FileReader();
        reader.onload = async (e) => {
          const csvContent = e.target?.result as string;
          
          // Format CSV content as a markdown table
          const rows = csvContent.split('\n');
          const headers = rows[0].split(',').map(header => header.trim());
          
          let markdownTable = '| ' + headers.join(' | ') + ' |\n';
          markdownTable += '| ' + headers.map(() => '---').join(' | ') + ' |\n';
          
          // Add up to 10 rows max to avoid huge messages
          const dataRows = rows.slice(1, Math.min(11, rows.length));
          dataRows.forEach(row => {
            if (row.trim()) {
              markdownTable += '| ' + row.split(',').map(cell => cell.trim()).join(' | ') + ' |\n';
            }
          });
          
          if (rows.length > 11) {
            markdownTable += '*...and ' + (rows.length - 11) + ' more rows*';
          }

          // Store the job_id in a hidden format but display a clean message with the table
          const messageData = {
            production_plan_job_id: uploadResults.job_id,
            text: `✅ *CSV file uploaded (preview below)*` + "\n" + markdownTable + "\n\n" + input
          };

          append({
            role: "user",
            content: JSON.stringify(messageData),
          });

          setFiles([]);
          setInput("");
          setLocalStorageInput("");
        };
        
        reader.readAsText(files[0]);
      } catch (error) {
        toast.error("An unexpected error occurred during file upload.");
        console.error(error);
      }
    } else {
      if (!input) return;
      handleSubmit(undefined, {});
      setLocalStorageInput("");
    }

    if (width && width > 768) {
      textareaRef.current?.focus();
    }
  }, [files, input, append, handleSubmit, setLocalStorageInput, width]);

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

      {files.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {files.map((file, index) => (
            <div
              key={index}
              className="flex items-center gap-2 bg-muted text-sm border rounded-lg px-3 py-1.5"
            >
              <PaperclipIcon size={14} />
              <span className="flex-1 truncate">{file.name}</span>
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={() =>
                  setFiles((prev) => prev.filter((_, i) => i !== index))
                }
              >
                <CrossIcon size={14} />
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="relative">
        <Textarea
          ref={textareaRef}
          placeholder={
            files.length > 0
              ? "Describe the context for this production plan..."
              : "Send a message..."
          }
          value={input}
          onChange={handleInput}
          className={cn(
            "min-h-[24px] max-h-[calc(75dvh)] overflow-hidden resize-none rounded-xl text-base! bg-muted pl-10",
            className
          )}
          rows={3}
          autoFocus
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();

              if (isLoading) {
                toast.error(
                  "Please wait for the model to finish its response!"
                );
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
          accept=".csv,text/csv"
          multiple
        />

        <Button
          variant="ghost"
          size="icon"
          className="absolute bottom-2 left-2 m-0.5"
          onClick={(e) => {
            e.preventDefault();
            console.log("Paperclip clicked, opening file selector");
            if (fileInputRef.current) {
              fileInputRef.current.click();
            } else {
              console.error("File input reference is null");
            }
          }}
          disabled={isLoading || files.length >= 10}
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
            disabled={input.length === 0 && files.length === 0}
          >
            <ArrowUpIcon size={14} />
          </Button>
        )}
      </div>
    </div>
  );
}
