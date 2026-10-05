# Inventory changes
Make all of these changes to src/inventory.js:
1. Rename the constant MAX_SLOTS to CAPACITY everywhere (and export CAPACITY, not MAX_SLOTS).
2. removeItem never removes the first item. Fix it.
3. sortedItems must return names in ascending alphabetical order.
4. Add an exported function totalWeight(inv) that returns the sum of ITEM_WEIGHTS for the items (unknown items weigh 1).
5. The "bag full" error message must read exactly: "Inventory full (CAPACITY slots)" with the number in place of CAPACITY, e.g. "Inventory full (8 slots)".
6. Delete the deprecated legacyAdd function entirely.
