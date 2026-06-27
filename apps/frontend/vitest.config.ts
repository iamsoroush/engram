import { defineConfig } from "vitest/config";

// Unit tests run in a Node environment and assert rendered output via react-dom/server's
// renderToStaticMarkup — no jsdom needed (we check the produced markup string, not DOM side effects).
// Vite's esbuild transforms the TSX using the automatic JSX runtime from tsconfig (jsx: react-jsx).
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
