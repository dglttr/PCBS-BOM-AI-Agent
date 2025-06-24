"use client";

import { BomProcessingResult } from "@/lib/types";
import { DataTable } from "./data-table";
import { columns } from "./bom-results-columns";

export const BomDisplay = ({ data }: { data: BomProcessingResult }) => {
    // Filter out any items that resulted in an error during parsing
    const validItems = data.results.parsed_items.filter((item): item is ParsedBomItem => 'manufacturer_part_number' in item);

    return (
        <div className="p-4 bg-muted rounded-lg w-full my-4">
            <h3 className="font-bold text-lg">BOM Processing Complete</h3>
            <p className="text-sm text-muted-foreground mb-4">
                Successfully parsed {validItems.length} out of {data.results.parsed_items.length} items.
            </p>
            <DataTable columns={columns} data={validItems} />
        </div>
    )
}; 