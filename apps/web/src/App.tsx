import { QueryClientProvider } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ApiProvider } from "./api/ApiContext";
import { createApiClient } from "./api/client";
import type { ApiClient } from "./api/client";
import { ChatPage } from "./pages/ChatPage";
import { InterviewIntroPage } from "./pages/InterviewIntroPage";
import { InterviewReportPage } from "./pages/InterviewReportPage";
import { InterviewRoomPage } from "./pages/InterviewRoomPage";

import { createQueryClient } from "./queryClient";

export interface AppProps {
  client?: ApiClient;
  queryClient?: QueryClient;
}

export function App({ client, queryClient }: AppProps = {}) {
  const [activeClient] = useState(() => client ?? createApiClient({}));
  const [activeQueryClient] = useState(() => queryClient ?? createQueryClient());

  return (
    <QueryClientProvider client={activeQueryClient}>
      <ApiProvider client={activeClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
            <Route path="/interview" element={<InterviewIntroPage />} />
            <Route path="/interview/room/:sessionId" element={<InterviewRoomPage />} />
            <Route path="/interview/report/:sessionId" element={<InterviewReportPage />} />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </BrowserRouter>
      </ApiProvider>
    </QueryClientProvider>
  );
}

export default App;