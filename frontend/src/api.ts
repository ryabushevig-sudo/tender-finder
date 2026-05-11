import axios from "axios";

const apiBase = (import.meta as ImportMeta & { env: Record<string, string> }).env.VITE_API_BASE || "";

export const api = axios.create({
  baseURL: apiBase,
  timeout: 600_000,
});

export type LlmHealth = {
  provider: string;
  model: string;
  healthy: boolean;
};

export type DocumentSummary = {
  id: string;
  filename: string;
  status: string;
  size_bytes: number;
  created_at: string;
  updated_at: string;
  items_count: number;
};

export type Offer = {
  id: string;
  position: number;
  title: string;
  url: string;
  supplier_domain: string | null;
  snippet: string | null;
  price: string | null;
  contact_phone: string | null;
  contact_email: string | null;
};

export type Item = {
  id: string;
  document_id: string;
  position: number;
  name: string;
  quantity: number | null;
  unit: string | null;
  gost: string | null;
  okpd2: string | null;
  specifications: Record<string, unknown> | null;
  notes: string | null;
  search_query: string | null;
  offers: Offer[];
};

export type DocumentDetail = DocumentSummary & {
  mime_type: string | null;
  error: string | null;
  items: Item[];
};

export async function getLlmHealth() {
  const res = await api.get<LlmHealth>("/api/system/llm");
  return res.data;
}

export async function listDocuments() {
  const res = await api.get<DocumentSummary[]>("/api/documents");
  return res.data;
}

export async function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post<DocumentSummary>("/api/documents", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function getDocument(id: string) {
  const res = await api.get<DocumentDetail>(`/api/documents/${id}`);
  return res.data;
}

export async function deleteDocument(id: string) {
  await api.delete(`/api/documents/${id}`);
}

export async function extractItems(id: string) {
  const res = await api.post<{ items: Item[] }>(`/api/documents/${id}/extract`);
  return res.data.items;
}

export async function exportDocument(id: string) {
  const res = await api.get(`/api/documents/${id}/export`, { responseType: "blob" });
  return res.data as Blob;
}

export async function updateItem(itemId: string, patch: Partial<Item>) {
  const res = await api.patch<Item>(`/api/items/${itemId}`, patch);
  return res.data;
}

export async function deleteItem(itemId: string) {
  await api.delete(`/api/items/${itemId}`);
}

export async function searchForItem(itemId: string) {
  const res = await api.post<{ item_id: string; offers: Offer[] }>(
    `/api/items/${itemId}/search`,
  );
  return res.data.offers;
}
