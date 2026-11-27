import { NavLink, Outlet } from "react-router-dom";
import type { ReactNode } from "react";
import styles from "./AppShell.module.css";

const LINKS = [
  { to: "/", label: "Início" },
  { to: "/producoes", label: "Produções" },
  { to: "/perfis", label: "Perfis" },
  { to: "/memoria", label: "Memória" },
  { to: "/ferramentas", label: "Ferramentas" },
  { to: "/configuracoes", label: "Configurações" },
];

export function AppShell({ children }: { children?: ReactNode }) {
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#conteudo">
        Ir para o conteúdo
      </a>
      <header className={styles.header}>
        <NavLink to="/" className={styles.brand}>
          <img className={styles.logo} src="/logo.png" alt="" width={36} height={36} />
          AI Video Factory
        </NavLink>
        <nav aria-label="Navegação principal">
          <ul className={styles.nav}>
            {LINKS.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.to === "/"}
                  className={({ isActive }) =>
                    isActive ? styles.active : undefined
                  }
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="conteudo" tabIndex={-1}>
        {children}
        <Outlet />
      </main>
    </div>
  );
}
