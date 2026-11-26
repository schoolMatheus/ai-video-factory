import {
  RouterProvider,
  type RouterProviderProps,
} from "react-router-dom";
import { createRouter } from "./router";

export function App({ router }: { router?: RouterProviderProps["router"] }) {
  return <RouterProvider router={router ?? createRouter()} />;
}
