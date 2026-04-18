import axios from "axios";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8005";
const api = axios.create({
  baseURL: apiBaseUrl,
});

const aiApi = axios.create({
  baseURL: apiBaseUrl,
});

export const uploadStatement = async (file, bankName) => {
  const form = new FormData();
  form.append("file", file);
  const params = bankName ? { bank_name: bankName } : {};
  const { data } = await api.post("/api/upload-statement", form, { params });
  return data;
};

export const getTransactions = async (filters) => {
  const { data } = await api.get("/api/transactions", { params: filters });
  return data;
};

export const getDashboard = async (filters) => {
  const { data } = await api.get("/api/dashboard", { params: filters });
  return data;
};

export const generateInsights = async () => {
  const { data } = await api.post("/api/insights/generate");
  return data;
};

export const getInsights = async () => {
  const { data } = await api.get("/api/insights");
  return data;
};

export const getAiAdvice = async () => {
  const { data } = await aiApi.get("/api/ai/advice");
  return data;
};

export const getAiDiagnostics = async () => {
  const { data } = await aiApi.get("/api/ai/diagnostics");
  return data;
};

export const getForecast = async () => {
  const { data } = await api.post("/api/forecast");
  return data;
};

export const upsertBudget = async (payload) => {
  const { data } = await api.post("/api/budgets", payload);
  return data;
};

export const getBudgets = async (month) => {
  const { data } = await api.get("/api/budgets", { params: { month } });
  return data;
};

export const updateCategory = async (id, category, keyword) => {
  const { data } = await api.patch(`/api/transactions/${id}/category`, { category, keyword });
  return data;
};

export const getPremiumOverview = async () => {
  const { data } = await api.get("/api/premium/overview");
  return data;
};

export const createGoal = async (payload) => {
  const { data } = await api.post("/api/goals", payload);
  return data;
};

export const getGoals = async () => {
  const { data } = await api.get("/api/goals");
  return data;
};

export const updateGoalProgress = async (goalId, currentAmount) => {
  const { data } = await api.patch(`/api/goals/${goalId}/progress`, { current_amount: currentAmount });
  return data;
};

export const getMerchantMappings = async () => {
  const { data } = await api.get("/api/merchant-mappings");
  return data;
};

export const applyMerchantMappingsBulk = async (mappings) => {
  const { data } = await api.put("/api/merchant-mappings/bulk", { mappings });
  return data;
};

export const exportTransactionsXlsxUrl = `${apiBaseUrl}/api/export/transactions.xlsx`;
export const exportSummaryPdfUrl = `${apiBaseUrl}/api/export/summary.pdf`;
