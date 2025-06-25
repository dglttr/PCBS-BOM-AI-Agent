import { motion } from "framer-motion";
import Link from "next/link";

import { MessageIcon } from "./icons";
import { LogoPython } from "@/app/icons";

export const Overview = () => {
  return (
    <motion.div
      key="overview"
      className="max-w-3xl mx-auto md:mt-20"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ delay: 0.5 }}
    >
      <div className="rounded-xl p-6 flex flex-col gap-8 leading-relaxed text-center max-w-xl">
        <p>
          Welcome to B.O.M.B.A., your AI-powered Bill of Materials (BOM) analyzer. Please upload a BOM file to get started.
        </p>
      </div>
    </motion.div>
  );
};
