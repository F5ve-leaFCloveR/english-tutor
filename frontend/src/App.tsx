import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ScenariosPage } from "./pages/ScenariosPage";

function Placeholder({ label }: { label: string }) {
  return <div className="p-8 text-slate-600">{label}</div>;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ScenariosPage />} />
        <Route path="/session/:id" element={<Placeholder label="Session page coming soon" />} />
        <Route path="/review" element={<Placeholder label="Review page coming soon" />} />
        <Route path="/stats" element={<Placeholder label="Stats page coming soon" />} />
      </Routes>
    </Layout>
  );
}
