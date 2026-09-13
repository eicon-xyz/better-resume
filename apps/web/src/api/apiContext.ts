import { createContext } from "react";

import type { ApiClient } from "./client";

/** Kept in a plain .ts module so component files only export components. */
export const ApiContext = createContext<ApiClient | null>(null);
