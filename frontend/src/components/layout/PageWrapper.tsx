import { motion } from "framer-motion";
import type { ReactNode } from "react";

type PageWrapperProps = {
  children: ReactNode;
};

export default function PageWrapper({ children }: PageWrapperProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0, transition: { duration: 0.45 } }}
      exit={{ opacity: 0, y: -8, transition: { duration: 0.25 } }}
    >
      {children}
    </motion.div>
  );
}
