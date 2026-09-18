import { Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import HowItWorks from "./pages/HowItWorks.jsx";
import ScrollToTop from "./components/ScrollToTop.jsx";

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="*" element={<Landing />} />
      </Routes>
    </>
  );
}
