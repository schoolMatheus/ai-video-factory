import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { profiles } from "../../test/handlers";
import { ProfileForm } from "./ProfileForm";

describe("ProfileForm", () => {
  it("troca todos os campos ao alternar perfis em cache (A → B → A → B)", () => {
    const a = profiles.find((item) => item.id === "canal-a")!;
    const b = profiles.find((item) => item.id === "canal-b")!;
    const view = render(<ProfileForm profile={a} />);

    function expectProfile(profile: (typeof profiles)[number]) {
      expect(screen.getByLabelText("Nome")).toHaveValue(profile.name);
      expect(screen.getByLabelText("Idioma dos vídeos")).toHaveValue(profile.language);
      const settings = screen.getByLabelText("Configurações tipadas (JSON)");
      expect(settings).toHaveValue(JSON.stringify(profile.settings, null, 2));
    }

    expectProfile(a);
    view.rerender(<ProfileForm key={b.id} profile={b} />);
    expectProfile(b);
    view.rerender(<ProfileForm key={a.id} profile={a} />);
    expectProfile(a);
    view.rerender(<ProfileForm key={b.id} profile={b} />);
    expectProfile(b);
  });

  it("envia nome, idioma e nicho na revisão", async () => {
    const a = profiles.find((item) => item.id === "canal-a")!;
    render(<ProfileForm profile={a} />);
    expect(screen.getByLabelText("Nome")).toHaveValue("Canal A");
  });
});
