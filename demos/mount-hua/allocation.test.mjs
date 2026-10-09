import test from "node:test";
import assert from "node:assert/strict";
import {
  setAddition,
  distribute,
  classify,
  assess,
  sum,
} from "./allocation.js";

test("editing one stat never spends more than the available pool or changes another stat", () => {
  const original = [4, 8, 3, 0];
  assert.deepEqual(setAddition(original, 3, 99, 20), [4, 8, 3, 5]);
  assert.deepEqual(original, [4, 8, 3, 0]);
  assert.deepEqual(setAddition(original, 1, -10, 20), [4, 0, 3, 0]);
  assert.deepEqual(setAddition(original, 0, 2.8, 20), [2, 8, 3, 0]);
});
test("example rounding conserves every point for every supported pool", () => {
  for (let pool = 0; pool <= 100; pool++) {
    for (const weights of [
      [4, 12, 4, 0],
      [9, 2, 8, 1],
      [4, 8, 7, 1],
      [1, 2, 3, 14],
    ]) {
      const result = distribute(pool, weights);
      assert.equal(sum(result), pool);
      assert.ok(result.every((n) => Number.isInteger(n) && n >= 0));
    }
  }
});
test("new mixed and technique paths use projected stats, including the existing foundation", () => {
  assert.equal(classify([5, 5, 5, 5], [0, 10, 0, 10]).name, "Mist walker");
  assert.equal(classify([5, 5, 5, 5], [0, 0, 0, 20]).name, "Inner flame");
  assert.equal(
    classify([5, 5, 5, 5], [5, 5, 5, 5]).name,
    "Fourfold foundation",
  );
  assert.equal(classify([30, 5, 5, 5], [0, 1, 0, 0]).name, "Iron fist");
});
test("feedback permits reserves and explains a mismatch with the chosen goal", () => {
  const result = assess([5, 5, 5, 5], [0, 0, 0, 15], 20, "swift");
  assert.match(result.text, /Agility/);
  assert.match(result.text, /5 remaining points unspent/);
  assert.equal(
    assess([5, 5, 5, 5], [0, 0, 0, 0], 0, "any").text.startsWith(
      "No points remain",
    ),
    true,
  );
});
