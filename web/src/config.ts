const env = import.meta.env;

export const config = {
  apiUrl: (env.VITE_API_URL) ?? "http://localhost:2024",
  dataApiUrl: (env.VITE_DATA_API_URL) ?? "http://localhost:8000",
  assistantId: (env.VITE_ASSISTANT_ID) ?? "agent",
};
