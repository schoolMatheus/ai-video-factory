import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ProfileForm } from "./ProfileForm";
import { profiles } from "../../test/handlers";

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
});
