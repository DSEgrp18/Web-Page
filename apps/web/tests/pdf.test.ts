import { describe, expect, it, vi } from "vitest";

import { renderPage } from "../src/lib/pdf";

/**
 * Why this test exists.
 *
 * pdf.js composes its transform onto whatever the canvas context already has —
 * `resetCtxToDefault` resets styles but deliberately not the matrix. Setting
 * `canvas.width` is what hands it a clean identity.
 *
 * So a second render starting while the first is still drawing resets the
 * context out from under the first, which then finishes in raw PDF coordinates
 * — y-up, origin bottom-left — and the page comes out upside down. It happens
 * on some pages and not others, entirely depending on whether a second draw
 * landed mid-render, which is what makes it look inexplicable.
 *
 * These assert the ordering that prevents it, not the pixels: jsdom has no
 * canvas, so the render is a fake whose job is to record when it was touched.
 */

/** A fake render task that finishes only when told to. */
function fakeTask() {
  let settle!: () => void;
  let rejectWith!: (error: unknown) => void;
  const promise = new Promise<void>((resolve, reject) => {
    settle = resolve;
    rejectWith = reject;
  });
  return {
    task: {
      promise,
      cancel: vi.fn(() => rejectWith(new Error("RenderingCancelledException"))),
    },
    finish: () => settle(),
  };
}

function fakePdf(onRender: (task: unknown) => void) {
  return {
    getPage: async () => ({
      getViewport: ({ scale }: { scale: number }) => ({
        width: 500 * scale,
        height: 700 * scale,
        scale,
      }),
      render: (params: unknown) => {
        const made = fakeTask();
        onRender(made);
        // Record what pdf.js was actually handed.
        (made.task as Record<string, unknown>).params = params;
        return made.task;
      },
    }),
  } as never;
}

function fakeCanvas(record: string[]) {
  const canvas = {
    style: {} as Record<string, string>,
    _width: 0,
    _height: 0,
    get width() {
      return this._width;
    },
    set width(value: number) {
      record.push(`width=${value}`);
      this._width = value;
    },
    get height() {
      return this._height;
    },
    set height(value: number) {
      this._height = value;
    },
    getContext: () => ({}),
  };
  return canvas as unknown as HTMLCanvasElement;
}

describe("rendering a page", () => {
  it("waits for a running render to stop before resizing the canvas", async () => {
    const order: string[] = [];
    const made: ReturnType<typeof fakeTask>[] = [];
    const pdf = fakePdf((t) => made.push(t as ReturnType<typeof fakeTask>));
    const canvas = fakeCanvas(order);

    const first = renderPage(pdf, 1, canvas, 500);
    // Let the first render reach `page.render`.
    await vi.waitFor(() => expect(made).toHaveLength(1));

    const second = renderPage(pdf, 2, canvas, 500);

    // The second must not have touched the canvas yet: doing so is what resets
    // the transform the first is still drawing with.
    await Promise.resolve();
    expect(made).toHaveLength(1);
    expect(made[0]!.task.cancel).toHaveBeenCalled();

    // Once the first is actually finished, the second may proceed.
    made[0]!.finish();
    await vi.waitFor(() => expect(made).toHaveLength(2));
    made[1]!.finish();

    await first.catch(() => {});
    await second;
  });

  it("cancels the first render rather than letting two draw at once", async () => {
    const made: ReturnType<typeof fakeTask>[] = [];
    const pdf = fakePdf((t) => made.push(t as ReturnType<typeof fakeTask>));
    const canvas = fakeCanvas([]);

    const first = renderPage(pdf, 1, canvas, 400);
    await vi.waitFor(() => expect(made).toHaveLength(1));

    const second = renderPage(pdf, 2, canvas, 400);
    made[0]!.finish();
    await vi.waitFor(() => expect(made).toHaveLength(2));
    made[1]!.finish();

    await first.catch(() => {});
    await second;

    // pdf.js throws "Cannot use the same canvas during multiple render
    // operations" if two overlap, so the first has to be stopped, not ignored.
    expect(made[0]!.task.cancel).toHaveBeenCalledTimes(1);
  });

  it("hands pdf.js a canvas and no context", async () => {
    const made: ReturnType<typeof fakeTask>[] = [];
    const pdf = fakePdf((t) => made.push(t as ReturnType<typeof fakeTask>));
    const canvas = fakeCanvas([]);

    const render = renderPage(pdf, 1, canvas, 400);
    await vi.waitFor(() => expect(made).toHaveLength(1));
    made[0]!.finish();
    await render;

    const params = (made[0]!.task as unknown as { params: Record<string, unknown> }).params;
    expect(params.canvas).toBe(canvas);
    // Passing both is documented as wrong, and pdf.js discards the context
    // anyway — it takes its own with `alpha: false`.
    expect(params.canvasContext).toBeUndefined();
    // No `transform` either: the device scale is folded into the viewport, so
    // there is one fewer matrix to compose and no sign to get wrong.
    expect(params.transform).toBeUndefined();
  });

  it("sizes the bitmap in device pixels and the element in CSS pixels", async () => {
    const made: ReturnType<typeof fakeTask>[] = [];
    const pdf = fakePdf((t) => made.push(t as ReturnType<typeof fakeTask>));
    const canvas = fakeCanvas([]);
    vi.stubGlobal("devicePixelRatio", 2);

    const render = renderPage(pdf, 1, canvas, 500);
    await vi.waitFor(() => expect(made).toHaveLength(1));
    made[0]!.finish();
    await render;

    // A 500px-wide page at 2x is a 1000px bitmap shown at 500 CSS pixels.
    expect(canvas.width).toBe(1000);
    expect(canvas.style.width).toBe("500px");
    vi.unstubAllGlobals();
  });
});
