import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import {
  MIN_PASSWORD_LENGTH,
  nextPath,
  RecoverForm,
  RegisterForm,
  SignInForm,
} from "../src/components/AccountForms";
import { AppFrame } from "../src/components/AppFrame";
import { Library } from "../src/components/Library";
import { strings } from "../src/lib/strings";
import { FAKE_CSRF, FakeServer } from "./fakeApi";
import { politeText, renderApp } from "./render";
import { navigations } from "./setup";

const PASSWORD = "a-long-enough-password";

/** A server with one account, and a browser that is signed out. */
function withAccount() {
  const server = new FakeServer();
  server.accounts.push({
    user_id: "usr-1",
    email: "nimali@example.lk",
    password: PASSWORD,
    display_name: "නිමලි",
  });
  return server;
}

async function violations(container: HTMLElement) {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.map((v) => v.id);
}

describe("signing in", () => {
  it("signs in, says so, and goes to the library", async () => {
    const user = userEvent.setup();
    renderApp(<SignInForm />, withAccount(), "");

    await user.type(screen.getByLabelText(strings.emailLabel), "nimali@example.lk");
    await user.type(screen.getByLabelText(strings.passwordLabel), PASSWORD);
    await user.click(screen.getByRole("button", { name: strings.signInAction }));

    await waitFor(() => expect(navigations).toEqual(["/library"]));
    expect(politeText()).toContain(strings.signedIn);
  });

  it("goes back to the page the reader was sent from", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/sign-in?next=%2Fbookmarks");
    renderApp(<SignInForm />, withAccount(), "");

    await user.type(screen.getByLabelText(strings.emailLabel), "nimali@example.lk");
    await user.type(screen.getByLabelText(strings.passwordLabel), PASSWORD);
    await user.click(screen.getByRole("button", { name: strings.signInAction }));

    await waitFor(() => expect(navigations).toEqual(["/bookmarks"]));
  });

  it("says what went wrong in one sentence, and puts focus on it", async () => {
    const user = userEvent.setup();
    renderApp(<SignInForm />, withAccount(), "");

    await user.type(screen.getByLabelText(strings.emailLabel), "nimali@example.lk");
    await user.type(screen.getByLabelText(strings.passwordLabel), "not-the-password");
    await user.click(screen.getByRole("button", { name: strings.signInAction }));

    const failure = await screen.findByText(strings.errorSignIn);
    expect(document.activeElement).toBe(failure);
    expect(navigations).toEqual([]);
  });

  it("tells a reader who has tried too often to wait, not that they are wrong", async () => {
    const user = userEvent.setup();
    const server = withAccount();
    server.throttleAccounts = true;
    renderApp(<SignInForm />, server, "");

    await user.type(screen.getByLabelText(strings.emailLabel), "nimali@example.lk");
    await user.type(screen.getByLabelText(strings.passwordLabel), PASSWORD);
    await user.click(screen.getByRole("button", { name: strings.signInAction }));

    expect(await screen.findByText(strings.errorThrottled)).toBeTruthy();
  });

  it("can show the password being typed", async () => {
    const user = userEvent.setup();
    renderApp(<SignInForm />, withAccount(), "");
    const field = screen.getByLabelText(strings.passwordLabel);
    expect(field.getAttribute("type")).toBe("password");

    await user.click(screen.getByLabelText(strings.showPassword));

    expect(field.getAttribute("type")).toBe("text");
  });

  it("gives every field what autofill and a password manager need", () => {
    renderApp(<SignInForm />, withAccount(), "");

    expect(screen.getByLabelText(strings.emailLabel).getAttribute("autocomplete")).toBe("email");
    expect(screen.getByLabelText(strings.passwordLabel).getAttribute("autocomplete")).toBe(
      "current-password",
    );
  });
});

describe("where signing in may lead", () => {
  it.each([
    ["?next=%2Fbookmarks", "/bookmarks"],
    ["", "/library"],
    ["?next=https%3A%2F%2Fevil.test", "/library"],
    ["?next=%2F%2Fevil.test", "/library"],
    ["?next=%2F%5Cevil.test", "/library"],
  ])("%s goes to %s", (search, expected) => {
    expect(nextPath(search)).toBe(expected);
  });
});

