import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import DocumentsPage from "./features/documents/DocumentsPage";
import AiManagementPage from "./features/ai-management/AiManagementPage";
import WorkspacePage from "./features/cases/WorkspacePage";
import ApplyPage from "./features/review/ApplyPage";
import ExceptionsPage from "./features/review/ExceptionsPage";
import ProposalPage from "./features/review/ProposalPage";
import ReviewPage from "./features/review/ReviewPage";
import StatusPage from "./features/status/StatusPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<WorkspacePage />} />
        <Route path="cases/:caseId" element={<WorkspacePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="exceptions" element={<ExceptionsPage />} />
        <Route path="review/apply" element={<ApplyPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="review/:proposalId" element={<ProposalPage />} />
        <Route path="ai" element={<AiManagementPage />} />
        <Route path="status" element={<StatusPage />} />
      </Route>
    </Routes>
  );
}
