"use client"

import { ColumnDef } from "@tanstack/react-table"
import { ParsedBomItem } from "@/lib/types"

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
] 