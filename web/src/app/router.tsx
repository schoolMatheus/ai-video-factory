import { createBrowserRouter, RouteObject } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { Home } from "../features/home/Home";
import { ProductionList } from "../features/productions/ProductionList";
import { ProductionCreate } from "../features/productions/ProductionCreate";
import { ProductionWorkspace } from "../features/productions/ProductionWorkspace";
import { ProfileList } from "../features/profiles/ProfileList";
import { MemoryList } from "../features/memory/MemoryList";
import { ToolsPage } from "../features/tools/ToolsPage";
import { SettingsPage } from "../features/settings/SettingsPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },
      { path: "producoes", element: <ProductionList /> },
      { path: "novo", element: <ProductionCreate /> },
      { path: "producoes/:productionId", element: <ProductionWorkspace /> },
      { path: "perfis", element: <ProfileList /> },
      { path: "memoria", element: <MemoryList /> },
      { path: "ferramentas", element: <ToolsPage /> },
      { path: "configuracoes", element: <SettingsPage /> },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}
