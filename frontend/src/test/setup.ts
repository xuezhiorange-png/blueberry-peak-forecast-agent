import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { webcrypto } from "node:crypto";

// jsdom lacks SubtleCrypto. Exercise Node's real WebCrypto, never a fake hash.
if (!globalThis.crypto.subtle)
  Object.defineProperty(globalThis.crypto, "subtle", { value: webcrypto.subtle });

afterEach(() => cleanup());
