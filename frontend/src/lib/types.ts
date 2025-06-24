// This file contains TypeScript types that mirror the Pydantic models on the backend.
// Keeping them in sync is crucial for type safety between the frontend and backend.

export interface OctopartSpec {
    name: string;
    value: string;
    units: string | null;
}

export interface OctopartPriceBreak {
    quantity: number;
    price: number;
    currency: string;
}

export interface OctopartOffer {
    inventory_level: number;
    prices: OctopartPriceBreak[];
}

export interface OctopartSeller {
    company_name: string;
    offers: OctopartOffer[];
}

export interface OctopartPart {
    mpn: string;
    manufacturer_name: string;
    short_description: string | null;
    octopart_url: string | null;
    specs: OctopartSpec[];
    sellers: OctopartSeller[];
    similar_parts: SimilarPart[];
}

export interface SimilarPart {
    mpn: string | null;
    manufacturer_name: string | null;
    specs: OctopartSpec[];
}

export interface ExtractedParameters {
    electrical_value: string | null;
    tolerance: string | null;
    voltage: string | null;
    package_footprint: string | null;
}

export interface ParsedBomItem {
    original_row_text: string;
    manufacturer_part_number: string | null;
    designators: string[];
    quantity: number;
    parameters: ExtractedParameters;
    parsing_notes: string | null;
    octopart_data: OctopartPart | null;
    recommended_alternative: SimilarPart | null;
    cost_analysis: CostAnalysis | null;
}

export interface CostAnalysis {
    original_part_cost: number | null;
    alternative_part_cost: number | null;
    savings_per_board: number | null;
    total_savings: number | null;
}

export interface BomProcessingResult {
    message: string;
    job_id: string;
    results: {
        column_mapping: Record<string, string | null>;
        parsed_items: (ParsedBomItem | { error: string })[];
        processing_error: string | null;
    };
}

export function isBomProcessingResult(obj: unknown): obj is BomProcessingResult {
    if (typeof obj !== 'object' || obj === null) {
        return false;
    }

    const o = obj as { [key: string]: unknown };

    return (
        'message' in o &&
        'job_id' in o &&
        'results' in o &&
        typeof o.results === 'object' &&
        o.results !== null &&
        'parsed_items' in (o.results as { [key: string]: unknown }) &&
        'processing_error' in (o.results as { [key: string]: unknown })
    );
} 