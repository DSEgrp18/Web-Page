import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AppFrame } from "../src/components/AppFrame";
import { ClassDetail } from "../src/components/ClassDetail";
import { Classes } from "../src/components/Classes";
import { Library } from "../src/components/Library";
import { ShareBook } from "../src/components/ShareBook";
import { strings } from "../src/lib/strings";
import type { FlaggedPage } from "../src/lib/types";
import { FakeServer, readablePage, type FakeClass } from "./fakeApi";
import { noticeText, opensBook, politeText, renderApp } from "./render";
import { navigations } from "./setup";

const TEACHER = "usr-teacher";
const STUDENT = "usr-student";

function school(): FakeServer {
  const server = new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["පළමු වාක්‍යය."])],
      },
    ],
  });
  server.accounts.push(
    { user_id: TEACHER, email: "t@example.lk", password: "x", display_name: "සුනිල්" },
    { user_id: STUDENT, email: "s@example.lk", password: "x", display_name: "නිමලි" },
  );
  server.teachers.add(TEACHER);
  return server;
}

function room(overrides: Partial<FakeClass> = {}): FakeClass {
  return {
    class_id: "cls-a",
    name: "10 ශ්‍රේණිය",
    join_code: "12345678",
    teacher: TEACHER,
    members: [],
    ...overrides,
  };
}

function member(state: "pending" | "active", share = false) {
  return {
    user_id: STUDENT,
    display_name: "නිමලි",
    state,
    share_progress: share,
    joined_at: "2026-09-10T00:00:00Z",
  };
}

async function region(name: string) {
  return within(await screen.findByRole("region", { name }));
}

describe("joining a class", () => {
  it("asks to join with the code, and waits for the teacher", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    renderApp(<Classes />, server, STUDENT);

    const join = await region(strings.joinHeading);
    await user.type(join.getByLabelText(strings.joinCodeLabel), "1234 5678");
    await user.click(join.getByRole("button", { name: strings.joinAction }));

    await waitFor(() => expect(politeText()).toContain(strings.joinedWaiting("10 ශ්‍රේණිය")));
    const joined = await region(strings.joinedHeading);
    expect(await joined.findByText(strings.memberState("pending"))).toBeTruthy();
    expect(joined.getByText(new RegExp(strings.teacherOf("සුනිල්")))).toBeTruthy();
  });

  it("shares progress only when the reader ticks the box", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    renderApp(<Classes />, server, STUDENT);

    const join = await region(strings.joinHeading);
    const consent = join.getByRole("checkbox", { name: strings.shareProgressLabel });
    expect((consent as HTMLInputElement).checked).toBe(false);
    await user.type(join.getByLabelText(strings.joinCodeLabel), "12345678");
    await user.click(join.getByRole("button", { name: strings.joinAction }));

    await waitFor(() => expect(server.classes[0]!.members).toHaveLength(1));
    expect(server.classes[0]!.members[0]!.share_progress).toBe(false);
    expect(server.callsTo("PUT", /share-progress/)).toEqual([]);
  });

  it("sends the consent when it is given", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    renderApp(<Classes />, server, STUDENT);

    const join = await region(strings.joinHeading);
    await user.click(join.getByRole("checkbox", { name: strings.shareProgressLabel }));
    await user.type(join.getByLabelText(strings.joinCodeLabel), "12345678");
    await user.click(join.getByRole("button", { name: strings.joinAction }));

    await waitFor(() => expect(server.classes[0]!.members[0]?.share_progress).toBe(true));
  });

  it("says plainly when no class has the code", async () => {
    const user = userEvent.setup();
    renderApp(<Classes />, school(), STUDENT);

    const join = await region(strings.joinHeading);
    await user.type(join.getByLabelText(strings.joinCodeLabel), "99999999");
    await user.click(join.getByRole("button", { name: strings.joinAction }));

    await waitFor(() => expect(noticeText()).toContain(strings.errorNoClassCode));
  });

  it("lets a student stop sharing, and leave", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room({ members: [member("active", true)] }));
    renderApp(<Classes />, server, STUDENT);

    const joined = await region(strings.joinedHeading);
    // The class's name is in the label too, so each class's box is its own.
    const toggle = await joined.findByRole("checkbox", { name: /10 ශ්‍රේණිය/ });
    await user.click(toggle);
    await waitFor(() => expect(server.classes[0]!.members[0]!.share_progress).toBe(false));

    await user.click(
      joined.getByRole("button", { name: new RegExp(`${strings.leaveClass}.*10 ශ්‍රේණිය`) }),
    );
    await waitFor(() => expect(politeText()).toContain(strings.leftClass));
    expect(await joined.findByText(strings.noJoined)).toBeTruthy();
  });

  it("does not offer a student a class of their own", async () => {
    renderApp(<Classes />, school(), STUDENT);

    await region(strings.joinedHeading);
    expect(screen.queryByRole("region", { name: strings.teachingHeading })).toBeNull();
  });
});

