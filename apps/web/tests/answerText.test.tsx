import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerText, answerBlocks } from "../src/components/AnswerText";

describe("a written answer, laid out", () => {
  it("makes one list item per line into a numbered list", () => {
    const text = "ඉතිහාසය වැදගත් වන්නේ:\n1. මුතුන් මිත්තන් දැනගත හැකිය.\n2. වැරදි නැවත නොවේ.";
    expect(answerBlocks(text)).toEqual([
      { kind: "paragraph", text: "ඉතිහාසය වැදගත් වන්නේ:" },
      {
        kind: "numbered",
        items: [
          { number: 1, text: "මුතුන් මිත්තන් දැනගත හැකිය." },
          { number: 2, text: "වැරදි නැවත නොවේ." },
        ],
      },
    ]);
  });

  it("splits an older one-line answer whose numbers count up", () => {
    const text = "1. ඉතිහාසය ඉගෙන ගැනීමෙන් දැනගත හැකිය. 2. ඔවුන් ගැටලු විසඳූහ. 3. වැරදි නොවේ.";
    const blocks = answerBlocks(text);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toEqual({
      kind: "numbered",
      items: [
        { number: 1, text: "ඉතිහාසය ඉගෙන ගැනීමෙන් දැනගත හැකිය." },
        { number: 2, text: "ඔවුන් ගැටලු විසඳූහ." },
        { number: 3, text: "වැරදි නොවේ." },
      ],
    });
  });

  it("leaves decimals, years and stray numbers in their sentence", () => {
    for (const text of [
      "උෂ්ණත්වය 2.5 ක් ඉහළ ගියේය.",
      "1971. 1987 කාලයේ කැරලි ඇති විය.",
      "පිටුව 3. ඉන්පසු පිටුව 7. බලන්න.",
    ]) {
      expect(answerBlocks(text)).toEqual([{ kind: "paragraph", text }]);
    }
  });

  it("keeps the book's own numbers, and paragraphs apart", () => {
    const text = "පළමු කොටස.\n\n4. සතරවැන්න.\n5. පස්වැන්න.\n\nඅවසානය.";
    const { container } = render(<AnswerText text={text} />);
    const items = [...container.querySelectorAll("li")];
    expect(items.map((li) => li.getAttribute("value"))).toEqual(["4", "5"]);
    expect(container.querySelector("ol")?.getAttribute("start")).toBe("4");
    expect([...container.querySelectorAll("p")].map((p) => p.textContent)).toEqual([
      "පළමු කොටස.",
      "අවසානය.",
    ]);
  });

  it("renders text, never markup", () => {
    const { container } = render(<AnswerText text={'<img src=x onerror="alert(1)">'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img");
  });
});
