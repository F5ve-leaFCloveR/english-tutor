import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ScenariosPage } from "./pages/ScenariosPage";
import { SessionPage } from "./pages/SessionPage";
import { PracticePage } from "./pages/PracticePage";
import { StatsPage } from "./pages/StatsPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ScenariosPage />} />
        <Route path="/session/:id" element={<SessionPage />} />
        <Route path="/practice" element={<PracticePage />} />
        <Route path="/stats" element={<StatsPage />} />
      </Routes>
    </Layout>
  );
}
