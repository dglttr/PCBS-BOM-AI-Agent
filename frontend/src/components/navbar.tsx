"use client";

import { Button } from "./ui/button";
import Link from "next/link";

export const Navbar = () => {
  return (
    <div className="p-2 flex flex-row gap-2 justify-between">
      <Link href="https://example.com">
        <Button variant="outline">
          Link 1
        </Button>
      </Link>

      <Link href="https://example.com">
        <Button>
          Link 2
        </Button>
      </Link>
    </div>
  );
};
