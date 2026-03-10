/**
 * Unit tests for isRecentlyCompleted logic used in Team tab.
 *
 * Run with: npx tsx src/__tests__/isRecentlyCompleted.test.ts
 */

const TWO_WEEKS_MS = 14 * 24 * 60 * 60 * 1000;

function isRecentlyCompleted(
  completedAt: string | undefined,
  updatedAt: string | undefined,
): boolean {
  const ref = completedAt || updatedAt;
  if (!ref) return false;
  return Date.now() - new Date(ref).getTime() < TWO_WEEKS_MS;
}

// ---------- Test runner ----------
let passed = 0;
let failed = 0;

function assert(condition: boolean, name: string) {
  if (condition) {
    passed++;
    console.log(`  ✓ ${name}`);
  } else {
    failed++;
    console.error(`  ✗ ${name}`);
  }
}

console.log("isRecentlyCompleted tests:");

// 1. Completed 1 day ago → recent
const oneDayAgo = new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString();
assert(
  isRecentlyCompleted(oneDayAgo, undefined) === true,
  "completed 1 day ago is recent",
);

// 2. Completed 13 days ago → recent
const thirteenDaysAgo = new Date(Date.now() - 13 * 24 * 60 * 60 * 1000).toISOString();
assert(
  isRecentlyCompleted(thirteenDaysAgo, undefined) === true,
  "completed 13 days ago is recent",
);

// 3. Completed 15 days ago → NOT recent
const fifteenDaysAgo = new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString();
assert(
  isRecentlyCompleted(fifteenDaysAgo, undefined) === false,
  "completed 15 days ago is NOT recent",
);

// 4. Completed 30 days ago → NOT recent
const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
assert(
  isRecentlyCompleted(thirtyDaysAgo, undefined) === false,
  "completed 30 days ago is NOT recent",
);

// 5. No completedAt, but updatedAt 3 days ago → recent (fallback)
const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
assert(
  isRecentlyCompleted(undefined, threeDaysAgo) === true,
  "updatedAt 3 days ago (fallback) is recent",
);

// 6. No completedAt, updatedAt 20 days ago → NOT recent
const twentyDaysAgo = new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString();
assert(
  isRecentlyCompleted(undefined, twentyDaysAgo) === false,
  "updatedAt 20 days ago (fallback) is NOT recent",
);

// 7. Both undefined → NOT recent
assert(
  isRecentlyCompleted(undefined, undefined) === false,
  "both undefined is NOT recent",
);

// 8. completedAt takes priority over updatedAt
assert(
  isRecentlyCompleted(oneDayAgo, twentyDaysAgo) === true,
  "completedAt (recent) takes priority over updatedAt (old)",
);

// 9. completedAt (old) takes priority over updatedAt (recent)
assert(
  isRecentlyCompleted(fifteenDaysAgo, oneDayAgo) === false,
  "completedAt (old) takes priority over updatedAt (recent)",
);

// 10. Exactly at the boundary (14 days)
const exactlyFourteenDaysAgo = new Date(Date.now() - TWO_WEEKS_MS + 1000).toISOString();
assert(
  isRecentlyCompleted(exactlyFourteenDaysAgo, undefined) === true,
  "just under 14 days is recent",
);

const justOverFourteenDays = new Date(Date.now() - TWO_WEEKS_MS - 1000).toISOString();
assert(
  isRecentlyCompleted(justOverFourteenDays, undefined) === false,
  "just over 14 days is NOT recent",
);

console.log(`\nResults: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
