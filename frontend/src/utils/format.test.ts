import { expect, test } from "vitest";
import { formatMoney } from "./format";

test("formats Decimal-backed monetary strings", () => {
  expect(formatMoney("27950.00")).toBe("$27,950.00");
  expect(formatMoney(null)).toBe("—");
});
