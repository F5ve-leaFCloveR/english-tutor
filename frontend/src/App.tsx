import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ScenariosPage } from "./pages/ScenariosPage";
import { SessionPage } from "./pages/SessionPage";
import { ReviewPage } from "./pages/ReviewPage";
import { ReviewDetail } from "./pages/ReviewDetail";
import { PracticePage } from "./pages/PracticePage";
import { ChatPage } from "./pages/ChatPage";
import { StatsPage } from "./pages/StatsPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ScenariosPage />} />
        <Route path="/session/:id" element={<SessionPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/review/:sessionId" element={<ReviewDetail />} />
        <Route path="/practice" element={<PracticePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/stats" element={<StatsPage />} />
      </Routes>
    </Layout>
  );
}
