"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';

interface BomQuestionnaireProps {
  jobId: string;
  questions: string[];
  onSubmit: (answers: Record<string, string>) => void;
}

export const BomQuestionnaire = ({ jobId, questions, onSubmit }: BomQuestionnaireProps) => {
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const handleInputChange = (question: string, value: string) => {
    setAnswers(prev => ({ ...prev, [question]: value }));
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (Object.keys(answers).length !== questions.length) {
      toast.error("Please answer all questions before submitting.");
      return;
    }
    console.log("Submitting answers:", { jobId, answers });
    onSubmit(answers);
  };

  return (
    <Card className="w-full max-w-2xl mx-auto my-4">
      <CardHeader>
        <CardTitle>Project Requirements</CardTitle>
        <CardDescription>
          Please answer a few questions to help me find the best components for your BOM.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          {questions.map((q, index) => (
            <div key={index} className="space-y-2">
              <Label htmlFor={`question-${index}`}>{q}</Label>
              <Input
                id={`question-${index}`}
                value={answers[q] || ''}
                onChange={(e) => handleInputChange(q, e.target.value)}
                placeholder="Your answer..."
                required
              />
            </div>
          ))}
        </CardContent>
        <CardFooter>
          <Button type="submit">Start Analysis</Button>
        </CardFooter>
      </form>
    </Card>
  );
}; 