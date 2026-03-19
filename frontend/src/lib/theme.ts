export type ServiceItem = {
  id: string;
  title: string;
  description: string;
  metric: string;
};

export const services: ServiceItem[] = [
  {
    id: "ingestion",
    title: "Real-Time Ingestion",
    description:
      "Continuously pulls events from RSS, SEC filings, APIs, and custom connectors with retry-safe workers.",
    metric: "24/7 stream"
  },
  {
    id: "normalization",
    title: "Schema Normalization",
    description:
      "Converts heterogeneous payloads into one canonical event model with source lineage and validation gates.",
    metric: "typed events"
  },
  {
    id: "enrichment",
    title: "LLM Enrichment",
    description:
      "Applies prompt-driven classification, extraction, and summarization to convert raw content into usable insight.",
    metric: "context-rich"
  },
  {
    id: "vector",
    title: "Vector Indexing",
    description:
      "Embeds documents and stores semantic vectors for fast retrieval and question answering.",
    metric: "sub-second search"
  },
  {
    id: "observability",
    title: "Observability & Alerts",
    description:
      "Tracks worker health, latency, and throughput with operational dashboards and actionable incident signals.",
    metric: "ops-ready"
  },
  {
    id: "delivery",
    title: "API Delivery Layer",
    description:
      "Exposes clean APIs for search, stats, and health so downstream apps can integrate without pipeline complexity.",
    metric: "integration-first"
  }
];

export const navLinks = [
  { label: "Home", to: "/" },
  { label: "About", to: "/about" },
  { label: "Services", to: "/services" },
  { label: "Contact", to: "/contact" },
  { label: "Dashboard", to: "/dashboard" }
];
