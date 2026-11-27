import { Suspense } from "react";
import ExportView from "./ExportView";

export default function ExportPage() {
  return (
    <Suspense fallback={null}>
      <ExportView />
    </Suspense>
  );
}
