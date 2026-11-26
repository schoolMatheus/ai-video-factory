import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { Providers } from "./app/providers";
import { bootstrapSession } from "./api/client";
import "./styles/tokens.css";
import "./styles/global.css";

async function start(): Promise<void> {
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = fragment.get("token");
  if (token) {
    try {
      await bootstrapSession(token);
    } finally {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
    }
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <Providers>
        <App />
      </Providers>
    </StrictMode>,
  );
}

void start();
