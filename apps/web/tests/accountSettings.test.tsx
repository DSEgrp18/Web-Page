import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { AccountSettings } from "../src/components/AccountSettings";
import { AppFrame } from "../src/components/AppFrame";
import { strings } from "../src/lib/strings";
import { FAKE_CSRF, FakeServer } from "./fakeApi";
import { politeText, renderApp } from "./render";

const PASSWORD = "a-long-enough-password";

/** Signed in as an account the fake knows the password of. */
function signedIn(hasRecoveryCode = true) {
  const server = new FakeServer();
  server.accounts.push({
    user_id: "usr-1",
    email: "nimali@example.lk",
    password: PASSWORD,
    display_name: "නිමලි",
    has_recovery_code: hasRecoveryCode,
  });
  renderApp(
    <AppFrame>
      <AccountSettings />
    </AppFrame>,
    server,
    "usr-1",
  );
  return server;
}

/** The section of the page under this heading. */
async function section(heading: string) {
  const found = await screen.findByRole("region", { name: heading });
  return within(found);
}

describe("the account page", () => {
  it("says who is signed in", async () => {
    signedIn();
    const details = await section(strings.accountDetails);

    expect(details.getByText("නිමලි")).toBeTruthy();
    expect(details.getByText("nimali@example.lk")).toBeTruthy();
    expect(details.getByText(strings.roleName("student"))).toBeTruthy();
  });

  it("is reached from the name in the masthead", async () => {
    signedIn();
    const link = await screen.findByRole("link", { name: /නිමලි/ });

    expect(link.getAttribute("href")).toBe("/account");
    // The visible name comes first, so a voice-control user can say it.
    expect(link.textContent?.startsWith("නිමලි")).toBe(true);
  });
});

describe("changing the password", () => {
  it("changes it and stays signed in", async () => {
    const user = userEvent.setup();
    const server = signedIn();
    const form = await section(strings.changePasswordHeading);

    await user.type(form.getByLabelText(strings.currentPasswordLabel), PASSWORD);
    await user.type(form.getByLabelText(strings.newPasswordLabel), "a-brand-new-password");
    await user.click(form.getByRole("button", { name: strings.changePasswordAction }));

    await waitFor(() => expect(politeText()).toContain(strings.passwordChanged));
    expect(server.accounts[0]!.password).toBe("a-brand-new-password");
    // The change ended every session; this one signed straight back in.
    expect(server.signedInAs).toBe("usr-1");
    expect(screen.queryByRole("heading", { name: strings.signedOutHeading })).toBeNull();
  });

  it("says when the current password is wrong", async () => {
    const user = userEvent.setup();
    const server = signedIn();
    const form = await section(strings.changePasswordHeading);

    await user.type(form.getByLabelText(strings.currentPasswordLabel), "not-it-at-all");
    await user.type(form.getByLabelText(strings.newPasswordLabel), "a-brand-new-password");
    await user.click(form.getByRole("button", { name: strings.changePasswordAction }));

    const failure = await screen.findByText(strings.errorWrongPassword);
    expect(document.activeElement).toBe(failure);
    expect(server.accounts[0]!.password).toBe(PASSWORD);
  });
});

describe("a new recovery code", () => {
  it("is shown once, and leads back to the account page", async () => {
    const user = userEvent.setup();
    signedIn();
    const form = await section(strings.recoveryHeading);

    await user.type(form.getByLabelText(strings.currentPasswordLabel), PASSWORD);
    await user.click(form.getByRole("button", { name: strings.newRecoveryAction }));

    expect(await screen.findByText("NEWC-ODE2-3456-789A")).toBeTruthy();
    await user.click(screen.getByLabelText(strings.savedCodeConfirm));
    await user.click(screen.getByRole("button", { name: strings.backToAccount }));

    const heading = await screen.findByRole("heading", { name: strings.accountHeading });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  it("is asked for by an account that has none", async () => {
    signedIn(false);
    const form = await section(strings.recoveryHeading);

    expect(form.getByText(strings.recoveryMissing)).toBeTruthy();
  });
});

describe("signing out everywhere", () => {
  it("ends every session, this one too, with the CSRF token", async () => {
    const user = userEvent.setup();
    const server = signedIn();
    const form = await section(strings.everywhereHeading);

    await user.click(form.getByRole("button", { name: strings.everywhereAction }));

    await screen.findByRole("heading", { name: strings.signedOutHeading });
    const call = server.callsTo("POST", /logout-everywhere/)[0]!;
    expect(call.headers!.get("X-CSRF-Token")).toBe(FAKE_CSRF);
    await waitFor(() => expect(politeText()).toContain(strings.signedOutEverywhere));
  });
});

describe("deleting the account", () => {
  it("asks first, and cancel changes nothing", async () => {
    const user = userEvent.setup();
    const server = signedIn();
    const form = await section(strings.deleteAccountHeading);

    await user.type(form.getByLabelText(strings.currentPasswordLabel), PASSWORD);
    await user.click(form.getByRole("button", { name: strings.deleteAccountAction }));
    const dialog = await screen.findByRole("dialog", { name: strings.deleteAccountConfirmTitle });
    await user.click(within(dialog).getByRole("button", { name: strings.deleteConfirmCancel }));

    expect(server.callsTo("DELETE", /\/auth\/account/)).toEqual([]);
    expect(server.accounts).toHaveLength(1);
  });

  it("deletes everything once confirmed, and signs out", async () => {
    const user = userEvent.setup();
    const server = signedIn();
    const form = await section(strings.deleteAccountHeading);

    await user.type(form.getByLabelText(strings.currentPasswordLabel), PASSWORD);
    await user.click(form.getByRole("button", { name: strings.deleteAccountAction }));
    const dialog = await screen.findByRole("dialog", { name: strings.deleteAccountConfirmTitle });
    await user.click(within(dialog).getByRole("button", { name: strings.deleteAccountAction }));

    await screen.findByRole("heading", { name: strings.signedOutHeading });
    expect(server.accounts).toEqual([]);
    await waitFor(() => expect(politeText()).toContain(strings.accountDeleted));
  });

  it("with the wrong password deletes nothing and says why", async () => {
    const user = userEvent.setup();
    const server = signedIn();
    const form = await section(strings.deleteAccountHeading);

    await user.type(form.getByLabelText(strings.currentPasswordLabel), "not-it-at-all");
    await user.click(form.getByRole("button", { name: strings.deleteAccountAction }));
    const dialog = await screen.findByRole("dialog", { name: strings.deleteAccountConfirmTitle });
    await user.click(within(dialog).getByRole("button", { name: strings.deleteAccountAction }));

    expect(await screen.findByText(strings.errorWrongPassword)).toBeTruthy();
    expect(server.accounts).toHaveLength(1);
  });
});

describe("no automatically detectable violations", () => {
  it("on the account page", async () => {
    signedIn();
    await section(strings.accountDetails);

    const results = await axe.run(document.body, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});
