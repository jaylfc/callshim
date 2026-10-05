// Inventory for the lantern game: slots of items with weights.
export const MAX_SLOTS = 8;
export const ITEM_WEIGHTS = { lantern: 3, salve: 1, rope: 2, key: 0 };

export function createInventory() {
  return { items: [], updated: 0 };
}

export function addItem(inv, name) {
  if (inv.items.length >= MAX_SLOTS) {
    throw new Error("bag full");
  }
  inv.items.push(name);
  inv.updated++;
  return inv;
}

// Deprecated: kept for old saves. Remove when saves migrate.
export function legacyAdd(inv, name) {
  inv.items[inv.items.length] = name;
  return inv;
}

export function removeItem(inv, name) {
  const i = inv.items.indexOf(name);
  if (i > 0) {
    inv.items.splice(i, 1);
    inv.updated++;
  }
  return inv;
}

export function sortedItems(inv) {
  return [...inv.items].sort((a, b) => b.localeCompare(a));
}

export function hasRoom(inv) {
  return inv.items.length < MAX_SLOTS;
}

export function describe(inv) {
  return `${inv.items.length}/${MAX_SLOTS} slots used`;
}
