"use client";

import { css, Global } from "@emotion/react";

const globalStyles = css({
  ":root": {
    "--bg-1": "#f4efe5",
    "--bg-2": "#dbe8d5",
    "--ink": "#1e2a24",
    "--ink-soft": "#415348",
    "--panel": "rgba(255, 255, 255, 0.68)",
    "--line": "rgba(30, 42, 36, 0.2)",
    "--accent": "#a23b2a",
    "--accent-soft": "#e8b990",
  },
  "*": {
    boxSizing: "border-box",
  },
  "html, body": {
    margin: 0,
    padding: 0,
    color: "var(--ink)",
    background:
      "radial-gradient(circle at 10% 0%, #efe1c9 0%, transparent 38%), radial-gradient(circle at 95% 10%, #c8dbd4 0%, transparent 40%), linear-gradient(145deg, var(--bg-1) 0%, var(--bg-2) 100%)",
  },
  a: {
    color: "inherit",
    textDecoration: "none",
  },
});

export default function EmotionGlobalStyles() {
  return <Global styles={globalStyles} />;
}
