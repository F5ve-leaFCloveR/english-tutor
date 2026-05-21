import { Routes, Route } from "react-router-dom";

function HomePlaceholder() {
  return <div className="p-8">English Tutor — frontend up.</div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePlaceholder />} />
    </Routes>
  );
}