describe("making an account", () => {
  async function register(user: ReturnType<typeof userEvent.setup>, email = "new@example.lk") {
    await user.type(screen.getByLabelText(strings.displayNameLabel), "සිතාරා");
    await user.type(screen.getByLabelText(strings.emailLabel), email);
    await user.type(screen.getByLabelText(strings.passwordLabel), PASSWORD);
    await user.click(screen.getByRole("button", { name: strings.registerAction }));
  }

  it("shows the recovery code once, with focus on it, and holds it there", async () => {
    const user = userEvent.setup();
    renderApp(<RegisterForm />, new FakeServer(), "");

    await register(user);

    const heading = await screen.findByRole("heading", { name: strings.recoveryCodeHeading });
    expect(document.activeElement).toBe(heading);
    expect(screen.getByText("ABCD-EFGH-JKMN-PQRS")).toBeTruthy();
    // Moving on is a decision, not the next swipe.
    const onward = screen.getByRole("button", { name: strings.continueToLibrary });
    expect(onward).toHaveProperty("disabled", true);

    await user.click(screen.getByLabelText(strings.savedCodeConfirm));
    await user.click(onward);

    expect(navigations).toEqual(["/library"]);
  });

  it("offers the code as a copy and as a file", async () => {
    const user = userEvent.setup();
    renderApp(<RegisterForm />, new FakeServer(), "");
    await register(user);

    expect(await screen.findByRole("button", { name: strings.copyCode })).toBeTruthy();
    expect(screen.getByRole("button", { name: strings.downloadCode })).toBeTruthy();
  });

  it("says when an address already has an account, and what to do", async () => {
    const user = userEvent.setup();
    renderApp(<RegisterForm />, withAccount(), "");

    await register(user, "nimali@example.lk");

    expect(await screen.findByText(strings.errorEmailTaken)).toBeTruthy();
  });

  it("states the password rule before it is broken, and after", async () => {
    const user = userEvent.setup();
    renderApp(<RegisterForm />, new FakeServer(), "");
    expect(screen.getByText(strings.passwordHint(MIN_PASSWORD_LENGTH))).toBeTruthy();

    await user.type(screen.getByLabelText(strings.displayNameLabel), "සිතාරා");
    await user.type(screen.getByLabelText(strings.emailLabel), "new@example.lk");
    await user.type(screen.getByLabelText(strings.passwordLabel), "short");
    await user.click(screen.getByRole("button", { name: strings.registerAction }));

    expect(await screen.findByText(strings.errorWeakPassword(MIN_PASSWORD_LENGTH))).toBeTruthy();
  });
});

describe("recovering an account", () => {
  async function recover(user: ReturnType<typeof userEvent.setup>, code: string) {
    await user.type(screen.getByLabelText(strings.emailLabel), "nimali@example.lk");
    await user.type(screen.getByLabelText(strings.recoveryCodeLabel), code);
    await user.type(screen.getByLabelText(strings.newPasswordLabel), "a-brand-new-password");
    await user.click(screen.getByRole("button", { name: strings.recoverAction }));
  }

  it("sets a new password and hands over the next code", async () => {
    const user = userEvent.setup();
    renderApp(<RecoverForm />, withAccount(), "");

    await recover(user, "abcd efgh jkmn pqrs");

    expect(await screen.findByRole("heading", { name: strings.recoveryCodeHeading })).toBeTruthy();
    expect(screen.getByText("TUVW-XYZ2-3456-789A")).toBeTruthy();
  });

  it("says a wrong code does not match, and nothing more", async () => {
    const user = userEvent.setup();
    renderApp(<RecoverForm />, withAccount(), "");

    await recover(user, "AAAA-BBBB-CCCC-DDDD");

    expect(await screen.findByText(strings.errorRecover)).toBeTruthy();
  });
});

describe("signing out", () => {
  it("ends the session, clears the page, and leaves focus somewhere", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
    );

    await user.click(await screen.findByRole("button", { name: strings.signOut }));

    const heading = await screen.findByRole("heading", { name: strings.signedOutHeading });
    expect(document.activeElement).toBe(heading);
    const logout = server.callsTo("POST", /^\/auth\/logout$/)[0]!;
    expect(logout.headers!.get("X-CSRF-Token")).toBe(FAKE_CSRF);
    await waitFor(() => expect(politeText()).toContain(strings.signedOut));
  });
});

describe("no automatically detectable violations", () => {
  it.each([
    ["signing in", SignInForm],
    ["making an account", RegisterForm],
    ["recovering an account", RecoverForm],
  ])("when %s", async (_name, Form) => {
    const { container } = renderApp(<Form />, new FakeServer(), "");
    expect(await violations(container)).toEqual([]);
  });

  it("on the recovery code", async () => {
    const user = userEvent.setup();
    const { container } = renderApp(<RegisterForm />, new FakeServer(), "");
    await user.type(screen.getByLabelText(strings.displayNameLabel), "සිතාරා");
    await user.type(screen.getByLabelText(strings.emailLabel), "new@example.lk");
    await user.type(screen.getByLabelText(strings.passwordLabel), PASSWORD);
    await user.click(screen.getByRole("button", { name: strings.registerAction }));
    await screen.findByRole("heading", { name: strings.recoveryCodeHeading });

    expect(await violations(container)).toEqual([]);
  });
});
