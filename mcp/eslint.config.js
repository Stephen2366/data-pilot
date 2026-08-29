import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts"],
    languageOptions: { globals: { console: "readonly", process: "readonly", Buffer: "readonly" } },
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  { ignores: ["dist/**"] },
);
