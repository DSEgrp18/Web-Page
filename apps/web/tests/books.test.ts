import { describe, expect, it } from "vitest";

import { bookTitle, titleFromFilename } from "../src/lib/books";
import type { DocumentSummary } from "../src/lib/types";

describe("bookTitle", () => {
  it("drops an image extension when there is no reader title", () => {
    const book = {
      title: null,
      filename: "පිටුව.png",
    } as DocumentSummary;
    expect(bookTitle(book)).toBe("පිටුව");
    expect(titleFromFilename("chapter.pdf")).toBe("chapter.pdf");
  });
});
