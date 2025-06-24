"use client"

import { ColumnDef } from "@tanstack/react-table"
import { ParsedBomItem, SimilarPart } from "@/lib/types"
import { Badge } from "@/components/ui/badge"

export const columns: ColumnDef<ParsedBomItem>[] = [
  {
    accessorKey: "manufacturer_part_number",
    header: "MPN",
  },
  {
    accessorKey: "designators",
    header: "Designators",
    cell: ({ row }) => {
        const designators = row.getValue("designators") as string[]
        // Display only the first 3 designators for brevity
        const display = designators.length > 3 
            ? `${designators.slice(0, 3).join(", ")}...` 
            : designators.join(", ")
        return <div title={designators.join(", ")}>{display}</div>
    }
  },
  {
    accessorKey: "quantity",
    header: "Quantity",
  },
  {
    accessorKey: "parameters.electrical_value",
    header: "Value",
  },
  {
    accessorKey: "parameters.tolerance",
    header: "Tolerance",
  },
    {
    accessorKey: "parameters.voltage",
    header: "Voltage",
  },
  {
    accessorKey: "parameters.package_footprint",
    header: "Package",
  },
  {
    accessorKey: "cost_analysis.original_part_cost",
    header: "Original Cost",
    cell: ({ row }) => {
        const cost = row.original.cost_analysis?.original_part_cost
        return cost ? `$${cost.toFixed(4)}` : <span className="text-muted-foreground">N/A</span>
    }
  },
  {
    accessorKey: "cost_analysis.alternative_part_cost",
    header: "Alternative Cost",
    cell: ({ row }) => {
        const cost = row.original.cost_analysis?.alternative_part_cost
        return cost ? `$${cost.toFixed(4)}` : <span className="text-muted-foreground">N/A</span>
    }
  },
  {
    accessorKey: "recommended_alternative",
    header: "Recommendation",
    cell: ({ row }) => {
        const alternative = row.getValue("recommended_alternative") as SimilarPart | null
        const savings = row.original.cost_analysis?.total_savings
        
        if (!alternative) {
            return <div className="text-muted-foreground">None found</div>
        }

        return (
            <div className="flex flex-col">
                <span className="font-medium">{alternative.mpn}</span>
                {savings && savings > 0 && (
                     <Badge variant="secondary" className="w-fit">
                        Save ${savings.toFixed(2)}
                    </Badge>
                )}
            </div>
        )
    }
  },
] 