describe("a teacher's classes", () => {
  it("makes a class and lists it with a link", async () => {
    const user = userEvent.setup();
    const server = school();
    renderApp(<Classes />, server, TEACHER);

    const teaching = await region(strings.teachingHeading);
    await user.type(teaching.getByLabelText(strings.createClassLabel), "11 ශ්‍රේණිය");
    await user.click(teaching.getByRole("button", { name: strings.createClassAction }));

    const link = await teaching.findByRole("link", { name: "11 ශ්‍රේණිය" });
    expect(link.getAttribute("href")).toBe(`/classes/${server.classes[0]!.class_id}`);
    expect(politeText()).toContain(strings.classCreated);
  });
});

describe("one class, as its teacher", () => {
  it("shows the code and lets a waiting student in", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room({ members: [member("pending")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    const code = await region(strings.classCodeHeading);
    expect(code.getByText("1234 5678")).toBeTruthy();

    const table = await screen.findByRole("table", { name: strings.membersHeading });
    const row = within(table).getByRole("row", { name: /නිමලි/ });
    expect(within(row).getByRole("rowheader").textContent).toBe("නිමලි");
    await user.click(within(row).getByRole("button", { name: strings.approveNamed("නිමලි") }));

    await waitFor(() => expect(server.classes[0]!.members[0]!.state).toBe("active"));
    expect(politeText()).toContain(strings.memberApproved("නිමලි"));
    expect(within(row).queryByRole("button", { name: strings.approveNamed("නිමලි") })).toBeNull();
  });

  it("gives an approved student a new recovery code, after asking", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room({ members: [member("active")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    const ask = await screen.findByRole("button", { name: strings.resetNamed("නිමලි") });
    await user.click(ask);
    const dialog = await screen.findByRole("dialog", {
      name: strings.resetConfirmTitle("නිමලි"),
    });
    expect(server.issuedResets).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: strings.resetConfirmAction }));

    const heading = await screen.findByRole("heading", {
      name: strings.resetCodeHeading("නිමලි"),
    });
    expect(server.issuedResets).toEqual([STUDENT]);
    expect(screen.getByText("RSET-CODE-2345-6789")).toBeTruthy();
    expect(politeText()).toContain(strings.resetIssued("නිමලි"));
    await waitFor(() => expect(document.activeElement).toBe(heading));

    await user.click(screen.getByRole("button", { name: strings.resetDone }));
    expect(screen.queryByText("RSET-CODE-2345-6789")).toBeNull();
    expect(document.activeElement).toBe(ask);
  });

  it("does not issue a code when the teacher cancels", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room({ members: [member("active")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    await user.click(await screen.findByRole("button", { name: strings.resetNamed("නිමලි") }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: strings.deleteConfirmCancel }));

    expect(server.issuedResets).toEqual([]);
  });

  it("offers no code to a student still waiting", async () => {
    const server = school();
    server.classes.push(room({ members: [member("pending")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    await screen.findByRole("button", { name: strings.approveNamed("නිමලි") });
    expect(screen.queryByRole("button", { name: strings.resetNamed("නිමලි") })).toBeNull();
  });

  it("takes a student out", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room({ members: [member("active")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    await user.click(await screen.findByRole("button", { name: strings.removeNamed("නිමලි") }));

    expect(await screen.findByText(strings.noMembers)).toBeTruthy();
    expect(server.classes[0]!.members[0]!.state).toBe("removed");
  });

  it("makes a new code, which retires the old one", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    await user.click(await screen.findByRole("button", { name: strings.newCodeAction }));

    await waitFor(() => expect(politeText()).toContain(strings.newCodeDone));
    expect(server.classes[0]!.join_code).not.toBe("12345678");
    expect(screen.queryByText("1234 5678")).toBeNull();
  });

  it("deletes the class only after asking, then goes back to the classes", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    const zone = await region(strings.deleteClassAction);
    await user.click(zone.getByRole("button", { name: strings.deleteClassAction }));
    expect(server.classes).toHaveLength(1);

    const dialog = await screen.findByRole("dialog", { name: strings.deleteClassConfirmTitle });
    await user.click(within(dialog).getByRole("button", { name: strings.deleteClassAction }));

    await waitFor(() => expect(server.classes).toHaveLength(0));
    await waitFor(() => expect(navigations).toContain("/classes"));
  });
});

describe("one class, as anyone else", () => {
  it("shows a student their standing, with no code and no classmates", async () => {
    const server = school();
    server.classes.push(room({ members: [member("pending")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, STUDENT);

    expect(
      await screen.findByRole("heading", { name: strings.memberState("pending") }),
    ).toBeTruthy();
    expect(screen.queryByText("1234 5678")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("is not found for a reader outside it", async () => {
    const server = school();
    server.accounts.push({
      user_id: "usr-other",
      email: "o@example.lk",
      password: "x",
      display_name: "කසුන්",
    });
    server.classes.push(room({ members: [member("active")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, "usr-other");

    expect(await screen.findByRole("heading", { name: strings.errorNotFound })).toBeTruthy();
  });
});

function flagged(pageIndex: number, decision: FlaggedPage["decision"] = null): FlaggedPage {
  return {
    page_index: pageIndex,
    page_label: String(pageIndex + 1),
    quality: "needs_review",
    notes: [],
    decision,
  };
}

describe("sharing a book", () => {
  it("decides the flagged pages, attests, and shares", async () => {
    const user = userEvent.setup();
    const server = school();
    server.books[0]!.title = null;
    server.classes.push(room());
    server.reviews["doc-1"] = [flagged(4)];
    renderApp(<ShareBook documentId="doc-1" />, server, TEACHER);

    const page = await screen.findByRole("group", { name: `${strings.pageWord} 5` });
    await user.click(within(page).getByRole("radio", { name: strings.pageWithhold }));
    await waitFor(() => expect(server.reviews["doc-1"]![0]!.decision).toBe("withheld"));

    const basis = screen.getByRole("group", { name: strings.basisIntro });
    await user.click(
      within(basis).getByRole("radio", { name: strings.basisName("government_textbook") }),
    );
    await user.click(screen.getByRole("checkbox", { name: "10 ශ්‍රේණිය" }));
    await user.click(screen.getByRole("button", { name: strings.publishAction }));

    await waitFor(() => expect(politeText()).toContain(strings.published));
    expect(server.publications["doc-1"]).toMatchObject({
      basis: "government_textbook",
      class_ids: ["cls-a"],
    });
    const shared = await region(strings.sharedWithHeading);
    expect(
      shared.getByRole("button", { name: strings.stopSharingNamed("10 ශ්‍රේණිය") }),
    ).toBeTruthy();
  });

  it("says what to do first, in the order the form reads, before asking the server", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    server.reviews["doc-1"] = [flagged(4)];
    renderApp(<ShareBook documentId="doc-1" />, server, TEACHER);

    await user.click(await screen.findByRole("button", { name: strings.publishAction }));
    expect(noticeText()).toContain(strings.errorUnreviewed);

    const page = screen.getByRole("group", { name: `${strings.pageWord} 5` });
    await user.click(within(page).getByRole("radio", { name: strings.pageAccept }));
    await waitFor(() => expect(server.reviews["doc-1"]![0]!.decision).toBe("accepted"));
    await user.click(screen.getByRole("button", { name: strings.publishAction }));
    expect(noticeText()).toContain(strings.errorChooseBasis);

    await user.click(screen.getByRole("radio", { name: strings.basisName("other") }));
    await user.click(screen.getByRole("button", { name: strings.publishAction }));
    expect(noticeText()).toContain(strings.errorBasisNote);

    await user.type(screen.getByLabelText(strings.basisNoteLabel), "පාසලේ අවසරය");
    await user.click(screen.getByRole("button", { name: strings.publishAction }));
    expect(noticeText()).toContain(strings.errorChooseClass);

    expect(server.callsTo("POST", /\/publish$/)).toEqual([]);
  });

  it("stops sharing with a class", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room());
    server.publications["doc-1"] = {
      version: "v1",
      basis: "own_work",
      note: null,
      attested_at: "2026-09-10T00:00:00Z",
      published_at: "2026-09-10T00:00:00Z",
      class_ids: ["cls-a"],
      stale: true,
    };
    renderApp(<ShareBook documentId="doc-1" />, server, TEACHER);

    const shared = await region(strings.sharedWithHeading);
    expect(shared.getByText(strings.staleShare)).toBeTruthy();
    await user.click(shared.getByRole("button", { name: strings.stopSharingNamed("10 ශ්‍රේණිය") }));

    expect(await shared.findByText(strings.notShared)).toBeTruthy();
    expect(politeText()).toContain(strings.stoppedSharing);
  });

  it("tells a student that only teachers share", async () => {
    renderApp(<ShareBook documentId="doc-1" />, school(), STUDENT);

    expect(await screen.findByText(strings.onlyTeachersShare)).toBeTruthy();
    expect(screen.queryByRole("button", { name: strings.publishAction })).toBeNull();
  });
});

describe("the library", () => {
  it("lists books from the reader's classes in a section of their own", async () => {
    const server = school();
    server.classes.push(room({ members: [member("active")] }));
    server.publications["doc-1"] = {
      version: "v1",
      basis: "own_work",
      note: null,
      attested_at: "2026-09-10T00:00:00Z",
      published_at: "2026-09-10T00:00:00Z",
      class_ids: ["cls-a"],
      stale: false,
    };
    renderApp(<Library />, server, STUDENT);

    const section = await region(strings.fromYourClasses);
    expect(section.getByRole("link", { name: "ඉතිහාසය.pdf" }).getAttribute("href")).toBe(
      "/library/doc-1",
    );
    expect(section.getByText(strings.classBookFrom("10 ශ්‍රේණිය"))).toBeTruthy();
  });

  it("says nothing about classes to a reader in none", async () => {
    renderApp(<Library />, school(), STUDENT);

    await waitFor(() => expect(screen.queryByText(strings.pageLoading)).toBeNull());
    expect(screen.queryByRole("region", { name: strings.fromYourClasses })).toBeNull();
  });

  it("offers sharing on a teacher's ready book", async () => {
    renderApp(<Library />, school(), TEACHER);

    const share = await screen.findByRole("link", { name: new RegExp(strings.shareBook) });
    expect(share.getAttribute("href")).toBe("/library/doc-1/share");
  });

  it("does not offer sharing to a student", async () => {
    renderApp(<Library />, school(), STUDENT);

    await screen.findByRole("link", { name: opensBook("ඉතිහාසය.pdf") });
    expect(screen.queryByRole("link", { name: new RegExp(strings.shareBook) })).toBeNull();
  });
});

describe("a student whose teacher made a reset code", () => {
  function told(used = false) {
    const server = school();
    server.resetNotices[STUDENT] = {
      teacher_name: "සුනිල්",
      issued_at: "2026-09-10T08:00:00Z",
      used,
    };
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
      STUDENT,
    );
    return server;
  }

  it("is told, by name, before anything else on the screen", async () => {
    told();

    const notice = await region(strings.resetNoticeHeading);
    expect(notice.getByText(/සුනිල් ගුරුවරයා/)).toBeTruthy();
    const main = document.querySelector("main")!;
    expect(main.firstElementChild?.querySelector("h2")?.textContent).toBe(
      strings.resetNoticeHeading,
    );
  });

  it("says whether the code was used", async () => {
    told(true);

    const notice = await region(strings.resetNoticeHeading);
    expect(notice.getByText(/එම කේතයෙන් මුරපදය වෙනස් කර ඇත/)).toBeTruthy();
  });

  it("stays until they say they have seen it, then leaves focus on the screen", async () => {
    const user = userEvent.setup();
    const server = told();

    const notice = await region(strings.resetNoticeHeading);
    await user.click(notice.getByRole("button", { name: strings.resetNoticeSeen }));

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: strings.resetNoticeHeading })).toBeNull(),
    );
    expect(server.resetNotices[STUDENT]).toBeUndefined();
    expect(document.activeElement?.tagName).toBe("H1");
  });

  it("says nothing when there is nothing to tell", async () => {
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      school(),
      STUDENT,
    );

    await screen.findByRole("link", { name: opensBook("ඉතිහාසය.pdf") });
    expect(screen.queryByRole("region", { name: strings.resetNoticeHeading })).toBeNull();
  });

  it("is told once the teacher has made one", async () => {
    const user = userEvent.setup();
    const server = school();
    server.classes.push(room({ members: [member("active")] }));
    renderApp(<ClassDetail classId="cls-a" />, server, TEACHER);

    await user.click(await screen.findByRole("button", { name: strings.resetNamed("නිමලි") }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: strings.resetConfirmAction }));

    await screen.findByRole("heading", { name: strings.resetCodeHeading("නිමලි") });
    expect(server.resetNotices[STUDENT]?.teacher_name).toBe("සුනිල්");
  });
});

describe("voicing a shared book for the class", () => {
  function shared() {
    const server = school();
    server.classes.push(room());
    server.publications["doc-1"] = {
      version: "v1",
      basis: "own_work",
      note: null,
      attested_at: "2026-09-10T00:00:00Z",
      published_at: "2026-09-10T00:00:00Z",
      class_ids: ["cls-a"],
      stale: false,
    };
    renderApp(<ShareBook documentId="doc-1" />, server, TEACHER);
    return server;
  }

  it("says how much is ready, and voices the rest on request", async () => {
    const user = userEvent.setup();
    const server = shared();

    const section = await region(strings.prerenderHeading);
    expect(await section.findByText(strings.prerenderProgress(0, 12))).toBeTruthy();
    await user.click(section.getByRole("button", { name: strings.prerenderAction }));

    expect(await section.findByText(strings.prerenderDone)).toBeTruthy();
    expect(server.prerendered.has("doc-1")).toBe(true);
    expect(politeText()).toContain(strings.prerenderDone);
    expect(section.queryByRole("button", { name: strings.prerenderAction })).toBeNull();
  });

  it("is not offered before the book is shared", async () => {
    const server = school();
    server.classes.push(room());
    renderApp(<ShareBook documentId="doc-1" />, server, TEACHER);

    await region(strings.sharedWithHeading);
    expect(screen.queryByRole("region", { name: strings.prerenderHeading })).toBeNull();
  });
});
