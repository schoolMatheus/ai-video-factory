import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ProfileForm } from "./ProfileForm";
import { profiles } from "../../test/handlers";
import { server } from "../../test/setup";

describe("ProfileForm", () => {
  it("explica conflito de revisão concorrente", async () => {
    const user = userEvent.setup();
    render(<ProfileForm profile={profiles[0]} />);

    await user.click(screen.getByRole("button", { name: "Salvar perfil" }));

    expect(
      await screen.findByText(/Outra aba ou o agente alterou este perfil/),
    ).toBeInTheDocument();
  });

  it("explica que produções em curso mantêm o snapshot", () => {
    render(<ProfileForm profile={profiles[0]} />);
    expect(screen.getByText(/produções em andamento mantêm o snapshot/i)).toBeInTheDocument();
  });

  it("cadastra o perfil com o nicho informado", async () => {
    let body: { niche?: string } | undefined;
    server.use(
      http.post("/api/v1/profiles", async ({ request }) => {
        body = (await request.json()) as { niche?: string };
        return HttpResponse.json({
          id: "canal-c",
          name: "Canal C",
          niche: "astronomia",
          revision: 1,
          settings: {},
          explicit_fields: [],
          available: true,
          problem: null,
        });
      }),
    );
    const user = userEvent.setup();
    render(<ProfileForm />);

    await user.type(screen.getByLabelText("Nome"), "Canal C");
    await user.type(screen.getByLabelText("Nicho"), "astronomia");
    await user.click(screen.getByRole("button", { name: "Salvar perfil" }));

    await waitFor(() => expect(body?.niche).toBe("astronomia"));
  });
});
