// This file contains TypeScript types that mirror the Pydantic models on the backend.
// Keeping them in sync is crucial for type safety between the frontend and backend.

export interface ProductionPlanItem {
    date: string;
    transaction_type: string;
    product: string;
    quantity: string;
}

export interface ProductionPlanResult {
    result: string;
}

export interface UploadResult {
    job_id: string;
    message: string;
} 