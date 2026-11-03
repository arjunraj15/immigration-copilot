import { createContext, useContext } from "react";

// Lets any citation, file row or table link open the document drawer without passing props around.
export const DocViewerContext = createContext<(sourceId: string) => void>(() => {});

export function useDocViewer(): (sourceId: string) => void {
  return useContext(DocViewerContext);
}
