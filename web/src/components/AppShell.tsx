import { NavLink, Outlet } from "react-router-dom";
import type { ReactNode } from "react";
import styles from "./AppShell.module.css";

const LINKS = [
  { to: "/", label: "Produções" },
  { to: "/perfis", label: "Perfis" },
  { to: "/memoria", label: "Memória" },
  { to: "/ferramentas", label: "Ferramentas" },
];

export function AppShell({ children }: { children?: ReactNode }) {
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#conteudo">
        Ir para o conteúdo
      </a>
      <header className={styles.header}>
        <span className={styles.brand}>AI Video Factory</span>
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
