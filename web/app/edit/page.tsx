import { Suspense } from "react";
import EditorView from "./EditorView";

// EditorView reads ?id= with useSearchParams(); Next 16 requires that inside <Suspense>.
export default function EditClipPage() {
  return (
    <Suspense fallback={null}>
      <EditorView />
    </Suspense>
  );
}
