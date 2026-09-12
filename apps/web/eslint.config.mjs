import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

/**
 * jsx-a11y is the point of this file. It catches the accessibility mistakes
 * that are invisible in a browser and obvious in a screen reader: a control
 * that is a `div`, an image with no alternative, a label attached to nothing.
 * It does not replace testing with NVDA and TalkBack, and nothing here should
 * be read as if it did.
 */
export default tseslint.config(
  {
    ignores: [
      ".next/**",
      "out/**",
      "coverage/**",
      "next-env.d.ts",
      // Copied verbatim out of node_modules at build time. Linting somebody
      // else's minified bundle produces 1,700 errors about code we do not own
      // and cannot change, which buries the handful that are ours.
      "public/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // A focusable `separator` is a real ARIA widget: the spec calls it a
      // window splitter and *requires* a tabindex, arrow keys, and
      // aria-valuenow. The rule treats `separator` as non-interactive because
      // the non-focusable form is, and cannot tell the two apart — so the role
      // is named here once rather than disabled at the one place it is used.
      "jsx-a11y/no-noninteractive-tabindex": [
        "error",
        { tags: [], roles: ["tabpanel", "separator"], allowExpressionValues: true },
      ],
    },
  },
  {
    // Node built-ins used by the test harness and the contract script. Listed
    // rather than pulled from a globals package: it is four names, and a
    // dependency whose only job is to name them is a dependency to keep.
    files: ["tests/**/*.{ts,tsx}", "scripts/**/*.mjs"],
    languageOptions: {
      globals: {
        console: "readonly",
        fetch: "readonly",
        process: "readonly",
        URL: "readonly",
      },
    },
  },
);
