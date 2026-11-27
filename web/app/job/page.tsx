import { Suspense } from "react";
import JobView from "./JobView";

// JobView reads ?id= with useSearchParams(); Next 16 requires that inside <Suspense>.
export default function JobPage() {
  return (
    <Suspense fallback={null}>
      <JobView />
    </Suspense>
  );
}
